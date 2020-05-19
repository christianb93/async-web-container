import asyncio
import warnings

import pytest
import unittest.mock 

import httptools

import aioweb.protocol

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



def test_header_received(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
    #
    # Feed some data. Here we feed one header line and
    # start a second one, but do not complete the message
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Test: x
'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER
    assert "Host" in protocol.get_headers()
    assert protocol.get_headers()["Host"] == b"example.com"

def test_headers_complete(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
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
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None

#
# Testcase: waiting for the future raises a CancelledError
#
def test_headers_complete_task_cancelled(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Now throw a CancelledError into the coroutine and verify that it
    # is re-raised
    #
    raised = 0
    try:
        coro.throw(asyncio.exceptions.CancelledError())
    except asyncio.exceptions.CancelledError:
        raised = 1
    assert raised == 1
    
#
# Testcase: waiting for the future raises a timeout error
#
def test_headers_complete_task_timeout():
    transport = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Now throw a CancelledError into the coroutine and verify that it
    # is re-raised
    #
    raised = 0
    try:
        coro.throw(asyncio.exceptions.TimeoutError())
    except asyncio.exceptions.CancelledError:
        raised = 1
    assert raised == 1
    #
    # Verify that the transport has been closed
    # 
    transport.close.assert_called()


#
# Testcase: waiting for the future raises a base exception
#
def test_headers_complete_task_base_exception():
    transport = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Now throw a CancelledError into the coroutine and verify that it
    # is re-raised
    #
    raised = 0
    try:
        coro.throw(BaseException())
    except BaseException:
        raised = 1
    assert raised == 1


#
# We now simulate the full life cycle of a request
#
def test_user_handler_called(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
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
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None
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
    assert isinstance(future, asyncio.Future)
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

def test_user_handler_second_call(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # We now go through the full cycle once to simulate the
    # first request
    #
    future = coro.send(None)
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

ABC'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    result = future.result()
    #
    # As the body is complete, the next simulated scheduling of the coroutine
    # should make it run until it waits for the next request
    #
    future = coro.send(None)
    assert container._request is not None
    assert len(transport._data) > 0
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
    # Now go through the cycle once more to simulate a second request coming in 
    # via the same connection
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

ABC'''
    container._request = None
    transport._data = b""
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    result = future.result()
    coro.send(None)
    assert container._request is not None
    assert len(transport._data) > 0
    parser_helper = ParserHelper()
    parser = httptools.HttpResponseParser(parser_helper)
    parser.feed_data(transport._data)
    #
    # Again, we should get a valid HTTP response
    #
    assert parser.get_status_code() == 200
    assert parser_helper._body == b"abc"


#
# We now test some error cases, i.e. the case that the
# user provided handler raises an exception
#
def test_user_handler_http_exception(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

XXX'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function. We instruct
    # our container to raise an exception
    #
    container.set_exception(aioweb.exceptions.HTTPException())
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    request = container._request
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
    # and we should see an error
    #
    assert parser.get_status_code() == 500

def test_user_handler_cancelled_error(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

XXX'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function. We instruct
    # our container to raise an exception
    #
    container.set_exception(asyncio.exceptions.CancelledError())
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    request = container._request
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
    # and we should see an error
    #
    assert parser.get_status_code() == 500

def test_user_handler_timeout_error(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

XXX'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function. We instruct
    # our container to raise an exception
    #
    container.set_exception(asyncio.exceptions.TimeoutError())
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    request = container._request
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
    # and we should see an error
    #
    assert parser.get_status_code() == 500

def test_user_handler_base_exception(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

XXX'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function. We instruct
    # our container to raise an exception
    #
    container.set_exception(BaseException())
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    request = container._request
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
    # and we should see an error
    #
    assert parser.get_status_code() == 500

def test_user_handler_transport_closing(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

XXX'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function. Before
    # we do this, we close the transport - this should stop the handler
    #
    transport.close()
    try:
        coro.send(None)
    except StopIteration:
        pass
    else:
        assert 1 == 0
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    request = container._request
    #
    # Verify that we have not written anything into the transport
    #
    assert len(transport._data) == 0

def test_user_handler_transport_failed(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Feed some data and complete the headers
    #
    request = b'''GET / HTTP/1.1
Host: example.com
Content-Length: 3

XXX'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # When we now call send on the coroutine to simulate that the event
    # loop reschedules it, it should invoke our handler function. Before
    # we do this, we tell the dummy transport to fail on write
    #
    transport.fail_next()
    coro.send(None)
    #
    # Make sure that the handler has been called
    #
    assert container._request is not None
    request = container._request
    #
    # Verify that we have not written anything into the transport
    #
    assert len(transport._data) == 0


#
# We now use HTTP 1.0 and verify that we get the same version back
# and do not use keep alive
#
def test_user_handler_http10(transport, container):

    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Feed some data 
    #
    request = b'''GET / HTTP/1.0
Host: example.com
Content-Length: 3

123'''
    protocol.data_received(request.replace(b'\n', b'\r\n'))
    #
    # Now the future should be completed
    #
    result = future.result()
    assert result is not None
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

    
def test_timeout_invalid_state(transport):
    loop = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None, loop=loop)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Get the coroutine handed over to the task 
        #
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Check that we have scheduled a timeout
    #
    loop.call_later.assert_called()
    _do_timeout = loop.call_later.call_args.args[1]
    #
    # Invoke the scheduled function - this should add an exception to the
    # future the coroutine is waiting for. But before doing this, set the 
    # future to complete to produce an InvalidStateError
    #
    future.set_result(1)
    _do_timeout()
    coro.close()
        


#
# Testcase: we receive message complete before the header is complete
#
def test_no_headers():
    protocol = aioweb.protocol.HttpProtocol(container=container)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        coro = mock.call_args.args[0]
    #
    # When we now start our coroutine, it should wait for the message
    # header, i.e. it should yield a Future
    #
    future = coro.send(None)
    assert isinstance(future, asyncio.Future)
    #
    # Instead of sending header, we now call message complete
    # directly. This should never happen, but we should handle
    # this gracefully
    #
    protocol.on_message_complete()
    #
    # Same thing for headers complete
    #
    protocol.on_headers_complete()
