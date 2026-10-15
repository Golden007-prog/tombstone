"""Invariants that must hold, each one locking in a bug I actually hit.

Run: PYTHONPATH=src python -m pytest tests/ -q
These need a live FalkorDB on 6380 (`docker compose up -d`) and the committed snapshot.
"""
from __future__ import annotations

import pytest

from graphkit.ingest import connect
from tombstone.agent import Agent, render
from tombstone.build import build, to_ms
from tombstone.corpus import expand, is_bot, is_template, normalise_status
from tombstone.snapshot import load, load_vectors

GRAPH = "tomb:test"


@pytest.fixture(scope="module")
def g():
    build(load(), graph_name=GRAPH)
    return connect().select_graph(GRAPH)


@pytest.fixture(scope="module")
def agent(g):
    return Agent(graph_name=GRAPH, now_ms=1_760_000_000_000)


# ---------------- parsing ----------------

def test_owners_aliases_expand_to_people():
    """A group alias must expand to its members. Missing this made 8% of my Person nodes groups."""
    table = {"sig-foo-approvers": ["alice", "bob"]}
    assert expand(["sig-foo-approvers"], table) == ["alice", "bob"]
    assert expand(["@Carol"], table) == ["carol"]          # handle passes through, normalised
    assert expand(["TBD", "", None], table) == []          # placeholders dropped


def test_bots_are_filtered():
    for h in ("k8s-ci-robot", "kubernetes-prow[bot]", "some-bot", "dependabot[bot]"):
        assert is_bot(h), h
    for h in ("lavalamp", "deads2k", "robertojrojas"):     # 'robot' substring must not false-positive
        assert not is_bot(h), h


def test_template_keps_are_excluded():
    assert is_template("NNNN-kep-template", {"kep-number": "NNNN"})
    assert is_template("sig-x/0000-cloud-provider-template", {"kep-number": 0})
    assert not is_template("sig-node/4680-add-resource-health", {"kep-number": 4680})


def test_template_placeholder_date_is_not_a_date():
    """The KEP template ships creation-date: 'yyyy-mm-dd' and authors forget to replace it."""
    assert to_ms("yyyy-mm-dd") == 0
    assert to_ms(None) == 0
    assert to_ms("") == 0
    assert to_ms("2023-01-20") > 0


def test_dirty_status_is_normalised():
    assert normalise_status("implemented")[0] == "implemented"
    assert normalise_status("imlpemented")[0] == "implemented"           # real typo in the corpus
    assert normalise_status("implementable ")[0] == "implementable"
    assert normalise_status("implemented (alpha)")[0] == "implemented"
    # unreplaced template pipe-list is not a status
    assert normalise_status("provisional|implementable|implemented")[0] == "unknown"


# ---------------- graph shape ----------------

def test_no_group_aliases_became_people(g):
    """71 of my first 866 Person nodes were groups like sig-api-machinery-approvers."""
    rows = g.ro_query(
        "MATCH (p:Person) WHERE p.key CONTAINS '-approvers' OR p.key CONTAINS '-reviewers' "
        "OR p.key CONTAINS '-maintainers' RETURN p.key"
    ).result_set
    assert rows == [], f"group aliases leaked into Person: {rows[:5]}"


def test_named_options_have_vectors_and_plain_alternatives_may_not(g):
    """The vector index is on :NamedOption, because FalkorDB vector indexes cannot
    property-filter -- a shared index would force post-filtering and lose recall."""
    named = g.ro_query("MATCH (a:NamedOption) RETURN count(a)").result_set[0][0]
    withvec = g.ro_query(
        "MATCH (a:NamedOption) WHERE a.emb IS NOT NULL RETURN count(a)"
    ).result_set[0][0]
    assert named > 500
    assert withvec == named, f"{named - withvec} NamedOption nodes have no embedding"


def test_snapshot_vectors_match_alternatives():
    keys, vecs = load_vectors()
    assert keys and vecs and len(keys) == len(vecs)
    assert len(vecs[0]) == 384


# ---------------- Cypher engine limits I verified ----------------

def test_variable_length_bounds_cannot_be_parameterised(g):
    """v4.22.1: `*1..$d` fails. Depth must be a literal, which is why who_owns ships as two
    fixed queries rather than one parameterised one."""
    with pytest.raises(Exception):
        g.ro_query("MATCH p=(k:Kep)-[:SEE_ALSO*1..$d]->(x) RETURN count(p)", params={"d": 2})


