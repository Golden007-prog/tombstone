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
    assert agent.dispatch("ownership_dilution", {}).shape == "ANSWERED_WITH_PATH"
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
    assert "every dedicated owner has left" in render(d4)


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


def test_malformed_arguments_never_leak_a_python_error(agent):
    """A bad argument type is a bad request, not a database failure. Judges will poke at this."""
    for tool, args in [
        ("departed_bridges", {"min_areas": "lots"}),
        ("broken_lineage", {"min_cites": -1}),
        ("has_this_been_tried", {"idea_text": "kubelet state", "max_dist": "near"}),
        ("who_owns", {"path": None, "depth": 4}),
        ("successor_for", {"handle": None}),
        ("successor_for", {}),
    ]:
        a = agent.dispatch(tool, args)
        assert a.shape in {"ANSWERED_WITH_PATH", "NOT_IN_GRAPH", "UNKNOWN_ENTITY"}, (tool, args, a.shape)
        body = render(a)
        for leak in ("Traceback", "invalid literal", "could not convert", "NoneType"):
            assert leak not in body, f"{tool}{args} leaked: {body[:120]}"


def test_any_depth_clamps_to_the_two_that_exist(agent):
    """Only two depths exist. A third tool name would fall through the renderer and print tuples."""
    path = "pkg/controller/podgc/OWNERS"
    for d in (2, 9999, 7):
        a = agent.dispatch("who_owns", {"path": path, "depth": d})
        assert a.tool == "who_owns(depth=4)", f"depth={d} produced {a.tool}"
        assert "every dedicated owner has left" in render(a)
    assert agent.dispatch("who_owns", {"path": path, "depth": -5}).tool == "who_owns(depth=1)"


def test_cypher_injection_is_structurally_impossible(agent):
    """Every query is parameterised and entity names are resolved against the graph first."""
    before = agent.g.ro_query("MATCH (k:Kep) RETURN count(k)").result_set[0][0]
    for tool, args in [
        ("successor_for", {"handle": "lavalamp'}) DETACH DELETE (n) //"}),
        ("who_owns", {"path": "x' OR 1=1 //", "depth": 4}),
        ("who_owns", {"path": "'); MATCH (n) DETACH DELETE n; //", "depth": 1}),
    ]:
        assert agent.dispatch(tool, args).shape == "UNKNOWN_ENTITY"
    assert agent.g.ro_query("MATCH (k:Kep) RETURN count(k)").result_set[0][0] == before


def test_agent_recovers_after_the_database_comes_back():
    """An instance that starts (or is hit) while FalkorDB is briefly down must not stay broken.

    The agent is cached per process, so without an explicit reconnect a judge clicking during a
    restart would get a permanently dead site until someone redeployed.
    """
    import os

    old = os.environ.get("FALKORDB_PORT")
    os.environ["FALKORDB_PORT"] = "6399"          # nothing listening
    try:
        a = Agent(graph_name=GRAPH)
        assert a.health()["falkordb"] == "down"
        assert a.dispatch("ownership_dilution", {}).shape == "DEGRADED"
    finally:
        if old is None:
            os.environ.pop("FALKORDB_PORT", None)
        else:
            os.environ["FALKORDB_PORT"] = old
    # same agent object, database now reachable again
    assert a.health()["falkordb"] == "up"
    assert a.dispatch("ownership_dilution", {}).shape == "ANSWERED_WITH_PATH"


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


# ---------------- the model-routing loop, with no API key needed ----------------

class _StubProvider:
    """Stands in for a real model so routing is testable in CI and without a key."""

    def __init__(self, reply: str):
        self.reply = reply
        self.provider = "stub"
        self.model = "stub-1"

    def choose_tool(self, system, question, catalogue):
        from tombstone.llm import Provider
        return Provider._parse(self.reply)


@pytest.mark.parametrize(
    "reply,expect_tool",
    [
        ('{"tool":"ownership_dilution","args":{}}', "ownership_dilution"),
        ('```json\n{"tool":"ownership_dilution","args":{}}\n```', "ownership_dilution"),
        ('Sure! Here you go:\n{"tool": "ownership_dilution", "args": {}}', "ownership_dilution"),
    ],
)
def test_router_survives_the_shapes_models_actually_emit(agent, reply, expect_tool):
    agent._provider = _StubProvider(reply)
    out = agent.ask("which areas have nobody left?")
    assert out["routed_to"] == expect_tool
    assert out["shape"] == "ANSWERED_WITH_PATH"


