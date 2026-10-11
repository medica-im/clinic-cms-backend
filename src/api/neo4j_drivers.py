"""One Neo4j driver of each kind per process, bound to every request's context.

neomodel 6 keeps its driver in a ContextVar, like the open transaction: that is
what makes a transaction belong to the request that opened it. But a server
runs each request in a fresh copy of its root context, where no driver was ever
set, so neomodel built a new driver, with its own socket pool, for every request
and never closed it. A driver is meant to be shared: this binds the process's
drivers to a request's context before neomodel looks for one. The transaction
stays per request.

The sync driver serves the code the request reaches through sync_to_async,
which runs in a copy of the request's context.

An async driver belongs to the event loop that created it, so a new loop gets a
new driver: a server has one loop, the tests one per test.
"""
import asyncio
from urllib.parse import urlsplit

from neo4j import AsyncDriver, AsyncGraphDatabase, Driver, GraphDatabase
from neomodel import adb, db, get_config

_async: tuple[asyncio.AbstractEventLoop, AsyncDriver] | None = None
_sync: Driver | None = None


def _target() -> tuple[str, tuple[str, str], str | None]:
    """URI, credentials and database name, from neomodel's database_url."""
    url = urlsplit(get_config().database_url)
    credentials, host = url.netloc.rsplit("@", 1)
    user, _, password = credentials.partition(":")
    database = get_config().database_name or url.path.strip("/") or None
    return f"{url.scheme}://{host}", (user, password), database


def async_driver() -> AsyncDriver:
    global _async
    loop = asyncio.get_running_loop()
    if _async is None or _async[0] is not loop:
        uri, auth, _ = _target()
        _async = (loop, AsyncGraphDatabase.driver(uri, auth=auth))
    return _async[1]


def sync_driver() -> Driver:
    global _sync
    if _sync is None:
        uri, auth, _ = _target()
        _sync = GraphDatabase.driver(uri, auth=auth)
    return _sync


def bind_drivers() -> None:
    """Give the current context the shared drivers, unless it has its own."""
    database = _target()[2]
    if adb.driver is None:
        adb.driver = async_driver()
        if database:
            adb._database_name = database
    if db.driver is None:
        db.driver = sync_driver()
        if database:
            db._database_name = database


async def close_drivers() -> None:
    global _async, _sync
    if _async is not None:
        await _async[1].close()
    if _sync is not None:
        _sync.close()
    _async = _sync = None


class Neo4jDriversMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            bind_drivers()
        await self.app(scope, receive, send)
