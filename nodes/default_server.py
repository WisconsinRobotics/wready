#!/usr/bin/env python3

from typing import Optional

import rospy

from wready import InitTask, WReadyServer, WReadyServerObserver
from wready.srv import InitProgressRequest

def loginfo(log_msg: str):
    """Writes a message to rosout prefixed with "WReady".

    Parameters
    ----------
    log_msg : str
        The message to log.
    """
    rospy.loginfo(f'WReady >> {log_msg}')

class RosOutObserver(WReadyServerObserver):
    """A simple WReady server observer that logs events to rosout."""
    
    def on_task_queued(self, task: InitTask):
        loginfo(f'Task queued: {task.name} ({task.slot_id})')

    def on_task_scheduled(self, task: InitTask):
        loginfo(f'Task scheduled: {task.name} ({task.slot_id})')

    def on_task_progress(self, task: InitTask, update: InitProgressRequest):
        loginfo(f'[{update.completion * 100:.1f}%] {update.message}')

    def on_task_done(self, task: InitTask):
        loginfo(f'Task completed: {task.name} ({task.slot_id})')

def main():
    """A simple WReady server that logs events to rosout.

    Various ROS params are accepted in the node's private namespace,
    which are listed below.

    Other Parameters
    ----------------
    server_ns : str, optional
        The ROS namespace for the server. Defaults to the node's
        private namespace.
    task_delay : int, optional
        The minimum delay between scheduled tasks, in milliseconds.
        Defaults to 1 second.
    enable_logging: bool, optional
        Enables or disables rosout logging. Defaults to enabled.
    """
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
