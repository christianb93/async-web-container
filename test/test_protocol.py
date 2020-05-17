import asyncio
import warnings

import pytest
import unittest.mock 


import aioweb.protocol

class DummyTransport:

    def __init__(self):
        pass

class DummyContainer:

    def __init__(self):
        self._request = None 
        self._handle_request_called = False

    async def handle_request(self, request):
        self._request = request
        self._handle_request_called = True 
        return b"abc"

@pytest.fixture
def transport():
    return DummyTransport()

@pytest.fixture
def container():
    return DummyContainer()


def test_protocol_creation(event_loop):

    protocol = aioweb.protocol.HttpProtocol(container=None, loop=event_loop)
    assert isinstance(protocol, asyncio.Protocol)
    assert protocol.get_state() == aioweb.protocol.ConnectionState.CLOSED

def test_connection_made(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Now verify that we have created an additional task
        #
        mock.assert_called_once()
    #
    # and check the state
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING


def test_connection_lost(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Get the coroutine handed over to the task and properly 
        # close it
        #
        coro = mock.call_args.args[0]
        print(coro)
        coro.close()
        #
        # Get the task that we returned
        #
        mocked_task = mock()
        #
        # Now call connection_lost 
        #
        protocol.connection_lost(exc=None)
        #
        # this should have called cancel() on the task
        #
        mocked_task.cancel.assert_called()


def test_data_received(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
    #
    # Feed some data. Here we only feed the first line, i.e. the message is not complete
    # and there are no headers yet
    #
    request = b'GET / HTTP/1.1'
    protocol.data_received(request)
    assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER

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
    #
    # Now try to wait for the body
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