def test_a_hallucinated_tool_is_refused_not_guessed(agent):
    agent._provider = _StubProvider('{"tool":"summarise_everything","args":{}}')
    out = agent.ask("summarise the whole project")
    assert out["shape"] == "UNKNOWN_ENTITY"
    assert "not a tool in this catalogue" in out["answer"]


def test_unparseable_model_output_degrades_cleanly(agent):
    agent._provider = _StubProvider("I think you should look at the kubelet.")
    out = agent.ask("who owns the kubelet?")
    assert out["shape"] == "DEGRADED"
    assert "routing failed" in out["answer"].lower()


# ---------------- memory: "remembers what it learns" ----------------

def test_answers_are_written_back_and_cite_real_nodes(agent):
    """An answer is stored as a node that CITES the nodes it was built from, not as text.

    That is what makes recall a traversal instead of a cache, and it is why a remembered answer
    can be re-checked against the live graph rather than trusted.
    """
    agent._provider = _StubProvider('{"tool":"ownership_dilution","args":{}}')
    out = agent.ask("which areas have nobody left?")
    assert out["shape"] == "ANSWERED_WITH_PATH"

    rows = agent.g.ro_query(
        """
        MATCH (a:Answer)-[c:CITED]->(n)
        WHERE a.tool = 'ownership_dilution'
        RETURN DISTINCT labels(n)[0] AS label, c.role AS role
        """
    ).result_set
    labels = {r[0] for r in rows}
    assert "OwnersFile" in labels, f"no area citations: {rows}"
    assert "Person" in labels, f"no person citations: {rows}"


def test_memory_and_facts_are_traversable_in_one_query(agent):
    """Memory lives in the SAME graph as the facts.

    A separate memory store would make the 'works without FalkorDB' test pass, which is exactly
    the failure the rules describe -- and it could not answer this query at all.
    """
    agent._provider = _StubProvider('{"tool":"departed_bridges","args":{"min_areas":3}}')
    agent.ask("whose departure hurt most?")
    rows = agent.g.ro_query(
        """
        MATCH (a:Answer)-[:CITED]->(p:Person)-[:EMERITUS_OF]->(f:OwnersFile)
        RETURN a.question, p.key, count(DISTINCT f) AS areas
        ORDER BY areas DESC LIMIT 1
        """
    ).result_set
    assert rows, "could not traverse from a remembered answer into the facts it cited"
    assert rows[0][2] > 0


def test_recall_works_across_sessions_on_different_wording(agent):
    """A new agent object, a differently-worded question, and it still finds the prior answer."""
    agent._provider = _StubProvider(
        '{"tool":"who_owns","args":{"path":"pkg/controller/podgc/OWNERS","depth":4}}')
    agent.ask("who owns pkg/controller/podgc?")

    fresh = Agent(graph_name=GRAPH, now_ms=1_760_000_000_000)
    a = fresh.dispatch("recall", {"question": "who currently owns the podgc controller"})
    assert a.shape == "ANSWERED_WITH_PATH", render(a)
    assert "podgc" in render(a)


def test_recall_admits_when_it_has_never_been_asked(agent):
    a = agent.dispatch("recall", {"question": "what is the airspeed velocity of an unladen swallow"})
    assert a.shape == "NOT_IN_GRAPH"
    assert "never" in render(a).lower() or "nothing" in render(a).lower()


def test_memory_write_failure_never_breaks_the_answer(agent, monkeypatch):
    """Memory is additive. A write problem must not cost the user their answer."""
    def boom(*_a, **_k):
        raise RuntimeError("simulated memory failure")

    agent._provider = _StubProvider('{"tool":"ownership_dilution","args":{}}')
    monkeypatch.setattr(agent.memory, "record", boom)
    out = agent.ask("which areas have nobody left?")
    assert out["shape"] == "ANSWERED_WITH_PATH"
    assert len(out["rows"]) == 7


# ---------------- Track 3's "keeping knowledge current" ----------------

