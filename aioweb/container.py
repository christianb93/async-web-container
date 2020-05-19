"""
This module contains the implementation of the actual web container which receives requests
and invokes a user specific handler.
"""

import abc
import asyncio
from typing import Callable, Awaitable


import aioweb.request

class WebContainer:
    """
    An abstract base class for a simple web container, based on the asyncio library.

    The container will accept incoming HTTP requests and, for each request, asynchronously invoke a
    user-specified handler as a separate task running inside the asyncio event loop.

    A handler is a coroutine with the following signature:

    async def handler(request, container)

    Here, the first argument is the request (i.e. an instance of Request). The second argument is
    a reference to the container in which the handler executes. A handler can now do one of the
    following things. Either it returns a sequence of bytes, which will then be sent back as
    response with status code 200, or it creates an exception using the method create_exception
    of the container and raises it, which will return an error 500.
    """

    @abc.abstractmethod
    async def start(self):
        """
        Start the container, i.e. start listening for requests.
        """

    @abc.abstractmethod
    def create_exception(self, msg: str):
        """
        Create an exception, using the string msg as message
        """

    @abc.abstractmethod
    def stop(self):
        """
        Stop the container.
        """

    @abc.abstractmethod
    async def handle_request(self, request: aioweb.request.Request):
        """
        Handle a single request. This method will usually delegate to the
        user provided handler
        """

Handler = Callable[[aioweb.request.Request, WebContainer], Awaitable[bytes]]

class HttpToolsWebContainer(WebContainer):

    """
    An implementation of the abstract web container class
    """

    __slots__ = ['_host', '_port', '_handler',
                 '_stop', '_server']

    def __init__(self, host: str, port: str, handler: Handler) -> None:
        self._host = host
        self._port = port
        self._handler = handler
        self._stop = False
        self._server = False

    async def start(self):
        loop = asyncio.get_running_loop()
        self._server = await loop.create_server(lambda: aioweb.protocol.HttpProtocol(self),
                                                host=self._host,
                                                port=self._port)
        await self._server.start_serving()
        while not self._stop:
            await asyncio.sleep(1)
        self._server.close()
        await self._server.wait_closed()

    def stop(self):
        self._stop = True

    def create_exception(self, msg: str):
        return aioweb.exceptions.HTTPException(msg)

    async def handle_request(self, request: aioweb.request.Request):
        result = await self._handler(request, self)
        return result
