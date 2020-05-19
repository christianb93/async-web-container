import asyncio

import pytest
import unittest.mock 

import aioweb.protocol

#############################################################
# Dummy classes
#############################################################

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



@pytest.fixture
def transport():
    return DummyTransport()


#
# Test creation of a protocol. The initial state of the protocol should be 
# CLOSED
#
def test_protocol_creation():

    protocol = aioweb.protocol.HttpProtocol(container=None, loop=unittest.mock.Mock())
    assert isinstance(protocol, asyncio.Protocol)
    assert protocol.get_state() == aioweb.protocol.ConnectionState.CLOSED

#
# Test the connection_made callback
#
def test_connection_made(transport):
    loop = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None, loop=loop)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Now verify that we have created an additional task
        #
        mock.assert_called_once()
        #
        # get the coroutine and clean it up to avoid warnings
        #
        coro = mock.call_args.args[0]
        coro.close()
    #
    # check the state
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING
    #
    # Check that we have scheduled a timeout
    #
    loop.call_later.assert_called()
    _do_timeout = loop.call_later.call_args.args[1]

#
# Test the connection_lost callback
#
def test_connection_lost(transport):
    loop = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None, loop=loop)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Get the coroutine handed over to the task and properly 
        # close it
        #
        coro = mock.call_args.args[0]
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
    #
    # Retrieve the timeout handler from the loop mock
    # and verify that is has been cancelled as well
    #
    timeout_handler = loop.call_later()
    timeout_handler.cancel.assert_called()
        
#
# Test the case that the connection closes with an exception.
#
def test_connection_lost_exc(transport):
    loop = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None, loop=loop, timeout_seconds = 3)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Get the coroutine handed over to the task and properly 
        # close it
        #
        coro = mock.call_args.args[0]
        coro.close()
        #
        # Check that we have scheduled a timeout
        #
        loop.call_later.assert_called()
        timeout_seconds = loop.call_later.call_args.args[0]
        assert 3 == timeout_seconds
        timeout_handler = loop.call_later.return_value
        #
        # Get the task that we returned
        #
        mocked_task = mock()
    #
    # Now call connection_lost, and pass an exception
    #
    protocol.connection_lost(exc=BaseException())
    #
    # this should have called cancel() on the task
    #
    mocked_task.cancel.assert_called()
    #
    # and should have cancelled the timeout
    #
    timeout_handler.cancel.assert_called()
    #
    # The state should be CLOSED again
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.CLOSED

#
# Test the data received callback - first call. We verify that the data is
# passed to the parser and that the previous timeout has been cancelled
#
def test_data_received_first(transport):
    loop = unittest.mock.Mock()
    protocol = aioweb.protocol.HttpProtocol(container=None, loop=loop)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
        #
        # Check that we have scheduled a timeout
        #
        loop.call_later.assert_called()
        timeout_handler = loop.call_later.return_value
        timeout_seconds = loop.call_later.call_args.args[0]
        timeout_method = loop.call_later.call_args.args[1]
        coro = mock.call_args.args[0]
        coro.close()
    #
    # Feed some data. Here we only feed the first line, i.e. the message is not complete
    # and there are no headers yet
    #
    request = b'GET / HTTP/1.1'
    with unittest.mock.patch("aioweb.protocol.httptools.HttpRequestParser") as mock:
        protocol.data_received(request)
        #
        # Get the parser mock and verify that we did call feed_data
        #
        parser = mock.return_value
    parser.feed_data.assert_called()
    #
    # check that the data passed is our request and that the state of the
    # connection has changed
    #
    assert parser.feed_data.call_args.args[0] == request
    assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER
    #
    # Verify that we have cancelled the timeout
    #
    timeout_handler.cancel.assert_called()
    #
    # and a new timeout has been created, using the same arguments as
    # for the first timeout
    #
    assert loop.call_later.call_count == 2
    assert timeout_seconds == loop.call_later.call_args.args[0]
    assert timeout_method == loop.call_later.call_args.args[1]


#
# Test the data received callback - second call
#
def test_data_received_second(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    with unittest.mock.patch("asyncio.create_task") as mock:
        protocol.connection_made(transport)
    #
    # Feed some data. Here we only feed the first line, i.e. the message is not complete
    # and there are no headers yet
    #
    request = b'GET /'
    with unittest.mock.patch("aioweb.protocol.httptools.HttpRequestParser") as mock:
        protocol.data_received(request)
        #
        # Get the parser mock and verify that we did call feed_data
        #
        parser = mock.return_value
        parser.feed_data.assert_called()
        #
        # check that the data passed is our request and that the state of the
        # connection has changed
        #
        assert parser.feed_data.call_args.args[0] == request
        assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER
        #
        # Now do the second call
        #
        protocol.data_received(b' HTTP/1.1')
        parser.feed_data.assert_called()
        assert parser.feed_data.call_args.args[0] == b' HTTP/1.1'
        assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER
        