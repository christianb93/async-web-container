"""
This module implements a protocol which can be used with asyncio and controls the
processing flow of a request
"""

import asyncio
import logging
from enum import Enum

import httptools

import aioweb.container
import aioweb.request
import aioweb.exceptions

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

    __slots__ = ['_loop', '_transport', '_future', '_container',
                 '_current_task', '_timeout_seconds', '_timeout_handler',
                 '_parser', '_state', '_headers', '_request_future', '_body']

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
        self._request_future = None
        self._body = None

    def connection_made(self, transport):
        """
        This callback is invoked by the transport when a connection is established. It
        creates a task which handles all future requests received via this connection
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
        #
        # This handler needs to remain open for the entire
        # duration of the connection
        #
        while True:
            #
            # Wait until the header is complete
            #
            try:
                request = await self._future
            except asyncio.exceptions.CancelledError:
                #
                # If the connection has been closed in the meantime (before we get scheduled again),
                # the connection_list will have cancelled the tasks - raise it again so that the
                # event loop marks the task as cancelled
                #
                raise asyncio.exceptions.CancelledError("Coroutine cancelled")
            except asyncio.exceptions.TimeoutError:
                #
                # If we got a timeout error, close the connection and raise a CancelledError
                # so that the event loop will mark the task as cancelled and not schedule it again
                #
                if self._transport is not None:
                    self._transport.close()
                raise asyncio.exceptions.CancelledError("Timeout received")
            except BaseException as exc:
                logger.error("Waiting for future resulted in error (type=%s, msg=%s)",
                             type(exc), exc)
                raise
            #
            # Renew future for next request
            #
            self._future = asyncio.Future()
            #
            # Asynchronously invoke container handler for this request
            #
            msg = None
            try:
                response = await self._container.handle_request(request)
            except aioweb.exceptions.HTTPException:
                msg = "Handler raised exception"
            except asyncio.exceptions.CancelledError:
                msg = "Task was cancelled, ignoring"
            except asyncio.exceptions.TimeoutError:
                msg = "Request timed out"
            except BaseException as exc: # pylint: disable=broad-except
                msg = "Unknown exception (type=%s, msg=%s) caught" % (type(exc), exc)

            if msg is not None:
                logger.error("Have message %s from previous error", msg)
                response = bytes(msg, "utf-8")

            print(response)
        return


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
        self._future = None
        #
        # Place the current body in the request future
        #
        if self._request_future is None:
            logger.error("Could not locate valid future for body completion")
        else:
            if self._body is None:
                self._request_future.set_result(b"")
            else:
                self._request_future.set_result(self._body)
        #
        # Reset body and parser
        #
        self._body = None
        self._parser = None
        self._request_future = None


    def on_header(self, key, value):
        """
        Called by the parser when a header line is received, passing bytes
        """
        self._state = ConnectionState.HEADER
        if key is not None:
            key_str = key.decode("utf-8")
            if len(key_str) > 0:
                self._headers[key_str] = value

    def on_body(self, data):
        """
        This method is called by the parser when a piece of the body comes in
        We simply append the body part to the existing body data
        """
        if self._body is None:
            self._body = bytearray()
        self._body.extend(data)


    def get_headers(self) -> dict:
        """
        Return the currently collected headers as a dictionary. The keys are built assuming
        UTF-8 encoding
        """
        return self._headers

    def on_headers_complete(self):
        """
        This is called by the parser when the headers are complete. Here we complete the future
        on which the handler task is currently waiting
        """
        logger.debug("Header complete")
        #
        # Build a request object and release handler task to
        # signal that a new header has arrived
        #
        if self._future:
            self._request_future = asyncio.Future()
            request = aioweb.request.HTTPToolsRequest(self._request_future, self.get_headers())
            self._future.set_result(request)
        else:
            logger.error("Could not find future for completed header")
        self._state = ConnectionState.BODY
