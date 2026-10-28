"""Reads from Neo4j through the official driver, not neomodel.

New graph code goes through here: the process's shared async driver
(api.neo4j_drivers), a session per unit of work, an explicit read transaction
(execute_read retries transient errors), Cypher parameters only. Rows come back
as plain dicts; callers turn them into Pydantic models.
"""
from typing import Any, LiteralString

from neo4j import AsyncManagedTransaction

from api.neo4j_drivers import _target, async_driver


async def read(query: LiteralString, **params: Any) -> list[dict[str, Any]]:
    """Every row of `query`, run in a read transaction on the configured database."""

    async def work(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
        result = await tx.run(query, params)
        return [record.data() async for record in result]

    async with async_driver().session(database=_target()[2]) as session:
        return await session.execute_read(work)
