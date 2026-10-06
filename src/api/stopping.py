"""Whether this server process has been asked to stop.

uvicorn, asked to stop (SIGTERM from docker stop or from --reload, SIGINT),
waits for every open connection to close before it does. A long-lived
response -- the invitations' event stream -- never closes by itself, so it
held the old process forever: --reload hung, and the backend answered 504
meanwhile. install() wraps uvicorn's own handlers so that a stop request also
sets an event long-lived responses watch (mailer.live.stream_changes); uvicorn
then proceeds as usual. Called at startup, after uvicorn installed its handlers.
"""
import asyncio
import signal

_event: asyncio.Event | None = None


def install() -> asyncio.Event:
    global _event
    loop = asyncio.get_running_loop()
    event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(sig)

        def handler(signum, frame, previous=previous):
            loop.call_soon_threadsafe(event.set)
            if callable(previous):
                previous(signum, frame)

        signal.signal(sig, handler)
    _event = event
    return event


def event() -> asyncio.Event:
    """The stop event; a fresh, never-set one if install() has not run (tests)."""
    global _event
    if _event is None:
        _event = asyncio.Event()
    return _event
