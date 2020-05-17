"""
This module contains the implementation of the actual web container which receives requests
and invokes a user specific handler.
"""

import abc
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

Handler = Callable[[aioweb.request.Request, WebContainer], Awaitable[bytes]]

class HttpToolsWebContainer(WebContainer):

    """
    An implementation of the abstract web container class
    """

    def __init__(self, host: str, port: str, handler: Handler) -> None:
        pass

    async def start(self):
        pass

    def stop(self):
        pass

    def create_exception(self, msg: str):
        return None
