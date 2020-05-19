# async-web-container ![Build status](https://api.travis-ci.org/christianb93/async-web-container.svg?branch=master)


This repository contains a simple asynchronous web container using Pythons asyncio library. I wrote this to better understand the programming model behind the asyncio library, and this code is far from being ready for any production use, but still I decided to put this repository online as it might help other trying to understand asynchronous programming with Python.

The repository contains a set of abstract base classes and an implementation based on the HTTP parser library [httptools](https://github.com/MagicStack/httptools) provided by the folks at MagicStack and adds the logic around this parser to schedule and manage request handlers. 

## Linting and unit tests

We use type hints as defined in [PEP 484](https://www.python.org/dev/peps/pep-0484/). To run linting, make sure that you have pylint installed (`pip3 install pylint`) and then run

```
pylint aioweb
```

from the top level directory of the repository. For unit tests, we use the Python pytest module. All unit tests are in the *test* directory and can be run by executing

```
python3 -m pytest
```

To run linting and tests, you can also use the included Makefile and do `make` or `make all`. 

## Running and testing the sample server

This repository contains a sample server which you can run to test the library by executing `python3 sample_server.py`. By default, the server uses the asyncio event loop, but can also be run using the alternative uvloop, simply add the switch *--uvloop* when starting the server.

The reason why you might want to use an asynchronous server is that it is fast. To see how fast we can get, I have added a simple test client in Go which fires off a given number of requests per threads with a given number of threads (10). To create 100.000 requests, i.e. 10.000 requests per threads, simply run (assuming of course that you have a working Go environment)

```
go run client.go --threads=10 --requests=10000
```

On my PC, this took only a bit more than 4 seconds, so that we achieve a rate of more than 20.000 requests per second. The Python client which is also included is much slower, but, if run in several instances, is still able to make roughly 8000 - 10000 requests per second on the same machine.

## Limitations

The HTTP container in this repository is far from completed, and important features that a mature container would have are missing. Just to list a few of them:

* compressed content is not supported
* chunked transfer encoding is not supported
* we only support HTTP 1.0 and HTTP 1.1
* when using HTTP 1.0, keep-alive is not supported
* a *aioweb.request.Requests* contains only a subset of what you might want to see, there is for instance no easy way to retriev method and URL (though this would be easy to add)
* no HTTP conformance testing has been done

