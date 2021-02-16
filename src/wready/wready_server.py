from abc import ABC
from collections import deque
from threading import Condition, Lock
from time import sleep
from typing import Deque, Optional

import rospy
from std_msgs.msg import Empty

from wready.msg import InitNotify, InitProgress
from wready.srv import InitRequest, InitRequestRequest, InitRequestResponse

class InitTask:
    def __init__(self, name: str, notify_topic: str, slot_id: int):
        self.name = name
        self.notify_topic = notify_topic
        self.slot_id = slot_id

class WReadyServerObserver(ABC):
    def on_task_queued(self, task: InitTask):
        pass
    
    def on_task_scheduled(self, task: InitTask):
        pass

    def on_task_progress(self, task: InitTask, msg: InitProgress):
        pass

    def on_task_done(self, task: InitTask):
        pass

class WReadyServer:
    def __init__(self, server_ns: Optional[str] = None, observer: Optional[WReadyServerObserver] = None):
        namespace = '~' if server_ns is None else f'{server_ns}/'
        self._srv_req = rospy.Service(f'{namespace}request', InitRequest, self._on_request_req)
        self._sub_progress = rospy.Subscriber(f'{namespace}progress', InitProgress, self._on_progress_msg)
        self._sub_done = rospy.Subscriber(f'{namespace}done', Empty, self._on_done_msg)
        self._last_task_id = -1
        self._req_queue: Deque[InitTask] = deque()
        self._current_task: Optional[InitTask] = None
        self._task_lock = Lock()
        self._task_cond = Condition(self._task_lock)
        self.observer = observer
    
    def _next_task_id(self) -> int:
        self._last_task_id += 1
        return self._last_task_id

    def _on_request_req(self, req: InitRequestRequest) -> InitRequestResponse:
        task = InitTask(req.name, req.topic, self._next_task_id())
        self._req_queue.append(task)
        if self.observer:
            self.observer.on_task_queued(task)
        return InitRequestResponse(task.slot_id)

    def _on_progress_msg(self, msg: InitProgress):
        if self._current_task is None:
            rospy.logwarn('Init task progress received while no task is scheduled!')
        elif self.observer:
            self.observer.on_task_progress(self._current_task, msg)

    def _on_done_msg(self, msg: Empty):
        if self._current_task is None:
            rospy.logwarn('Init task done received while no task is scheduled!')
        else:
            if self.observer:
                self.observer.on_task_done(self._current_task)
            self._current_task = None
            with self._task_lock:
                self._task_cond.notify_all()

    def next(self) -> bool:
        if len(self._req_queue) == 0:
            return False
        task = self._req_queue.popleft()
        self._current_task = task
        if self.observer:
            self.observer.on_task_scheduled(task)
        notify_pub = rospy.Publisher(task.notify_topic, InitNotify, latch=True, queue_size=1)
        try:
            notify_pub.publish(InitNotify(task.slot_id))
            with self._task_lock:
                self._task_cond.wait_for(lambda: self._current_task is None)
        finally:
            notify_pub.unregister() # FIXME console spammed with warnings https://github.com/RobotWebTools/rosbridge_suite/issues/249
        return True

    def kill(self):
        with self._task_lock: # free any blocked threads
            self._task_cond.notify_all()
        self._srv_req.shutdown()
        self._sub_progress.unregister()
        self._sub_done.unregister()
