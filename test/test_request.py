import aioweb.request
import asyncio
import pytest

@pytest.fixture
def future():
    return asyncio.Future()

def test_create_request(future):

    request = aioweb.request.HTTPToolsRequest(future)
    assert isinstance(request, aioweb.request.Request)


def test_get_headers(future):

    request = aioweb.request.HTTPToolsRequest(future)
    headers = request.headers()
    assert headers is not None

def test_get_http_version(future):

    request = aioweb.request.HTTPToolsRequest(future)
    version = request.http_version()
    assert version == "1.1"

    request = aioweb.request.HTTPToolsRequest(future, http_version="1.0")
    version = request.http_version()
    assert version == "1.0"
