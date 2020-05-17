"""
This module implements a protocol which can be used with asyncio and controls the
processing flow of a request
"""

import asyncio
import logging

import aioweb.container

logger = logging.Logger(__name__)

class HttpProtocol(asyncio.Protocol):

    """
    A protocol used by our container class. When a connection is made, this protocol
    creates a task which handles all requests processed through this connection and
    is cancelled if the connection is closed. The task will then wait on a future
    until the parser signals that a header is complete and then invoke the user
    supplied handler.
    """

    def __init__(self, container: aioweb.container.WebContainer,
                 loop=None, timeout_seconds: int = 5) -> None:
        if loop is None:
            loop = asyncio.get_event_loop()
        self._loop = loop
        self._transport = None
        self._future = None
        self._container = container
        self._current_task = None
        self._timeout_seconds = timeout_seconds
        self._timeout_handler = None

    def connection_made(self, transport):
        self._transport = transport
        logger.debug("Connection started, transport is %s", self._transport)
        #
        # Create a future that will be released by the parser when a new message header has arrived
        #
        self._future = asyncio.Future()
        #
        #
        # Schedule a task to handle all requests coming in via this connection
        #
        self._current_task = asyncio.create_task(self._handle_requests())
        #
        # Schedule a timer
        #
        logger.debug("Scheduling timeout")
        self._timeout_handler = self._loop.call_later(self._timeout_seconds, self._do_timeout)

    async def _handle_requests(self):
        pass

    #
    # This will be called by the event loop when a timeout is scheduled.
    #
    def _do_timeout(self):
        #
        # If the coroutine is waiting for a future, raise a timeout error
        #
        logger.debug("Timeout fired")
        if self._future is not None:
            try:
                self._future.set_exception(
                    asyncio.exceptions.TimeoutError("Timeout for connection reached"))
            except asyncio.exceptions.InvalidStateError:
                #
                # Future already done, ignore this
                #
                pass
