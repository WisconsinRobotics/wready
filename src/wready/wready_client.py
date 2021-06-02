from abc import ABC, abstractmethod
from threading import Condition, Lock, Semaphore
from typing import Callable, ContextManager, Dict, Optional

import rospy
from std_srvs.srv import Empty
from wready.srv import InitNotify, InitNotifyRequest, InitNotifyResponse, InitRequest, InitProgress

from .sig_handler import SignalInterruptHandler

class TaskContext(ABC):
    """The context for a running task."""
    
    @abstractmethod
    def report_progress(self, msg: str = '', compl: float = 0):
        """Sends a progress update to the WReady server for this task.

        Parameters
        ----------
        msg : str, optional
            The message for the progress report, defaulting to an empty string.
        compl : float, optional
            The progress percentage to report, defaulting to 0.
        """
        raise NotImplementedError('Abstract method!')

class WReadyClient:
    """An implementation of a WReady client.
    
    Both synchronous tasks and asynchronous tasks are supported through the
    `request_sync` and `request_async` methods respectively.
    """
    
    class TaskContextImpl(TaskContext):
        """The implementation of `TaskContext` for a `WReadyClient` instance.
        
        Note that this class does not depend on the specific task at all, so
        it is sufficient to create a single instance for the entire client.
        """
        
        def __init__(self, cli_progress: rospy.ServiceProxy):
            """Creates a new task context instance.

            Parameters
            ----------
            cli_progress : rospy.ServiceProxy
                The service client for task progress reports.
            """
            self._cli_progress = cli_progress
        
        def report_progress(self, msg: str = '', compl: float = 0):
            self._cli_progress(msg, compl)

    class SyncTask(ContextManager[TaskContext]):
        """A context manager used to wrap a synchronous task.
        
        Entry blocks until the task is scheduled and exit reports task comletion.
        """
        
        def __init__(self, task_ctx: TaskContext, cli_done: rospy.ServiceProxy):
            """Constructs a new synchronous task wrapper.

            Parameters
            ----------
            task_ctx : TaskContext
                The context for the task.
            cli_done : rospy.ServiceProxy
                The service client for the WReady server's completion callback.
            """
            self._task_ctx = task_ctx
            self._cli_done = cli_done
            self._semaphore = Semaphore(0)

        def __enter__(self) -> TaskContext:
            self._semaphore.acquire()
            return self._task_ctx
        
        def __exit__(self, e_type, value, traceback):
            self._cli_done()

    def __init__(self, server_ns: str, notify_service: Optional[str] = None):
        """Constructs a new WReady client.

        Parameters
        ----------
        server_ns : str
            The namespace for the WReady server.
        notify_service : Optional[str], optional
            The service name for the task scheduling callback service.
            Defaults to ~wready_notify in the node's private namespace.
        """
        req_srv_name = f'{server_ns}/request'
        rospy.wait_for_service(req_srv_name)
        self._cli_req = rospy.ServiceProxy(req_srv_name, InitRequest)
        self._cli_progress = rospy.ServiceProxy(f'{server_ns}/progress', InitProgress, persistent=True)
        self._cli_done = rospy.ServiceProxy(f'{server_ns}/done', Empty)
        
        self._task_ctx = self.TaskContextImpl(self._cli_progress) # with current api shape, we only need one
        self._task_callbacks: Dict[int, Callable[[], None]] = dict()
        self._task_callback_lock = Lock()
        self._task_callback_cond = Condition(self._task_callback_lock)
        
        self._sig_int_handler = SignalInterruptHandler(self.kill)

        self._srv_notify = rospy.Service(notify_service or '~wready_notify', InitNotify, self._on_notify_req)
    
    def request_sync(self, task_name: str) -> ContextManager[TaskContext]:
        """Requests a task that is completed immediately on the current thread.

        This is to say that the current thread blocks until the task is
        scheduled, at which point the task can be completed on the current
        thread. The returned context manager should be used for this::
         
            with wready_client.request_sync('Example Task'):
                do_task_stuff()

        Parameters
        ----------
        task_name : str
            The name of the task.

        Returns
        -------
        ContextManager[TaskContext]
            A context manager for the synchronous task completion.
            Entry blocks until the task is scheduled and exit reports
            task completion.
        
        See Also
        --------
        request_async : Requests tasks for asynchronous completion.
        """
        with self._task_callback_lock:
            slot_id = self._request_slot(task_name)
            task = self.SyncTask(self._task_ctx, self._cli_done)
            self._task_callbacks[slot_id] = lambda: task._semaphore.release()
            return task

    def request_async(self, task_name: str, callback: Callable[[TaskContext], None]):
        """Requests a task that is completed asynchronously.

        This method takes a callback function which should perform the work
        of the task. When the task is scheduled later, the callback is
        invoked and passed the task context. Once the callback completes,
        the task is reported as completed. For example::

            wready_client.request_async('Example Task', do_task_stuff)
            wready_client.wait() # waits for all async tasks to complete

        Parameters
        ----------
        task_name : str
            The name of the task.
        callback : Callable[[TaskContext], None]
            A callback that completes the task.

        See Also
        --------
        request_sync : Requests tasks for synchronous completion.
        wait : Blocks until all pending tasks are completed.
        """
        with self._task_callback_lock:
            slot_id = self._request_slot(task_name)
            def cb_wrapper():
                callback(self._task_ctx)
                self._cli_done()
            self._task_callbacks[slot_id] = cb_wrapper

    def _request_slot(self, task_name: str) -> int:
        """Requests a task from the WReady server.

        Parameters
        ----------
        task_name : str
            The name of the task.

        Returns
        -------
        int
            The task slot ID allocated by the server.

        Raises
        ------
        KeyError
            If the slot ID received from the server conflicts with
            an existing task. Shouldn't happen with a correctly-
            implemented WReady server.
        """
        slot_id = self._cli_req(task_name, self._srv_notify.resolved_name).id
        if slot_id in self._task_callbacks: # this shouldn't happen, but we'll check anyways
            raise KeyError(f'Init task slot {slot_id} is already occupied!')
        return slot_id

    def _on_notify_req(self, req: InitNotifyRequest) -> InitNotifyResponse:
        """Callback for task notifications from the WReady server.

        If the notified task slot ID is owned by this client, then the
        associated task callback is invoked.

        Parameters
        ----------
        req : InitNotifyRequest
            The task notification request object.

        Returns
        -------
        InitNotifyResponse
            The empty response.
        """
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
        """Blocks until all pending tasks have completed."""
        with self._sig_int_handler:
            with self._task_callback_lock:
                self._task_callback_cond.wait_for(lambda: len(self._task_callbacks) == 0)

    def kill(self):
        """Shuts down the WReady client.
        
        This closes all communications to the server. All pending
        tasks are abruptly cancelled without notifying the server
        and no further tasks may be requested.

        In order to prevent the server from waiting for a task
        completion that will never come, it is recommended that
        `wait` be called before `kill` if any asynchronous tasks
        have been requested.
        """
        with self._task_callback_lock: # free any blocked threads
            self._task_callback_cond.notify_all()
        self._cli_req.close()
        self._srv_notify.shutdown()
        self._cli_progress.close()
        self._cli_done.close()