def test_exact_hop_equals_explicit_range(g):
    """A claim that exact `*2` returns nothing is false -- it equals `*2..2`."""
    a = g.ro_query("MATCH p=(k:Kep)-[:SEE_ALSO*2]->(x) RETURN count(p)").result_set[0][0]
    b = g.ro_query("MATCH p=(k:Kep)-[:SEE_ALSO*2..2]->(x) RETURN count(p)").result_set[0][0]
    assert a == b


def test_limit_is_ignored_by_destructive_clauses(g):
    """LIMIT does NOT bound CREATE/DELETE. A purge written that way deletes the wrong amount.
    The correct idiom is WITH ... LIMIT n before the destructive clause."""
    t = connect().select_graph("tomb:limit_probe")
    try:
        t.delete()
    except Exception:
        pass
    t = connect().select_graph("tomb:limit_probe")
    t.query("UNWIND [1,2,3] AS v CREATE (:T {v: v}) RETURN 1 LIMIT 1")
    assert t.ro_query("MATCH (n:T) RETURN count(n)").result_set[0][0] == 3   # not 1
    t.query("MATCH (n:T) WITH n LIMIT 2 DELETE n")
    assert t.ro_query("MATCH (n:T) RETURN count(n)").result_set[0][0] == 1   # correct idiom works
    t.delete()


def test_seeded_betweenness_is_reproducible(g):
    q = ("CALL algo.betweenness({nodeLabels:['Person'],relationshipTypes:['CO_AUTHORED'],"
         "samplingSeed:42}) YIELD node, score RETURN node.key, score ORDER BY score DESC LIMIT 5")
    assert g.ro_query(q).result_set == g.ro_query(q).result_set


# ---------------- agent contract ----------------

def test_all_four_answer_shapes_are_reachable(agent):
    assert agent.dispatch("orphaned_ownership", {}).shape == "ANSWERED_WITH_PATH"
    assert agent.dispatch("successor_for", {"handle": "no-such-human"}).shape == "UNKNOWN_ENTITY"
    assert agent.dispatch("not_a_tool", {}).shape == "UNKNOWN_ENTITY"
    absurd = agent.dispatch(
        "has_this_been_tried",
        {"idea_text": "rewrite the control plane in COBOL on a mainframe", "max_dist": 0.15},
    )
    assert absurd.shape == "NOT_IN_GRAPH"


def test_negative_answers_always_carry_coverage(agent):
    """An empty traversal only means the graph does not know. Saying otherwise is the
    plausible-wrong-answer failure the brief warns about."""
    a = agent.dispatch(
        "has_this_been_tried",
        {"idea_text": "rewrite the control plane in COBOL on a mainframe", "max_dist": 0.15},
    )
    assert a.shape == "NOT_IN_GRAPH"
    assert a.coverage.get("decisions_indexed", 0) > 500
    assert "not proof" in render(a).lower()


def test_depth_contrast_is_real(agent):
    """The rubric asks for the same question at two depths. Depth 1 finds nothing for an
    orphaned area; depth 4 explains who used to own it."""
    path = "pkg/controller/podgc/OWNERS"
    d1 = agent.dispatch("who_owns", {"path": path, "depth": 1})
    d4 = agent.dispatch("who_owns", {"path": path, "depth": 4})
    assert d1.shape == "NOT_IN_GRAPH"
    assert d4.shape == "ANSWERED_WITH_PATH"
    assert "ORPHANED" in render(d4)


def test_unknown_entity_runs_nothing(agent):
    a = agent.dispatch("who_owns", {"path": "totally/made/up/OWNERS", "depth": 4})
    assert a.shape == "UNKNOWN_ENTITY"
    assert a.rows == []


def test_no_age_is_rendered_when_the_date_is_missing(agent):
    a = agent.dispatch(
        "has_this_been_tried",
        {"idea_text": "make it opt-in with a feature gate rather than changing the default"},
    )
    out = render(a)
    assert "55y ago" not in out
    if any(r[7] is not None and r[7] < 0 for r in a.rows):
        assert "date not recorded" in out


def test_agent_fails_loudly_without_the_database():
    """No in-memory mirror, no cached fallback. With FalkorDB gone the product stops."""
    import os

    old = os.environ.get("FALKORDB_PORT")
    os.environ["FALKORDB_PORT"] = "6399"          # nothing listening
    try:
        a = Agent(graph_name=GRAPH)
        assert a.health()["falkordb"] == "down"
        out = a.ask("who owns the scheduler?")
        assert out["shape"] == "DEGRADED"
        assert "no fallback" in out["answer"].lower()
    finally:
        if old is None:
            os.environ.pop("FALKORDB_PORT", None)
        else:
            os.environ["FALKORDB_PORT"] = old
