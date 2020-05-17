"""
This module contains classes describing a HTTP request received by the container.
"""

import abc
import asyncio


class Request: # pylint: disable=too-few-public-methods
    """
    This class represents a HTTP request received by the container
    """


    @abc.abstractmethod
    async def body(self) -> bytes:
        """
        Return the body of the request as a sequence of bytes
        """

    @abc.abstractmethod
    def headers(self) -> dict:
        """
        Return a dictionary containing the headers as a dictionary
        """


class HTTPToolsRequest(Request):
    """
    An implementation of the abstract Request class using the HttpTools library
    """

    def __init__(self, future: asyncio.Future, headers: dict = None) -> None:
        self._future = future
        self._headers = headers

    async def body(self) -> bytes:
        return await self._future

    def headers(self) -> dict:
        if self._headers is None:
            return {}
        return self._headers
    