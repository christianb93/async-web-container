import asyncio
import aioweb.container
import pytest
import requests
import threading
import time

class SimpleClient:

    def __init__(self):
        self._text = None
        self._status_code = None
        self._request_done = False

    def do_test(self):
        #
        # Give container some time to complete start up
        #
        time.sleep(0.5)
        #
        # run request
        #
        response = requests.get("http://127.0.0.1:8888")
        assert response is not None
        self._request_done = True
        self._text = response.text
        self._status_code =  response.status_code
        response.close()


@pytest.fixture
def test_client():
    simple_client = SimpleClient()
    t = threading.Thread(target=simple_client.do_test)
    t.daemon = True
    t.start()
    return simple_client

def test_container_creation():

    async def handler(request, container):
        return b"abc"

    container = aioweb.container.HttpToolsWebContainer(host="127.0.0.1", port="8888", handler=handler)

def test_create_exception():

    async def handler(request, container):
        return b"abc"

    container = aioweb.container.HttpToolsWebContainer(host="127.0.0.1", port="8888", handler=handler)
    exc = container.create_exception("blub")
    assert str(exc) == "blub"

@pytest.mark.asyncio
async def test_start_stop_container():

    async def handler(request, container):
        return b"abc"

    container = aioweb.container.HttpToolsWebContainer(host="127.0.0.1", port="8888", handler=handler)

    async def stop_container():
        await asyncio.sleep(1)
        container.stop()

    #
    # Schedule a timer which will stop the container in one second
    #
    await asyncio.gather(stop_container(), container.start())

@pytest.mark.asyncio
async def test_single_request(test_client):

    async def handler(request, container):
        return b"abcd"

    container = aioweb.container.HttpToolsWebContainer(host="127.0.0.1", port="8888", handler=handler)

    async def stop_container():
        while not test_client._request_done:
            await asyncio.sleep(1)
        container.stop()

    await asyncio.gather(stop_container(), container.start())
    #
    # Check response
    #
    assert test_client._request_done 
    assert test_client._status_code == 200
    assert test_client._text == "abcd"