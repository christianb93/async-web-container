import asyncio

import pytest

import aioweb.protocol

@pytest.fixture
def loop():
    return asyncio.get_event_loop()

def test_protocol_creation(loop):

    protocol = aioweb.protocol.HttpProtocol(container=None, loop=loop)

