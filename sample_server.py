"""
A simple server using the aioweb library
"""


import signal
import asyncio
import functools
import argparse
import logging

import uvloop

import aioweb.container
import aioweb.protocol


async def handler(request, container):
    """
    This is the handler that will be executed for every request
    """
    body = await request.body()
    return body

def handle_signal(container, signal, frame):
    container.stop()

async def main():
    #
    # Create container
    #
    container = aioweb.container.HttpToolsWebContainer(host="127.0.0.1", port="8888", handler=handler)
    #
    # Register signal handler
    #
    signal.signal(signal.SIGINT, functools.partial(handle_signal, container))
    await container.start()

#
# Parse arguments
#
parser = argparse.ArgumentParser()
parser.add_argument("--debug", 
                    action="store_true",
                    default=False,
                    help="Turn on debugging mode")
parser.add_argument("--uvloop", 
                    action="store_true",
                    default=False,
                    help="Use uvloop")
args=parser.parse_args()

#
# Set up logging
#
logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d:%H:%M:%S',level=logging.ERROR)
if args.debug:
    logging.getLogger("aioweb").setLevel(logging.DEBUG)

#
# Install event loop    
#
if args.uvloop:
    uvloop.install()

#
# Run event loop
#
asyncio.run(main())