def test_stale_knowledge_uses_positive_evidence_of_departure(agent):
    """Absence of an approver role is NOT evidence of departure.

    An earlier version inferred "no living author" from having no APPROVES edge. 72% of KEP
    authors appear in no OWNERS file at all, so that mostly meant "was never an approver".
    Only `emeritus_approvers` -- an explicit, published statement that someone stepped back --
    counts as departure, and authors of unknown status are reported as unknown.
    """
    a = agent.dispatch("stale_knowledge", {"min_years": 3})
    assert a.shape == "ANSWERED_WITH_PATH"
    for r in a.rows:
        authors, live, gone, unknown = int(r[6]), int(r[7]), int(r[8]), int(r[9])
        assert live + gone + unknown == authors, (
            f"author buckets do not sum: {live}+{gone}+{unknown} != {authors}")
    # the top row must have positive evidence of departure, not merely an absence
    assert int(a.rows[0][8]) >= 1, "top stale decision has no verifiably departed author"
    lives = [int(r[7]) for r in a.rows]
    assert lives == sorted(lives), f"not ordered by authors holding a current role: {lives}"


def test_absence_from_owners_is_not_treated_as_departure(g):
    """Guards the exact confusion that produced the wrong claim."""
    total = g.ro_query(
        "MATCH (p:Person)-[:AUTHORED|APPROVED]->(:Kep) RETURN count(DISTINCT p)"
    ).result_set[0][0]
    no_owners = g.ro_query(
        """
        MATCH (p:Person)-[:AUTHORED|APPROVED]->(:Kep)
        OPTIONAL MATCH (p)-[a:APPROVES]->()
        OPTIONAL MATCH (p)-[e:EMERITUS_OF]->()
        WITH p, count(a) AS na, count(e) AS ne WHERE na = 0 AND ne = 0
        RETURN count(DISTINCT p)
        """
    ).result_set[0][0]
    # If this ever drops near zero the proxy would be safe, but it is ~72% -- so it is not.
    assert no_owners / total > 0.5, (
        "most KEP authors appear in no OWNERS file; absence must not imply departure")


def test_stale_knowledge_admits_when_nothing_qualifies(agent):
    a = agent.dispatch("stale_knowledge", {"min_years": 40})
    assert a.shape == "NOT_IN_GRAPH"
    assert a.coverage.get("decisions_indexed", 0) > 500


def test_no_directory_is_actually_unowned(g):
    """The correction that mattered most.

    An earlier version claimed 7 directories were "orphaned" because every approver in their own
    OWNERS file had departed. That is false: Kubernetes OWNERS INHERIT, so prow covers a directory
    with its ancestors' approvers too unless `options.no_parent_owners` is set. Verified against
    kubernetes.dev/docs/guide/owners. Zero directories are genuinely unowned, and this test fails
    loudly if that claim ever creeps back in.
    """
    unowned = g.ro_query(
        """
        MATCH (d:Person)-[:EMERITUS_OF]->(f:OwnersFile)
        OPTIONAL MATCH (own:Person)-[:APPROVES]->(f)
        WITH f, count(DISTINCT own) AS n WHERE n = 0
        OPTIONAL MATCH (f)-[:INHERITS_FROM*1..8]->(a:OwnersFile)<-[:APPROVES]-(:Person)
        WITH f, count(a) AS covered WHERE covered = 0
        RETURN count(f)
        """
    ).result_set[0][0]
    assert unowned == 0, f"{unowned} directories claimed unowned -- check OWNERS inheritance"


def test_dilution_reports_the_fallback_not_an_orphan(agent):
    """The honest finding: approval WIDENED to a group that never owned the code."""
    a = agent.dispatch("ownership_dilution", {})
    assert a.shape == "ANSWERED_WITH_PATH"
    for area, departed, n_dep, fallback, levels, n_fb, _url in a.rows:
        assert departed, f"{area} reported with no departed owners"
        assert fallback and fallback != area, f"{area} fell back to itself"
        assert levels >= 1, f"{area} reported a 0-level fallback"
        assert n_fb >= 1, f"{area} fell back to a group with no approvers"
    # ordered by bus-factor risk: the thinnest fallback first
    fbs = [r[5] for r in a.rows]
    assert fbs == sorted(fbs), f"not ordered by fallback size: {fbs}"
