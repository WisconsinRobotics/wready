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
    """A data object representing a single task."""
    
    def __init__(self, name: str, notify_service: str, slot_id: int):
        """Constructs a new task object.

        Parameters
        ----------
        name : str
            This task's name.
        notify_service : str
            The notify callback service name for this task.
        slot_id : int
            This task's slot ID.
        """
        self.name = name
        self.notify_service = notify_service
        self.slot_id = slot_id

class WReadyServerObserver(ABC):
    """An observer for the WReady server.

    When installed in a `WReadyServer`, the server will invoke the
    listener methods on this class when certain events occur.
    """
    
    def on_task_queued(self, task: InitTask):
        """Called when a new task is queued.

        Parameters
        ----------
        task : InitTask
            The newly-queued task.
        """
        pass
    
    def on_task_scheduled(self, task: InitTask):
        """Called when a task is scheduled.

        Parameters
        ----------
        task : InitTask
            The task that has been scheduled.
        """
        pass

    def on_task_progress(self, task: InitTask, update: InitProgressRequest):
        """Called when a client reports progress on a task.

        Parameters
        ----------
        task : InitTask
            The task that progress is being reported for.
        update : InitProgressRequest
            The progress report object.
        """
        pass

    def on_task_done(self, task: InitTask):
        """Called when a task has been completed.

        Parameters
        ----------
        task : InitTask
            The task that has completed.
        """
        pass

class WReadyServer:
    """A WReady server instance.
    
    A server frontend should repeatedly call the `next` method on
    the `WReadyServer` instance, as this is what performs the
    brunt of the server's task-scheduling work.
    """
    
    def __init__(self, server_ns: Optional[str] = None, observer: Optional[WReadyServerObserver] = None):
        """Constructs a new WReady server instance.

        Parameters
        ----------
        server_ns : Optional[str], optional
            The ROS namespace for the WReady server. By default,
            uses the node's private namespace.
        observer : Optional[WReadyServerObserver], optional
            An observer for this WReady server, if any.
        """
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
        """Produces an unused task slot ID.

        Returns
        -------
        int
            The next unused task slot ID.
        """
        self._last_task_id += 1
        return self._last_task_id

    def _on_request_req(self, req: InitRequestRequest) -> InitRequestResponse:
        """Callback for task requests from WReady clients.

        Parameters
        ----------
        req : InitRequestRequest
            The task request request object (lol).

        Returns
        -------
        InitRequestResponse
            A response with the newly-allocated task slot ID.
        """
        task = InitTask(req.name, req.notify_cb, self._next_task_id())
        self._req_queue.append(task)
        if self.observer:
            self.observer.on_task_queued(task)
        return InitRequestResponse(task.slot_id)

    def _on_progress_req(self, req: InitProgressRequest) -> InitProgressResponse:
        """Callback for task progress reports from WReady clients.

        Just passes the report along to the observer, if one is installed.

        Parameters
        ----------
        req : InitProgressRequest
            The progress report request object.

        Returns
        -------
        InitProgressResponse
            The empty response.
        """
        if self._current_task is None:
            rospy.logwarn('Init task progress received while no task is scheduled!')
        elif self.observer:
            self.observer.on_task_progress(self._current_task, req)
        return InitProgressResponse()

    def _on_done_req(self, req: EmptyRequest) -> EmptyResponse:
        """Callback for task completion notifications from WReady clients.

        Parameters
        ----------
        req : EmptyRequest
            The task completion request object.

        Returns
        -------
        EmptyResponse
            The empty response.
        """
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
        """Attempts to schedule a task.

        If successful, this call will block until the task is
        completed by the associated WReady client.

        This is the brunt of the WReady server's work, and so this
        method should be called repeatedly by the server frontend.
        The simplest implementation would simply call this in an
        infinite loop::

            sleeper = rospy.Rate(loop_rate)
            while not rospy.is_shutdown():
                wready_server.next()
                sleeper.sleep()
        
        Indeed, this is exactly what the default server
        implementation included with WReady does. However, this
        method also returns a boolean that indicates whether a
        task was successfully scheduled or not, which may be
        used to perform more complex scheduling behaviour. For
        example, this might be used to implement some kind of
        backoff mechanism.

        Returns
        -------
        bool
            Whether a task was successfully scheduled or not.
        """
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
        """Shuts down the WReady server.

        All communication with WReady clients is terminated and
        any queued tasks will not be scheduled. Note that this
        may cause WReady clients waiting for tasks to be
        scheduled to deadlock.
        """
        with self._task_lock: # free any blocked threads
            self._task_cond.notify_all()
        self._srv_req.shutdown()
        self._srv_progress.shutdown()
        self._srv_done.shutdown()
