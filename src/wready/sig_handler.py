import signal
import threading
from typing import Any, Callable, ContextManager, Optional, Tuple

class SignalInterruptHandler(ContextManager['SignalInterruptHandler']):
    """Utility for installing custom signal handlers for SIGINT, SIGHUP, and SIGTERM.
    
    To guard a block with a particular custom signal handler, call `inject` before the
    block and `restore` after. This could be useful for, for example, interrupting a
    long-running process that is normally uninterruptible, such as a blocking socket
    read operation. It is recommended that a `finally` block be used to ensure that
    `restore` is successfully called after the guarded block completes::

        sig_int_handler = SignalInterruptHandler(interrupt_handler)
        sig_int_handler.inject()
        try:
            do_stuff() # this is now guarded
        finally:
            sig_int_handler.restore()

    This class can also be used as a context manager. In that case, a block can be
    guarded by simply using it in a `with` expression::

        with SignalInterruptHandler(interrupt_handler):
            do_stuff() # this is now guarded

    Note that after the interrupt handler completes, a `KeyboardInterrupt` is
    automatically raised in order to prompt program termination.
    """
    
    def __init__(self, interrupt_handler: Callable[[], None]):
        """Creates a signal interrupt handler with the given interrupt callback.

        Parameters
        ----------
        interrupt_handler : Callable[[], None]
            The callback for handling the interrupt.
        """
        self._handler = interrupt_handler
        self._prev_sig_handlers: Optional[Tuple[Any, Any, Any]] = None # signal handler type is opaque

    def inject(self):
        """Injects the signal handler, storing the previously-installed handler.

        Call `restore` later to restore the previous handler.
        """
        if self._prev_sig_handlers is None and threading.current_thread() == threading.main_thread():
            def interrupt(*sig):
                self._handler()
                raise KeyboardInterrupt()
            self._prev_sig_handlers = signal.signal(signal.SIGINT, interrupt),\
                                      signal.signal(signal.SIGHUP, interrupt),\
                                      signal.signal(signal.SIGTERM, interrupt)

    def restore(self):
        """Restores the previously-installed signal handler, if any."""
        if self._prev_sig_handlers is not None:
            signal.signal(signal.SIGINT, self._prev_sig_handlers[0])
            signal.signal(signal.SIGHUP, self._prev_sig_handlers[1])
            signal.signal(signal.SIGTERM, self._prev_sig_handlers[2])

    def __enter__(self) -> 'SignalInterruptHandler':
        self.inject()
        return self

    def __exit__(self, *exc):
        self.restore()
