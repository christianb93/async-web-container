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

@pytest.mark.asyncio
async def test_connection_made(transport):
    protocol = aioweb.protocol.HttpProtocol(container=None)
    task_count = len(asyncio.all_tasks())
    protocol.connection_made(transport)
    #
    # Now verify that we have created an additional task
    #
    assert len(asyncio.all_tasks()) == (task_count + 1)

@pytest.mark.asyncio
async def test_connection_list(transport):
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