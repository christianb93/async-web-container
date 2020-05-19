import pytest
import aioweb.protocol
import unittest.mock
import httptools

#
# Here we collect tests to verify that pipelining
# is supported
#

###############################################
# Some helper classes
###############################################

class ParserHelper:

    def __init__(self):
        self._headers = None
        self._body = None

    def on_body(self, data):
        if self._body is None:
            self._body = bytearray()
        self._body.extend(data)

class DummyTransport:

    def __init__(self):
        self._data = b""
        self._is_closing = False
        self._fail_next = False
        self._messages = []

    def write(self, data):
        if self._fail_next:
            self._fail_next = False
            raise BaseException()
        self._messages.append(data)

    def is_closing(self):
        return self._is_closing

    def close(self):
        self._is_closing = True

    def fail_next(self):
        self._fail_next = True

class DummyContainer:

    def __init__(self):
        self._requests = [] 
        self._replies = []
        self._request_count = 0

    async def handle_request(self, request):
        self._requests.append(request)
        self._request_count += 1 
        #
        # Wait for body
        #
        body = await request.body()
        self._replies.append(body)
        return body

    

@pytest.fixture
def transport():
    return DummyTransport()

@pytest.fixture
def container():
    return DummyContainer()

#############################################
# The actual test cases
#############################################

def test_pipelining(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # Feed a first complete record
    #
    request = b'''GET / HTTP/1.1
Host: example1.com
Content-Length: 3

XYZ'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING
    #
    # Now feed a second record
    #
    request = b'''GET / HTTP/1.1
Host: example2.com
Content-Length: 3

123'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING
    #
    # Now simulate the event loop and run the coroutine for the first time
    #   
    coro.send(None)
    #
    # This should again block on the queue, but only after the two records
    # have been received. Thus we should have invoked our handler twice
    #
    assert container._request_count == 2
    #
    # Get the first request
    #
    request = container._requests[0]
    assert isinstance (request, aioweb.request.Request)
    #
    # this should be the first request
    #
    assert request.headers()['Host'] == b"example1.com"
    #
    # check content of first response
    # 
    assert container._replies[0] == b"XYZ"
    #
    # Now check the second request
    #
    request = container._requests[1]
    assert isinstance (request, aioweb.request.Request)
    assert request.headers()['Host'] == b"example2.com"
    assert container._replies[1] == b"123"
    #
    # Now we check that two responses have been written into 
    # the transport. We get them from the transport and send them
    # through our parser
    #   
    parser_helper = ParserHelper()
    parser = httptools.HttpResponseParser(parser_helper)
    parser.feed_data(transport._messages[0])
    assert parser.get_status_code() == 200
    assert bytes(parser_helper._body) == b"XYZ"

    parser_helper = ParserHelper()
    parser = httptools.HttpResponseParser(parser_helper)
    parser.feed_data(transport._messages[1])
    assert parser.get_status_code() == 200
    assert bytes(parser_helper._body) == b"123"

