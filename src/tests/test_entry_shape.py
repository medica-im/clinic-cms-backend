"""The shape of one entry, checked where it is written.

An Entry is the statement "this person, in this occupation, at this place,
listed in this directory": exactly one HAS_EFFECTOR, one HAS_EFFECTOR_TYPE,
one HAS_FACILITY, and at least one Directory. Nothing in Neo4j enforces it
(tests/test_entry_graph_model.py explains why), and a second type edge makes
the entry appear twice in /api/v2/entries.

test_entry_graph_model.py checks the whole dataset after the fact. This is
the same invariant for ONE entry, as code a write can call before and after
it touches the graph -- changing an entry's type checks it on both sides and
rolls back rather than leave a malformed entry behind.

Problems are codes ("HAS_EFFECTOR_TYPE:2", "HAS_FACILITY:0", "NO_DIRECTORY"),
so the API can report them and a log line says exactly what is wrong.
"""

import pytest

from directory.entry_shape import SINGLE_VALUED, shape_problems

pytestmark = pytest.mark.no_db

WELL_FORMED = {"HAS_EFFECTOR": 1, "HAS_EFFECTOR_TYPE": 1, "HAS_FACILITY": 1}


def test_the_single_valued_edges_are_the_three_of_the_model():
    assert set(SINGLE_VALUED) == {"HAS_EFFECTOR", "HAS_EFFECTOR_TYPE", "HAS_FACILITY"}


def test_a_well_formed_entry_has_no_problem():
    assert shape_problems(WELL_FORMED, directories=1) == []


def test_several_directories_are_fine():
    assert shape_problems(WELL_FORMED, directories=3) == []


def test_a_second_type_is_named_with_its_count():
    assert shape_problems({**WELL_FORMED, "HAS_EFFECTOR_TYPE": 2}, directories=1) == ["HAS_EFFECTOR_TYPE:2"]


def test_a_missing_edge_is_a_problem_too():
    assert shape_problems({**WELL_FORMED, "HAS_FACILITY": 0}, directories=1) == ["HAS_FACILITY:0"]


def test_an_edge_absent_from_the_counts_counts_as_zero():
    assert shape_problems({"HAS_EFFECTOR": 1, "HAS_EFFECTOR_TYPE": 1}, directories=1) == ["HAS_FACILITY:0"]


def test_an_entry_in_no_directory_is_a_problem():
    assert shape_problems(WELL_FORMED, directories=0) == ["NO_DIRECTORY"]


def test_every_problem_is_listed_in_a_stable_order():
    counts = {"HAS_EFFECTOR": 0, "HAS_EFFECTOR_TYPE": 2, "HAS_FACILITY": 1}

    assert shape_problems(counts, directories=0) == ["HAS_EFFECTOR:0", "HAS_EFFECTOR_TYPE:2", "NO_DIRECTORY"]
