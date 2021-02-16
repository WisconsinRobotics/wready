#!/usr/bin/env python3

import time

import rospy

from wready import WReadyClient
from wready.wready_client import TaskContext

def sim_work(ctx: TaskContext):
    ctx.report_progress('Doing things...', 0)
    time.sleep(1)
    ctx.report_progress('Doing stuff...', 1 / 3)
    time.sleep(1)
    ctx.report_progress('Almost done...', 2 / 3)
    time.sleep(1)

def main():
    rospy.init_node('wready_test_client', anonymous=True)
    
    name: str = rospy.get_param('~name', 'Test Client')
    server_ns: str = rospy.get_param('~server_ns', '/wready_server')

    client = WReadyClient(server_ns)
    client.request_async(f'{name}: Asynchronous', sim_work)
    with client.request_sync(f'{name}: Synchronous') as ctx:
        sim_work(ctx)
    client.wait()

if __name__ == '__main__':
    main()
