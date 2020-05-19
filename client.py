import asyncio 
import aiohttp 
import datetime
import argparse
import random

import uvloop

async def make_request(session, id, port):
    try:
        async with session.get('http://localhost:%s' % port) as resp:
            if resp.status != 200:
                print("Server error --%s-- returned for request %d" % (await resp.text(), id))
    except BaseException as e:
        print("Received error %s for message with id %d" % (e, id))


async def main(tasks, ports, pool_size=1000):
    #
    # Read ports - we use the full list in a round-robin fashion
    #
    ports = ports.split(",")
    #
    # Prepare list of coroutines in advance
    #
    conn = aiohttp.TCPConnector(limit=pool_size)
    async with aiohttp.ClientSession(connector=conn) as session:
        coros = [make_request(session, i, random.choice(ports)) for i in range(tasks)]
        started_at=datetime.datetime.now()
        print("Start time: ", "{:%H:%M:%S:%f}".format(started_at))
        await asyncio.gather(*coros)
        ended_at=datetime.datetime.now()
        print("End time:   ", "{:%H:%M:%S:%f}".format(ended_at))
        duration = ended_at - started_at 
        return duration



#
# Parse arguments
#
parser = argparse.ArgumentParser()
parser.add_argument("--tasks", 
                    type=int,
                    default=1,
                    help="Number of tasks to spawn")
parser.add_argument("--pool_size", 
                    type=int,
                    default=500,
                    help="Size of connection pool")
parser.add_argument("--ports", 
                    type=str,
                    default="8888",
                    help="A comma-separated lists of ports to connect to")
args=parser.parse_args()

uvloop.install()

duration = asyncio.run(main(args.tasks, args.ports, args.pool_size))
seconds = duration.seconds + (duration.microseconds / 1000000)
if seconds > 0:
    per_second = args.tasks / seconds
else:
    per_second = args.tasks
print("Completed %d requests in %d.%d seconds (%d per second)" % (args.tasks, duration.seconds, duration.microseconds, int(per_second)))