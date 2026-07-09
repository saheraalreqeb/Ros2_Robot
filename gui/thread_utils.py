"""
Thread utility helpers for safe shutdown.
"""


def _safe_stop_thread(thread, timeout_ms: int = 3000) -> None:
    """Safely stop a QThread with bounded wait.  Idempotent.

    Handles ``None``, already-finished threads, and ``RuntimeError``
    (deleted Qt objects) without raising.
    """
    if thread is None:
        return
    try:
        if thread.isRunning():
            if hasattr(thread, 'requestInterruption'):
                thread.requestInterruption()
            if hasattr(thread, 'quit'):
                thread.quit()
            thread.wait(timeout_ms)
    except RuntimeError:
        pass  # Qt object may already be deleted
