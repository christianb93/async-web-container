"""
This module contains the implementation of the actual web container which receives requests
and invokes a user specific handler.
"""

import abc


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
    of the container and raises it, which will  return an error 500.
    """

    def __init__(self, host, port, handler):
        pass

    @abc.abstractmethod
    async def start(self):
        """
        Start the container, i.e. start listening for requests.
        """

    @abc.abstractmethod
    def create_exception(self, msg):
        """
        Create an exception, using the string msg as message
        """

    @abc.abstractmethod
    def stop(self):
        """
        Stop the container.
        """
