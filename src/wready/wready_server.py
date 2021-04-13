from abc import ABC
from collections import deque
from threading import Condition, Lock
from typing import Deque, Optional

import rospy
from std_srvs.srv import Empty, EmptyRequest, EmptyResponse
from wready.srv import InitNotify, InitNotifyRequest,\
    InitProgress, InitProgressRequest, InitProgressResponse,\
    InitRequest, InitRequestRequest, InitRequestResponse

from .sig_handler import SignalInterruptHandler

class InitTask:
    def __init__(self, name: str, notify_service: str, slot_id: int):
        self.name = name
        self.notify_service = notify_service
        self.slot_id = slot_id

class WReadyServerObserver(ABC):
    def on_task_queued(self, task: InitTask):
        pass
    
    def on_task_scheduled(self, task: InitTask):
        pass

    def on_task_progress(self, task: InitTask, update: InitProgressRequest):
        pass

    def on_task_done(self, task: InitTask):
        pass

class WReadyServer:
    def __init__(self, server_ns: Optional[str] = None, observer: Optional[WReadyServerObserver] = None):
        namespace = '~' if server_ns is None else f'{server_ns}/'
        self._srv_req = rospy.Service(f'{namespace}request', InitRequest, self._on_request_req)
        self._srv_progress = rospy.Service(f'{namespace}progress', InitProgress, self._on_progress_req)
        self._srv_done = rospy.Service(f'{namespace}done', Empty, self._on_done_req)
        self._last_task_id = -1
        self._req_queue: Deque[InitTask] = deque()
        self._current_task: Optional[InitTask] = None
        self._task_lock = Lock()
        self._task_cond = Condition(self._task_lock)
        self.observer = observer
        self._sig_int_handler = SignalInterruptHandler(self.kill)
    
    def _next_task_id(self) -> int:
        self._last_task_id += 1
        return self._last_task_id

    def _on_request_req(self, req: InitRequestRequest) -> InitRequestResponse:
        task = InitTask(req.name, req.notify_cb, self._next_task_id())
        self._req_queue.append(task)
        if self.observer:
            self.observer.on_task_queued(task)
        return InitRequestResponse(task.slot_id)

    def _on_progress_req(self, req: InitProgressRequest) -> InitProgressResponse:
        if self._current_task is None:
            rospy.logwarn('Init task progress received while no task is scheduled!')
        elif self.observer:
            self.observer.on_task_progress(self._current_task, req)
        return InitProgressResponse()

    def _on_done_req(self, req: EmptyRequest) -> EmptyResponse:
        if self._current_task is None:
            rospy.logwarn('Init task done received while no task is scheduled!')
        else:
            if self.observer:
                self.observer.on_task_done(self._current_task)
            self._current_task = None
            with self._task_lock:
                self._task_cond.notify_all()
        return EmptyResponse()

    def next(self) -> bool:
        if len(self._req_queue) == 0:
            return False
        task = self._req_queue.popleft()
        self._current_task = task
        if self.observer:
            self.observer.on_task_scheduled(task)
        rospy.wait_for_service(task.notify_service)
        notify_cli = rospy.ServiceProxy(task.notify_service, InitNotify)
        try:
            notify_cli(InitNotifyRequest(task.slot_id))
            with self._sig_int_handler:
                with self._task_lock:
                    self._task_cond.wait_for(lambda: self._current_task is None)
        finally:
            notify_cli.close()
        return True

    def kill(self):
        with self._task_lock: # free any blocked threads
            self._task_cond.notify_all()
        self._srv_req.shutdown()
        self._srv_progress.shutdown()
        self._srv_done.shutdown()
