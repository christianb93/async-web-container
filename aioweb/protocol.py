"""
This module implements a protocol which can be used with asyncio and controls the
processing flow of a request
"""

import asyncio
import logging
from enum import Enum

import httptools

import aioweb.container

logger = logging.Logger(__name__)

class ConnectionState(Enum):
    """
    This encodes the state of a connection.
    CLOSED - closed
    HEADER - we have received a first part of the header
    BODY - we have received the complete header
    PENDING - waiting for the next message
    """
    CLOSED = 0              # Closed
    HEADER = 1              # We have received a first part of the header
    BODY = 2                # We have received the complete header
    PENDING = 3             # Waiting for the next message



class HttpProtocol(asyncio.Protocol): # pylint: disable=too-many-instance-attributes

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
        self._parser = None
        self._state = ConnectionState.CLOSED
        self._headers = {}

    def connection_made(self, transport):
        """
        This callback is invoked by the transport when a connection is established. It creates a task
        which handles all future requests received via this connection
        """
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
        self._state = ConnectionState.PENDING

    def get_state(self):
        """
        Return the current state of the connection
        """
        return self._state

    async def _handle_requests(self):
        pass

    #
    # This will be called by the event loop when a timeout is scheduled.
    #
    def _do_timeout(self):
        #
        # If the coroutine is waiting for a future, throw a timeout error into
        # the future
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

    def connection_lost(self, exc):
        """
        This callback is invoked by the transport when the connection is lost
        """
        if exc:
            #
            # Either the peer closed the connection, or a protocol callback raised
            # an error and the transport closed the connection
            #
            logger.error("Connection closed with message %s", exc)
        logger.debug("Connection closed")
        self._transport = None
        if self._current_task is not None:
            #
            # Cancel the task. This will (in the next iteration of the loop) resume
            # the task which is most likely waiting for a new message body and
            # raise a CancelledError which we can pass to the event loop which will
            # then mark the task as cancelled. This also avoids an error message in
            # the tasks __del__ method during cleanup
            #
            self._current_task.cancel()
            self._current_task = None
        if self._timeout_handler is not None:
            logger.debug("Cancelling timeout handler")
            self._timeout_handler.cancel()
            self._timeout_handler = None
        self._state = ConnectionState.CLOSED

    def data_received(self, data: bytes):
        """
        This is called by the transport if new data arrives
        """
        #
        # If we do not yet have a parser, create one
        #
        if self._parser is None:
            self._parser = httptools.HttpRequestParser(self) # pylint: disable=no-member
        #
        # If we were pending before, i.e. this is the first piece of a new request,
        # advance the status
        #
        if self._state == ConnectionState.PENDING:
            self._state = ConnectionState.HEADER
        #
        # Feed data into parser, which might eventually trigger callbacks
        # or raise exceptions if the data is not valid
        #
        self._parser.feed_data(data)
        #
        # If we have a running timeout, reschedule it. This is not awfully
        # efficient, we could also let it expire and reschedule only then...
        #
        if self._timeout_handler is not None:
            logger.debug("Resetting timeout")
            self._timeout_handler.cancel()
            self._timeout_handler = self._loop.call_later(self._timeout_seconds, self._do_timeout)

    def on_message_complete(self):
        """
        This callback is invoked by the parser when the message is done.
        """
        #
        # Reset parser
        #
        self._parser = None
        self._state = ConnectionState.PENDING
        self._headers = {}

    def on_header(self, key, value):
        """
        Called by the parser when a header line is received, passing bytes
        """
        self._state = ConnectionState.HEADER
        if key is not None:
            key_str = key.decode("utf-8")
            if len(key_str) > 0:
                self._headers[key_str] = value

    def get_headers(self) -> dict:
        """
        Return the currently collected headers as a dictionary. The keys are built assuming
        UTF-8 encoding
        """
        return self._headers
