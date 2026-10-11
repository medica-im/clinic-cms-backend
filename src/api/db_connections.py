"""Replace dead or expired database connections around each request.

Django does this in close_old_connections(), run from the request_started and
request_finished signals of its own request cycle. FastAPI fires neither, so
without this a connection Postgres closed stays closed: every query fails until
the process restarts. With CONN_HEALTH_CHECKS, close_old_connections() also
re-arms the check that tests a reused connection before its first query.

Connections are per thread and the async ORM runs on the thread-sensitive
executor, so that is where this must run; called from the event loop it would
close the event loop thread's connection, which no query uses. Django's own
ASGIHandler sends its signals the same way.

A plain ASGI middleware rather than BaseHTTPMiddleware: the second call runs
once the whole response is sent, the invitations' event stream included.
"""
from asgiref.sync import sync_to_async
from django.db import close_old_connections

close_old_connections_on_orm_thread = sync_to_async(close_old_connections, thread_sensitive=True)


class CloseOldConnectionsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        await close_old_connections_on_orm_thread()
        try:
            await self.app(scope, receive, send)
        finally:
            await close_old_connections_on_orm_thread()
