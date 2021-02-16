#!/usr/bin/env python3

from typing import Optional

import rospy

from wready import InitTask, WReadyServer, WReadyServerObserver
from wready.msg import InitProgress

def loginfo(log_msg: str):
    rospy.loginfo(f'WReady >> {log_msg}')

class RosOutObserver(WReadyServerObserver):
    def on_task_queued(self, task: InitTask):
        loginfo(f'Task queued: {task.name} ({task.slot_id})')

    def on_task_scheduled(self, task: InitTask):
        loginfo(f'Task scheduled: {task.name} ({task.slot_id})')

    def on_task_progress(self, task: InitTask, msg: InitProgress):
        loginfo(f'[{msg.completion * 100:.1f}%] {msg.message}')

    def on_task_done(self, task: InitTask):
        loginfo(f'Task completed: {task.name} ({task.slot_id})')

def main():
    rospy.init_node('wready_server')
    
    server_ns: Optional[str] = rospy.get_param('~server_ns', None)
    task_delay: int = rospy.get_param('~task_delay', 1000)
    enable_logging: bool = rospy.get_param('~enable_logging', True)

    server = WReadyServer(server_ns, RosOutObserver() if enable_logging else None)
    sleeper = rospy.Rate(1000 / task_delay)
    while not rospy.is_shutdown():
        server.next()
        sleeper.sleep()

if __name__ == '__main__':
    main()
