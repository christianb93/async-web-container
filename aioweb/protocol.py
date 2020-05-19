"""
This module implements a protocol which can be used with asyncio and controls the
processing flow of a request
"""

import asyncio
import logging
from enum import Enum

import httptools

import aioweb.request
import aioweb.container
import aioweb.exceptions

logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    """
    This encodes the state of a connection.

    Possible values are:
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
    A protocol used by our container class.

    When a connection is made, this protocol creates a task which handles all requests
    processed through this connection and is cancelled if the connection is closed. The task
    will then wait until the header of the request has been parsed.

    Then, the handler attached to the container is invoked. This handler can either decide
    to wait for the request body or proceed. In any case, the handler is expected to return
    a sequence of bytes which will then be used as the body of the response.

    If the parser signals that a message is complete, the future embedded into the current
    request will be completed using the request body as a result.
    """

    __slots__ = ['_loop', '_transport', '_queue', '_container',
                 '_current_task', '_timeout_seconds', '_timeout_handler',
                 '_parser', '_state', '_headers', '_body_future', '_body']

    def __init__(self, container: aioweb.container.WebContainer,
                 loop=None, timeout_seconds: int = 5) -> None:
        if loop is None:
            loop = asyncio.get_event_loop()
        self._loop = loop
        self._transport = None
        self._container = container
        self._current_task = None
        self._timeout_seconds = timeout_seconds
        self._timeout_handler = None
        self._parser = None
        self._state = ConnectionState.CLOSED
        self._headers = {}
        self._body_future = None
        self._body = None
        self._queue = asyncio.Queue()

    def connection_made(self, transport):
        """
        Signal creation of a new connection.

        This callback is invoked by the transport when a connection is established. It
        creates a task which handles all future requests received via this connection
        and schedules a timeout. The state of the connection will be updated to PENDING
        """

        self._transport = transport
        logger.debug("Connection started, transport is %s", self._transport)
        #
        #
        # Schedule a task to handle all requests coming in via this connection
        #
        self._current_task = asyncio.create_task(self._worker_loop())
        #
        # Schedule a timer
        #
        logger.debug("Scheduling timeout")
        self._timeout_handler = self._loop.call_later(self._timeout_seconds, self._do_timeout)
        self._state = ConnectionState.PENDING

    def connection_lost(self, exc):
        """
        Signal that a connection has been closed.

        This callback is invoked by the transport when the connection is lost. Exceptions
        passed will be ignored. The current task will be cancelled, and the state of the
        connection will be set to closed. Any pending timeout handlers will be cancelled as
        well.
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
        self._queue = asyncio.Queue()
        self._state = ConnectionState.CLOSED

    def data_received(self, data: bytes):
        """
        Main entry point to hand over received data to the protocol.

        This is called by the transport if new data arrives. If the state of the connection
        is still pending, it will be set to HEADER. Then the data will be handed over to the
        parser which potentially invokes further callbacks.
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


    def get_state(self):
        """
        Return the current state of the connection
        """

        return self._state

    #
    # Helper method to invoke the container handler and create a response
    #
    async def _invoke_handler(self, request: aioweb.request.HTTPToolsRequest) -> bytes:
        assert isinstance(request, aioweb.request.HTTPToolsRequest)
        #
        # Asynchronously invoke container handler for this request
        #
        msg = None
        try:
            result = await self._container.handle_request(request)
        except aioweb.exceptions.HTTPException as exc:
            msg = "Internal server error, message is %s" % exc
        except BaseException as exc: # pylint: disable=broad-except
            msg = "Unknown exception (type=%s, msg=%s) caught" % (type(exc), exc)

        #
        # If we got an exception, log it and replace result by error message
        #
        if msg is not None:
            logger.error("Have message %s from previous error", msg)
            result = bytes(msg, "utf-8")
            status_code = 500
        else:
            status_code = 200

        http_version = request.http_version()

        content_length = len(result)
        response_bytes = b''.join([
            bytes("HTTP/%s %s OK\r\n" % (http_version, status_code), "utf-8"),
            b'Content-Type: text/plain; charset=utf-8\r\n',
            bytes("Content-Length: %d\r\n" % content_length, "utf-8"),
            b'\r\n',
            result
            ])
        return response_bytes

    async def _worker_loop(self):
        #
        # This loop needs to run for the entire
        # duration of the connection
        #
        while True:
            #
            # Wait for the next request in the queue
            #
            try:
                request = await self._queue.get()
                #
                # Invoke container handler and prepare response
                #
                response_bytes = await self._invoke_handler(request)
                logger.debug("Writing %s", response_bytes.decode("utf-8"))
            except asyncio.exceptions.CancelledError:
                #
                # If the connection has been closed in the meantime (before we get scheduled again),
                # the connection_list will have cancelled the tasks - raise it again so that the
                # event loop marks the task as cancelled
                #
                raise asyncio.exceptions.CancelledError("Coroutine cancelled")
            #
            # Deliver response
            #
            if self._transport.is_closing():
                logger.error("Cannot write into closing transport")
                return
            try:
                self._transport.write(response_bytes)
                #
                # Close transport if needed
                #
                if not request.keep_alive():
                    self._transport.close()
            except BaseException as exc: # pylint: disable=broad-except
                logger.error("Got unexpected error (type=%s, msg=%s", type(exc), exc)



    #
    # This will be called by the event loop when a timeout is scheduled.
    #
    def _do_timeout(self):
        #
        # We set the current task to cancelled so that resuming the task will result
        # in a CancelledError being raised
        #
        logger.debug("Timeout fired")
        if self._current_task is not None:
            self._current_task.cancel("Task timed out")



    def on_message_complete(self):
        """
        Signal completion of a message.

        This callback is invoked by the parser when the message is done. It resets the connection
        state and completes the request future on which the main handler loop might be waiting,
        adding the request body as the result of the future
        """

        #
        # Reset parser
        #
        self._parser = None
        self._state = ConnectionState.PENDING
        self._headers = {}
        #
        # Complete the future representing the full body of the
        # currently parsed message
        #
        if self._body_future is None:
            logger.error("Could not locate valid future for body completion")
        else:
            if self._body is None:
                self._body_future.set_result(b"")
            else:
                self._body_future.set_result(self._body)
        #
        # Reset body and parser
        #
        self._body = None
        self._parser = None
        self._body_future = None


    def on_header(self, key, value):
        """
        Signal a new HTTP request header.

        Called by the parser when a header line is received, passing bytes. This method
        simply adds the received header to an internal dictionary of detected headers
        """

        self._state = ConnectionState.HEADER
        if key is not None:
            key_str = key.decode("utf-8")
            if len(key_str) > 0:
                self._headers[key_str] = value

    def on_body(self, data):
        """
        Receive a part of a HTTP request body.

        This method is called by the parser when a piece of the body comes in
        We simply append the body part to the existing body data
        """

        if self._body is None:
            self._body = bytearray()
        self._body.extend(data)


    def get_headers(self) -> dict:
        """
        Get all collected HTTP request headers.

        This returns the currently collected headers as a dictionary. The keys are built assuming
        UTF-8 encoding
        """

        return self._headers

    def on_headers_complete(self):
        """
        Signal completion of a HTTP request header.

        This is called by the parser when the headers are complete. Here we complete the future
        on which the handler task is currently waiting, using a HTTPRequest object as the result.
        The state of the connection will be advanced to BODY.
        """

        logger.debug("Header complete")
        #
        # Build a request object and release handler task to
        # signal that a new header has arrived
        #
        self._body_future = asyncio.Future()
        request = aioweb.request.HTTPToolsRequest(future=self._body_future,
                                                  headers=self.get_headers(),
                                                  http_version=self._parser.get_http_version(),
                                                  keep_alive=self._parser.should_keep_alive())
        self._queue.put_nowait(request)
        self._state = ConnectionState.BODY
