"""FastAPI logs at the level FASTAPI_LOG_LEVEL names, on the console too.

main.py configured the root logger at DEBUG unconditionally; FASTAPI_LOG_LEVEL
only reached the log file. So production wrote every request's headers, the
full text of every Neo4j query and every cache lookup to the console — part of
why FastAPI used 85% of a core on a 2-vCPU box with almost no visitors
(2026-10-03).

Checked in a fresh interpreter importing main, as the server does: the level
is set once, at import, and this test process has imported main already.
"""
import os
import subprocess
import sys

import pytest

PROBE = """
import logging, main
root = logging.getLogger()
print(logging.getLevelName(root.level))
print(logging.getLogger('neomodel.async_.core').isEnabledFor(logging.DEBUG))
print(logging.getLogger('api.routers.organization').isEnabledFor(logging.INFO))
"""


def levels_with(value):
    env = {**os.environ, "FASTAPI_LOG_LEVEL": value}
    out = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    root, neo4j_debug, info = out.stdout.strip().splitlines()[-3:]
    return root, neo4j_debug == "True", info == "True"


def test_info_silences_the_debug_flood():
    root, neo4j_debug, info = levels_with("INFO")
    assert root == "INFO"
    assert not neo4j_debug, "Neo4j query text would still be logged"
    assert info, "INFO messages must still get through"


def test_debug_keeps_everything_for_dev():
    root, neo4j_debug, _ = levels_with("DEBUG")
    assert root == "DEBUG"
    assert neo4j_debug


def test_an_unknown_level_falls_back_to_debug_rather_than_failing():
    root, _, _ = levels_with("CHATTY")
    assert root == "DEBUG"
