from abc import ABC, abstractmethod
from threading import Condition, Lock, Semaphore
from typing import Callable, ContextManager, Dict, Optional

import rospy
from std_srvs.srv import Empty
from wready.srv import InitNotify, InitNotifyRequest, InitNotifyResponse, InitRequest, InitProgress

from .sig_handler import SignalInterruptHandler

class TaskContext(ABC):
    @abstractmethod
    def report_progress(self, msg: str = '', compl: float = 0):
        raise NotImplementedError('Abstract method!')

class WReadyClient:
    class TaskContextImpl(TaskContext):
        def __init__(self, cli_progress: rospy.ServiceProxy):
            self._cli_progress = cli_progress
        
        def report_progress(self, msg: str = '', compl: float = 0):
            self._cli_progress(msg, compl)

    class SyncTask(ContextManager[TaskContext]):
        def __init__(self, task_ctx: TaskContext, cli_done: rospy.ServiceProxy):
            self._task_ctx = task_ctx
            self._cli_done = cli_done
            self._semaphore = Semaphore(0)

        def __enter__(self) -> TaskContext:
            self._semaphore.acquire()
            return self._task_ctx
        
        def __exit__(self, e_type, value, traceback):
            self._cli_done()

    def __init__(self, server_ns: str, notify_service: Optional[str] = None):
        req_srv_name = f'{server_ns}/request'
        rospy.wait_for_service(req_srv_name)
        self._cli_req = rospy.ServiceProxy(req_srv_name, InitRequest)
        self._srv_notify = rospy.Service(notify_service or '~wready_notify', InitNotify, self._on_notify_req)
        self._cli_progress = rospy.ServiceProxy(f'{server_ns}/progress', InitProgress, persistent=True)
        self._cli_done = rospy.ServiceProxy(f'{server_ns}/done', Empty)
        self._task_ctx = self.TaskContextImpl(self._cli_progress) # with current api shape, we only need one
        self._task_callbacks: Dict[int, Callable[[], None]] = dict()
        self._task_callback_lock = Lock()
        self._task_callback_cond = Condition(self._task_callback_lock)
        self._sig_int_handler = SignalInterruptHandler(self.kill)
    
    def request_sync(self, task_name: str) -> ContextManager[TaskContext]:
        with self._task_callback_lock:
            slot_id = self._request_slot(task_name)
            task = self.SyncTask(self._task_ctx, self._cli_done)
            self._task_callbacks[slot_id] = lambda: task._semaphore.release()
            return task

    def request_async(self, task_name: str, callback: Callable[[TaskContext], None]):
        with self._task_callback_lock:
            slot_id = self._request_slot(task_name)
            def cb_wrapper():
                callback(self._task_ctx)
                self._cli_done()
            self._task_callbacks[slot_id] = cb_wrapper

    def _request_slot(self, task_name: str) -> int:
        slot_id = self._cli_req(task_name, self._srv_notify.resolved_name).id
        if slot_id in self._task_callbacks: # this shouldn't happen, but we'll check anyways
            raise KeyError(f'Init task slot {slot_id} is already occupied!')
        return slot_id

    def _on_notify_req(self, req: InitNotifyRequest):
        with self._task_callback_lock:
            cb = self._task_callbacks.pop(req.id, None)
            if cb is not None:
                cb()
                self._task_callback_cond.notify_all()
            else:
                rospy.logwarn(f'Received init task notification for unknown ID {req.id}')
                # TODO: maybe send a "done" if this happens? or maybe fail-fast is better
        return InitNotifyResponse()
    
    def wait(self):
        with self._sig_int_handler:
            with self._task_callback_lock:
                self._task_callback_cond.wait_for(lambda: len(self._task_callbacks) == 0)

    def kill(self):
        with self._task_callback_lock: # free any blocked threads
            self._task_callback_cond.notify_all()
        self._cli_req.close()
        self._srv_notify.shutdown()
        self._cli_progress.close()
        self._cli_done.close()
