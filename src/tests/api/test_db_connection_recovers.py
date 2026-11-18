"""FastAPI recovers its Postgres connection after Postgres drops it.

Django replaces a dead or expired connection only in close_old_connections(),
which its own request cycle runs from the request_started/request_finished
signals. FastAPI fires neither, so a connection Postgres closed (a restart, a
crash, an idle timeout) stayed dead, and every /api/v2 call answered 500 until
FastAPI itself restarted.

Connections are per thread, and the async ORM runs on the thread-sensitive
executor: the connection that matters is that thread's, not the event loop's.
pg_terminate_backend() is what a Postgres restart does to it.

/api/v2/entry-slugs/{slug} stands for any route: an unknown slug is answered
404 after a real ORM query, and before any Neo4j one.
"""

import pytest
from asgiref.sync import sync_to_async
from django.db import connection

pytestmark = pytest.mark.asyncio

URL = "/api/v2/entry-slugs/never-an-entrys-slug"


def backend_pid():
    connection.ensure_connection()
    return connection.connection.info.backend_pid


async def orm_thread_backend_pid():
    """The Postgres backend serving the async ORM's thread."""
    return await sync_to_async(backend_pid, thread_sensitive=True)()


def terminate(pid):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_terminate_backend(%s)", [pid])


async def terminate_from_another_connection(pid):
    """As a Postgres restart would: not from the thread whose backend dies."""
    await sync_to_async(terminate, thread_sensitive=False)(pid)


async def test_a_request_after_postgres_dropped_the_connection_succeeds(versioned_client):
    assert (await versioned_client.get(URL)).status_code == 404
    await terminate_from_another_connection(await orm_thread_backend_pid())

    response = await versioned_client.get(URL)

    assert response.status_code == 404


async def test_requests_reuse_the_connection_while_it_lives(versioned_client):
    await versioned_client.get(URL)
    first = await orm_thread_backend_pid()

    await versioned_client.get(URL)

    assert await orm_thread_backend_pid() == first
