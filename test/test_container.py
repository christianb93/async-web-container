import asyncio
import aioweb.container
import pytest
import requests
import threading

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
async def test_single_request():

    async def handler(request, container):
        return b"abc"

    container = aioweb.container.HttpToolsWebContainer(host="127.0.0.1", port="8888", handler=handler)

    async def stop_container():
        await asyncio.sleep(2)
        container.stop()


    def do_test():
        #
        # Give container some time to complete start up
        #
        sleep(0.5)
        #
        # run request
        #
        response = requests.post("http://localhost:8888", data=b"111")
        assert response.status_code == 200
        assert response.text()=="abc"
        assert response.encoding == "utf-8"

    #
    # Start container and schedule actual test
    #
    thread = threading.Thread(target=do_test)
    thread.start()
    await asyncio.gather(container.start(), stop_container())
    thread.join()
