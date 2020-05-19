import warnings

import pytest
import unittest.mock 

import httptools

import aioweb.protocol


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

    def write(self, data):
        if self._fail_next:
            self._fail_next = False
            raise BaseException()
        self._data = data

    def is_closing(self):
        return self._is_closing

    def close(self):
        self._is_closing = True

    def fail_next(self):
        self._fail_next = True

class DummyContainer:

    def __init__(self):
        self._request = None 
        self._handle_request_called = False
        self._exc = None

    async def handle_request(self, request):
        self._request = request
        self._handle_request_called = True 
        if self._exc is not None:
            exc = self._exc
            self._exc = None
            raise exc
        return b"abc"

    def set_exception(self, exc):
        self._exc = exc
    

@pytest.fixture
def transport():
    return DummyTransport()

@pytest.fixture
def container():
    return DummyContainer()

##############################################################
# These test cases test individual callbacks
##############################################################

def test_on_header():
    protocol = aioweb.protocol.HttpProtocol(container=None, loop=unittest.mock.Mock())
    protocol.on_header(b"Host", b"127.0.0.1")
    protocol.on_header(b"A", b"B")
    headers = protocol.get_headers()
    assert "Host" in headers
    assert "A" in headers
    assert headers["Host"] == b"127.0.0.1"
    assert headers["A"] == b"B"
    assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER

def test_on_headers_complete():
    with unittest.mock.patch("aioweb.protocol.httptools.HttpRequestParser") as mock:
        with unittest.mock.patch("aioweb.protocol.asyncio.Queue") as Queue:
            protocol = aioweb.protocol.HttpProtocol(container=None, loop=unittest.mock.Mock())
            #
            # Simulate data to make sure that the protocol creates a parser
            #
            protocol.data_received(b"X")
            protocol.on_header(b"Host", b"127.0.0.1")
            protocol.on_headers_complete()
            queue = Queue.return_value
    #
    # Verify the state
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.BODY
    #
    # Check that we have added something to the queue
    #
    queue.put_nowait.assert_called()

def test_on_message_complete():
    with unittest.mock.patch("aioweb.protocol.httptools.HttpRequestParser") as mock:
        protocol = aioweb.protocol.HttpProtocol(container=None, loop=unittest.mock.Mock())
        protocol.on_message_complete()
    #
    # Verify the state
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING


##############################################################
# The test cases below this line simulate a full roundtrip
# using a "real" parser instead of calling the callbacks
##############################################################

    
def test_full_request_lifecycle_http11(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should suspend and wait
    #
    coro.send(None)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

X'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    assert protocol.get_state() == aioweb.protocol.ConnectionState.BODY
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function 
    #
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    #
    # Verify some attributes of the request object
    #
    request = container._request
    assert isinstance(request, aioweb.request.Request)
    headers = request.headers()
    assert headers is not None
    assert isinstance(headers, dict)
    assert "Host" in headers
    assert headers["Host"] == b"example.com"
    assert request.http_version() == "1.1"
    #
    # Get the future to wait for completion of the body
    #
    future = request.body().send(None)
    #
    # In our case, the body should not be complete yet
    #
    assert not future.done()
    #
    # complete it
    #
    request = b'YZ'
    protocol.data_received(request)
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING
    #
    # At this point, our future should be complete
    #
    body = future.result()
    assert body == b"XYZ"
    #
    # Verify that we have written back something into the transport
    #
    assert len(transport._data) > 0
    #
    # Now let us try to parse the response data
    #
    parser_helper = ParserHelper()
    parser = httptools.HttpResponseParser(parser_helper)
    parser.feed_data(transport._data)
    #
    # If we get to this point, this is a valid HTTP response
    #
    assert parser.get_status_code() == 200
    assert parser_helper._body == b"abc"
    #
    # Finally check that the transport is not closed
    #
    assert not transport._is_closing


#
# We now use HTTP 1.0 and verify that we get the same version back
# and do not use keep alive
#
def test_full_request_lifecycle_http10(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    coro.send(None)
    #
    # Feed some data 
    #
    request = b'''GET / HTTP/1.0
Host: example.com
Content-Length: 3

123'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function
    #
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    #
    # Verify some attributes of the request object
    #
    request = container._request
    assert isinstance(request, aioweb.request.Request)
    headers = request.headers()
    assert headers is not None
    assert isinstance(headers, dict)
    assert "Host" in headers
    assert headers["Host"] == b"example.com"
    assert request.http_version() == "1.0"
    assert not request.keep_alive() 
    #
    # Verify that we have written back something into the transport
    #
    assert len(transport._data) > 0
    #
    # Now let us try to parse the response data
    #
    parser_helper = ParserHelper()
    parser = httptools.HttpResponseParser(parser_helper)
    parser.feed_data(transport._data)
    #
    # If we get to this point, this is a valid HTTP response
    #
    assert parser.get_status_code() == 200
    assert parser_helper._body == b"abc"
    #
    # Finally check that the transport is closed
    #
    assert transport._is_closing



