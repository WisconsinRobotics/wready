from abc import ABC, abstractmethod
from threading import Condition, Lock, Semaphore
from typing import Callable, ContextManager, Dict, Optional

import rospy
from std_msgs.msg import Empty

from wready.msg import InitNotify, InitProgress
from wready.srv import InitRequest

class TaskContext(ABC):
    @abstractmethod
    def report_progress(self, msg: str = '', compl: float = 0):
        raise NotImplementedError('Abstract method!')

class WReadyClient:
    class TaskContextImpl(TaskContext):
        def __init__(self, pub_progress: rospy.Publisher):
            self.pub_progress = pub_progress
        
        def report_progress(self, msg: str = '', compl: float = 0):
            self.pub_progress.publish(InitProgress(msg, compl))

    class SyncTask(ContextManager[TaskContext]):
        def __init__(self, task_ctx: TaskContext, pub_done: rospy.Publisher):
            self.task_ctx = task_ctx
            self.pub_done = pub_done
            self.semaphore = Semaphore(0)

        def __enter__(self) -> TaskContext:
            self.semaphore.acquire()
            return self.task_ctx
        
        def __exit__(self, e_type, value, traceback):
            self.pub_done.publish(Empty())

    def __init__(self, server_ns: str, notify_topic: Optional[str] = None):
        req_srv_name = f'{server_ns}/request'
        rospy.wait_for_service(req_srv_name)
        self._cli_req = rospy.ServiceProxy(req_srv_name, InitRequest)
        self._sub_notify = rospy.Subscriber(notify_topic or '~wready_notify', InitNotify, self._on_notify_msg)
        self._pub_progress = rospy.Publisher(f'{server_ns}/progress', InitProgress, queue_size=10)
        self._pub_done = rospy.Publisher(f'{server_ns}/done', Empty, queue_size=1)
        self._task_ctx = self.TaskContextImpl(self._pub_progress) # with current api shape, we only need one
        self._task_callbacks: Dict[int, Callable[[], None]] = dict()
        self._task_callback_lock = Lock()
        self._task_callback_cond = Condition(self._task_callback_lock)
    
    def request_sync(self, task_name: str) -> ContextManager[TaskContext]:
        with self._task_callback_lock:
            slot_id = self._request_slot(task_name)
            task = self.SyncTask(self._task_ctx, self._pub_done)
            self._task_callbacks[slot_id] = lambda: task.semaphore.release()
            return task

    def request_async(self, task_name: str, callback: Callable[[TaskContext], None]):
        with self._task_callback_lock:
            slot_id = self._request_slot(task_name)
            def cb_wrapper():
                callback(self._task_ctx)
                self._pub_done.publish(Empty())
            self._task_callbacks[slot_id] = cb_wrapper

    def _request_slot(self, task_name: str) -> int:
        slot_id = self._cli_req(task_name, self._sub_notify.name).id
        if slot_id in self._task_callbacks: # this shouldn't happen, but we'll check anyways
            raise KeyError(f'Init task slot {slot_id} is already occupied!')
        return slot_id

    def _on_notify_msg(self, msg: InitNotify):
        with self._task_callback_lock:
            cb = self._task_callbacks.pop(msg.id, None)
            if cb is not None:
                cb()
                self._task_callback_cond.notify_all()
            else:
                rospy.logwarn(f'Received init task notification for unknown ID {msg.id}')
                # TODO: maybe send a "done" if this happens? or maybe fail-fast is better
    
    def wait(self):
        with self._task_callback_lock:
            self._task_callback_cond.wait_for(lambda: len(self._task_callbacks) == 0)

    def kill(self):
        with self._task_callback_lock: # free any blocked threads
            self._task_callback_cond.notify_all()
        self._cli_req.close()
        self._sub_notify.unregister()
        self._pub_progress.unregister()
        self._pub_done.unregister()
