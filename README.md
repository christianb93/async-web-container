# async-web-container


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

