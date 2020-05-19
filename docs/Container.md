## Overview

The abstract base class *WebContainer* represents the actual container which is started by an application, receives requests and invokes a user defined handler. In the background, the container uses asyncio to spawn an asynchronous TCP server process and the protocol class which are part of this package to communicate with clients via HTTP.

## Running a container

To run a container, a typical server application needs to conduct the following steps.

* define a request handler, i.e. a native coroutine which receives a *aioweb.request.Request* instance and, as second positional argument, a reference to the container in which it is running, and returns a sequence of bytes which will be returned to the client as the body of a HTTP response
* create a container, specifying host, port and the handler
* start the container by invoking its *start* method

Note that the start method only returns in case of an unexpected error or if a different task invokes the *stop* method of the container. The *stop* method is threadsafe, all other methods are not threadsafe. 

## Handling requests

When a request is received, the protocol that we use does not directly invoke the handler registered with the container, but instead calls the public method *handle_request* of the container itself. This method is supposed to simply delegate the call to the registered handler, but can be overriden in subclasses to realize e.g. routing mechanisms where different handlers could be called depending on the request content. 

Inside a handler, exceptions should be handled by calling the *create_exception* method of the container and raising this exception. The type of this exception is not relevant for the handler, which makes it easier to plug in alternative implementations of the same interface.

