## Overview

The class *aioweb.protocol.HttpProtocol* implements a protocol compatible with the asyncio protocol/transport logic. Processing within this class happens in three different modes.

First, there are callbacks triggered by the asyncio transport. These callbacks handle the connection state (*connection_made*, *connection_lost*) and process data received via the transport (*data_received*).

Data received is handed over to the HTTP parser. The parser then invokes a second calls of callbacks, namely callbacks that signal a certain event in the parsing stream, like completion of a header, receipt of a body part or completion of a request. 

Finally, there is the **worker loop* which is a native coroutine running inside an asyncio task. This worker loop is responsible for receiving the data produced by the HTTP parser callbacks and eventually invoking a user defined request handler which produces the HTTP response.

## Connection lifecycle

The worker loop is running inside a task which shares the lifecycle of the connection. Thus, if a connection is made, a task is created using *asyncio.create_task* running the worker loop. At the same time, a timeout is established by adding a timeout handler to the event loop. 

When the connection is closed by the transport, the transport will invoke *connection_lost*. Here, we cancel the task and the timeout again and reset the entire state of the connection. Any exceptions signaled by the transport will be ignored.

As data arrives, the transport will invoke the *data_received* callback. In this method, we first create a new HTTP parser (*httptools.HttpRequestParser*) if it does not yet exist. We then feed the data into the parser which might trigger additional callbacks. If the state of the connection is still PENDING, it is set to HEADER to indicate that processing of the header has started.

In addition, the *data_received* handler is responsible for managing the timeout. Specifically, it will cancel the existing timeout and add a new timeout handler, using the same parameters (timeout in seconds, method to be invoked) as before.

## Timeouts

To make sure that connections are closed if a client is idle for too long, we use a timeout handler. The timeouot is initially set when the connection is made and reset to its original value whenever data is received. When the timer expires, the current task is cancelled. This will raise a *asyncio.exceptions.CancelledError* in case the task is waiting for a future which needs to be caught and re-raised so that the event loop will not schedule the task again.

## The parser callbacks 

While a HTTP request is being processed, the HTTP parser will invoke additional callbacks on our protocol. The first callback which is invoked is *on_header*. This callback simply retrieves the header name and header value and stores it in a dictionary from where it can be retrieved using *get_headers*. Values will be added as bytes. The state of the connection will be set to HEADER.

When the entire header has been processed, the parser will run the *on_headers_complete* callback. This will set the connection state to BODY. In addition, it will create a Request object and add this object to an internal queue from which the worker thread will retrieve it later.

Note that the request object contains a future which will later be used to signal completion of the body. As there can always be at most one body in progress, we do not need a queue to store these futures, but simply keep a reference to the last "body future" as an internal variable.

The *on_body* callback is simple, it just stores the bytes that have been retrieved in an internal byte array. Finally, the *on_message_complete* callback handles the end of a message. This callback completes the current "body future" and sets the state of the connection back to PENDING.

## The worker loop

The worker loop is started as a task when a connection is established and continues to run until the connection is complete. Within the loop, we get the requests stored by *on_header_complete* from the queue asynchronously. For every request, we then invoke the handler registered with the container, format a HTTP response and write this response back into the transport.

Note that the request passed into the handler contains the future which *on_message_complete* will complete when the body has arrived. Thus, the handler can use the *body* method of the request object to wait for the body to be parsed.

The following expected errors are handled during the processing:

* if a CancelledError is raised while we are awaiting a coroutine, we raise the error again to the event loop
* if the transport is already closing when we try to write back the response, we simply ignore this error and return from the loop
* all other error that occur while writing to the transport are ignored
* if the handler raises an exception, a message with status code 500 is returned


