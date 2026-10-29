"""A job's cancellation signal follows its synchronous tools into worker threads."""
from contextvars import ContextVar

current_stop = ContextVar('jarvis_task_stop', default=None)


def check_cancelled():
    stop = current_stop.get()
    if stop is not None and stop.is_set():
        raise RuntimeError('Tâche arrêtée par l’utilisateur')
