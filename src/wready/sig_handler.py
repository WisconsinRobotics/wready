import signal
import threading
from typing import Any, Callable, ContextManager, Optional, Tuple

class SignalInterruptHandler(ContextManager['SignalInterruptHandler']):
    def __init__(self, interrupt_handler: Callable[[], None]):
        self._handler = interrupt_handler
        self._prev_sig_handlers: Optional[Tuple[Any, Any, Any]] = None # signal handler type is opaque

    def inject(self):
        if self._prev_sig_handlers is None and threading.current_thread() == threading.main_thread():
            def interrupt(*sig):
                self._handler()
                raise KeyboardInterrupt()
            self._prev_sig_handlers = signal.signal(signal.SIGINT, interrupt),\
                                      signal.signal(signal.SIGHUP, interrupt),\
                                      signal.signal(signal.SIGTERM, interrupt)

    def restore(self):
        if self._prev_sig_handlers is not None:
            signal.signal(signal.SIGINT, self._prev_sig_handlers[0])
            signal.signal(signal.SIGHUP, self._prev_sig_handlers[1])
            signal.signal(signal.SIGTERM, self._prev_sig_handlers[2])

    def __enter__(self) -> 'SignalInterruptHandler':
        self.inject()
        return self

    def __exit__(self, *exc):
        self.restore()
