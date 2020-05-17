import asyncio

import pytest

import aioweb.protocol

class DummyTransport:

    def __init__(self):
        pass


@pytest.fixture
def transport():
    return DummyTransport()

def test_protocol_creation(event_loop):

    protocol = aioweb.protocol.HttpProtocol(container=None, loop=event_loop)
    assert isinstance(protocol, asyncio.Protocol)
    assert protocol.get_state() == aioweb.protocol.ConnectionState.CLOSED

@pytest.mark.asyncio
async def test_connection_made(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    task_count = len(asyncio.all_tasks())
    protocol.connection_made(transport)
    #
    # Now verify that we have created an additional task
    #
    assert len(asyncio.all_tasks()) == (task_count + 1)
    #
    # and check the state
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.PENDING

@pytest.mark.asyncio
async def test_connection_lost(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    task_count = len(asyncio.all_tasks())
    protocol.connection_made(transport)
    #
    # Now verify that we have created an additional task
    #
    assert len(asyncio.all_tasks()) == (task_count + 1)   
    #
    # Call connection_lost
    #
    protocol.connection_lost(exc=None)
    #
    # Now we iterate through the tasks and check
    # whether cancelled was called on exactly one
    # of them. WARNING: this will break if later versions
    # of asyncio drop the _must_cancel field in the task
    #
    cancelling = 0
    for task in asyncio.all_tasks():
        if task._must_cancel:
            cancelling +=1
    assert cancelling == 1
    #
    # and check the state
    #
    assert protocol.get_state() == aioweb.protocol.ConnectionState.CLOSED    

@pytest.mark.asyncio
async def test_data_received(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    protocol.connection_made(transport)
    #
    # Feed some data. Here we only feed the first line, i.e. the message is not complete
    # and there are no headers yet
    #
    request = b'GET / HTTP/1.1'
    protocol.data_received(request)
    assert protocol.get_state() == aioweb.protocol.ConnectionState.HEADER

@pytest.mark.asyncio
async def test_header_received(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
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