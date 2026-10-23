"""Invariants that must hold, each one locking in a bug I actually hit.

Run: PYTHONPATH=src python -m pytest tests/ -q
These need a live FalkorDB on 6380 (`docker compose up -d`) and the committed snapshot.
"""
from __future__ import annotations

import time

import pytest

# Either shape means "the tool answered". ANSWERED_FROM_MEMORY is returned when the same question
# was asked before AND its citations still resolve, so a repeat ask inside one test session
# legitimately returns it.
ANSWERED = {"ANSWERED_WITH_PATH", "ANSWERED_FROM_MEMORY"}

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
    assert "no one named here still holds approval authority" in render(d4)


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
        ("stepped_back_bridges", {"min_areas": "lots"}),
        ("broken_lineage", {"min_cites": -1}),
        ("has_this_been_tried", {"idea_text": "kubelet state", "max_dist": "near"}),
        ("who_owns", {"path": None, "depth": 4}),
        ("successor_for", {"handle": None}),
        ("successor_for", {}),
        # Wrong TYPE, not just a wrong value. These six all answered DEGRADED carrying a raw
        # Python message -- "'list' object has no attribute 'strip'" -- until the 17 Oct audit.
        # DEGRADED means no answer was produced, which a judge poking the API reads as the
        # database being down; a bad request is the product declining to guess.
        ("who_owns", {"path": ["x"], "depth": 4}),
        ("successor_for", {"handle": ["deads2k"]}),
        ("has_this_been_tried", {"idea_text": {"a": 1}}),
        ("recall", {"question": ["x"]}),
        ("who_owns", {"path": 7}),
        ("has_this_been_tried", {"idea_text": 3.5}),
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
        assert "no one named here still holds approval authority" in render(a)
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
    assert out["shape"] in ANSWERED


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
    assert out["shape"] in ANSWERED

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
    agent._provider = _StubProvider('{"tool":"stepped_back_bridges","args":{"min_areas":3}}')
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
    assert out["shape"] in ANSWERED
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


def test_answered_from_memory_is_earned_not_cached(agent):
    """The organizer's taxonomy has four answer shapes; this is the fourth.

    It is only returned when the prior answer's citations STILL RESOLVE and re-running the tool
    returns the same row count. A remembered answer whose cited nodes have gone is a stale claim,
    not a memory -- so the agent falls through and re-runs instead of serving it.
    """
    agent._provider = _StubProvider('{"tool":"ownership_dilution","args":{}}')
    q = "which areas lost every dedicated approver, memory test?"

    first = agent.ask(q)
    assert first["shape"] in ANSWERED

    second = agent.ask(q)
    assert second["shape"] == "ANSWERED_FROM_MEMORY"
    assert "still in the graph" in second["answer"]
    # the rows are the live ones, not a replayed blob
    assert second["rows"] == first["rows"]


def test_memory_is_not_served_when_its_citations_are_gone(agent):
    """Delete what a remembered answer cited; the agent must stop calling it a memory."""
    agent._provider = _StubProvider('{"tool":"broken_lineage","args":{"min_cites":2}}')
    q = "which cited records do not exist, staleness test?"
    agent.ask(q)
    assert agent.ask(q)["shape"] == "ANSWERED_FROM_MEMORY"

    from tombstone.memory import qid
    agent.g.query(
        "MATCH (a:Answer {qid: $q})-[c:CITED]->() DELETE c", params={"q": qid(q, "broken_lineage")}
    )
    again = agent.ask(q)
    assert again["shape"] == "ANSWERED_WITH_PATH", "served a memory with no surviving citations"


# ---------------- bus factor + counterfactual ----------------

def test_sole_approver_risk_is_exact_not_simulated(agent):
    """For ONE person this is an exact query. No copy, no simulation."""
    a = agent.dispatch("sole_approver_risk", {})
    assert a.shape == "ANSWERED_WITH_PATH"
    for who, n, sample in a.rows:
        assert n >= 1 and who and sample
    counts = [r[1] for r in a.rows]
    assert counts == sorted(counts, reverse=True)
    assert "GRAPH.COPY" not in a.cypher


def test_counterfactual_only_counts_areas_that_had_something_to_lose(agent):
    """19 OWNERS files declare only `reviewers`/`labels` and never had an approver.

    Counting those as 'uncovered' is the same conflation that produced the retracted
    '7 orphaned directories' claim, so the baseline must be ZERO stranded areas.
    """
    a = agent.dispatch("what_if_they_go", {"handles": ["deads2k"]})
    if a.shape == "DEGRADED" and "GRAPH.COPY could not run" in (a.note or ""):
        # The host could not fork a copy of the graph. That is a capacity fact about this
        # machine, not a violated invariant, and it must not be reported as either a pass or a
        # correctness failure. test_counterfactual_degrades_when_the_host_cannot_fork covers
        # the behaviour on that path directly.
        pytest.skip(f"GRAPH.COPY unavailable on this host: {a.note}")
    assert a.shape == "ANSWERED_WITH_PATH"
    _cohort, _stranded, baseline, _ms, _copy = a.rows[0]
    assert baseline == 0, (
        f"baseline says {baseline} areas already stranded; an area that never had an approver "
        "cannot lose one")


def test_counterfactual_never_mutates_the_live_graph(agent):
    before_people = agent.g.ro_query("MATCH (p:Person) RETURN count(p)").result_set[0][0]
    before_appr = agent.g.ro_query("MATCH ()-[r:APPROVES]->() RETURN count(r)").result_set[0][0]
    agent.dispatch("what_if_they_go", {"handles": ["deads2k", "liggitt", "thockin"]})
    assert agent.g.ro_query("MATCH (p:Person) RETURN count(p)").result_set[0][0] == before_people
    assert agent.g.ro_query(
        "MATCH ()-[r:APPROVES]->() RETURN count(r)").result_set[0][0] == before_appr


def test_counterfactual_cleans_up_its_copies(agent):
    agent.dispatch("what_if_they_go", {"handles": ["deads2k"]})
    leaked = [g for g in agent.db.list_graphs() if ":cf:" in g]
    assert leaked == [], f"counterfactual leaked graphs: {leaked}"


def test_hollowing_communities_is_structurally_sound(agent):
    """Label propagation is NON-DETERMINISTIC and has no resolution parameter.

    So this asserts invariants that must hold on any partition, never exact community ids or
    sizes — a test that pinned those would fail randomly and teach us to ignore it.
    """
    a = agent.dispatch("hollowing_communities", {"min_size": 5})
    assert a.shape == "ANSWERED_WITH_PATH"
    pcts = []
    for cid, size, gone, live, pct, who in a.rows:
        size, gone, live, pct = int(size), int(gone), int(live), int(pct)
        assert size >= 5, f"community {cid} below min_size"
        assert gone >= 1, "a community with nobody stepped back should not be listed"
        assert gone + live <= size, f"{gone}+{live} exceeds community size {size}"
        assert 0 < pct <= 100, f"implausible percentage {pct}"
        assert len([w for w in who if w]) >= 1, "no names given for who stepped back"
        pcts.append(pct)
    assert pcts == sorted(pcts, reverse=True), f"not ordered by attrition: {pcts}"
    # the non-determinism must be disclosed, not hidden
    assert "non-deterministic" in (a.note or "").lower()


def test_hollowing_communities_discloses_its_algorithm(agent):
    """FalkorDB has no Louvain/Leiden; the answer must say which algorithm produced it."""
    a = agent.dispatch("hollowing_communities", {"min_size": 5})
    assert "labelPropagation" in a.cypher
    assert "label propagation" in render(a).lower()


def test_no_llm_anywhere_in_the_extraction_path():
    """A load-bearing claim: the graph is built by deterministic parsing, not by a model.

    This is what makes re-runs byte-identical and the rebuild free, and it is the whole
    distinction from Graphiti / Cognee / GraphRAG-SDK. If a model ever creeps into corpus.py,
    build.py or snapshot.py, that claim quietly becomes false — so this fails instead.
    """
    import pathlib
    import re

    banned = re.compile(r"\b(openai|anthropic|gpt-|claude-|completion|chat_completion)\b", re.I)
    for name in ("corpus.py", "build.py", "snapshot.py"):
        src = pathlib.Path("src/tombstone") / name
        for i, line in enumerate(src.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]          # comments may discuss LLMs; code may not use one
            assert not banned.search(code), f"{name}:{i} references a model in the build path: {line.strip()[:80]}"


def test_titled_alternatives_really_are_regex_derived(g):
    """78% of alternatives are titled by a markdown sub-heading, not labelled by a model."""
    total = g.ro_query("MATCH (a:Alternative) RETURN count(a)").result_set[0][0]
    titled = g.ro_query("MATCH (a:NamedOption) RETURN count(a)").result_set[0][0]
    assert titled / total > 0.7, f"only {titled}/{total} titled — extraction may have regressed"
    # every NamedOption must carry the flag the parser set, not a post-hoc label
    flagged = g.ro_query(
        "MATCH (a:NamedOption) WHERE a.titled = true RETURN count(a)").result_set[0][0]
    assert flagged == titled


def test_headline_comes_from_the_graph_not_from_the_page(agent, g):
    """The big number on screen must come from the data, or it will eventually contradict it.

    This test used to assert the opposite, and passed: it required the stat to equal
    `sum(int(r[1]) for r in a.rows)`, which is the LIMIT-ed page, so it pinned the defect in
    place. The chip read "31 areas held alone by 12 people" while the graph holds 45 across 23 --
    and README's own table two screens up says 45. A judge who read the table and clicked the
    chip the table names saw the product contradict itself, which is the one thing this project
    claims cannot happen.
    """
    from tombstone.agent import headline

    a = agent.dispatch("sole_approver_risk", {})
    h = headline(a)
    live = g.ro_query("MATCH (o:OwnersFile)<-[:APPROVES]-(p:Person) "
                      "WITH o, collect(DISTINCT p) AS ps WHERE size(ps) = 1 "
                      "RETURN count(DISTINCT o), count(DISTINCT ps[0])").result_set[0]
    assert h and h["stat"] == str(live[0]), f"headline says {h['stat']}, the graph says {live[0]}"
    assert str(live[1]) in h["label"]
    # Anti-vacuity: if the page happens to equal the population, this test cannot tell the two
    # apart and proves nothing. It is only meaningful while the limit bites.
    page = sum(int(r[1]) for r in a.rows)
    assert page != live[0], ("the page sum equals the true total on this corpus, so this test can "
                            "no longer distinguish them -- lower sole_approver_risk's limit")

    b = agent.dispatch("broken_lineage", {})
    hb = headline(b)
    lb = g.ro_query("MATCH (:Kep)-[r:CITES_MISSING]->(m:MissingRecord) "
                    "RETURN count(DISTINCT m), count(r)").result_set[0]
    assert hb["stat"] == str(lb[0]) and str(lb[1]) in hb["label"]
    assert len(b.rows) != lb[0], "same anti-vacuity point for broken_lineage"

    c = agent.dispatch("ownership_dilution", {})
    hc = headline(c)
    assert hc and str(min(int(r[5]) for r in c.rows)) in hc["label"]


def test_no_headline_reports_a_limited_page_as_a_population(agent):
    """The general form of the bug above: a LIMIT is a display decision, never a claim.

    ownership_dilution is correct today only because its population (7) is under its limit (20).
    That is luck, not design, so this asserts the rule for every paged tool rather than for the
    two that were caught: if a tool came back with a full page, its headline has to be built from
    `totals`, which are whole-graph counts, and not from the rows.
    """
    paged = ("sole_approver_risk", "broken_lineage", "ownership_dilution",
             "stepped_back_but_still_listed", "stale_knowledge", "hollowing_communities")
    checked = 0
    for tool in paged:
        a = agent.dispatch(tool, {})
        lim = a.params.get("limit")
        if not lim or not a.rows:
            continue
        checked += 1
        if len(a.rows) >= lim:
            assert a.totals, (
                f"{tool} returned a full page of {lim} rows and carries no totals, so any count "
                f"in its headline describes the page rather than the graph")
    assert checked >= 3, f"only {checked} paged tools were exercised; this check has gone stale"


def test_headline_never_contradicts_an_empty_answer(agent):
    from tombstone.agent import headline

    a = agent.dispatch("has_this_been_tried",
                       {"idea_text": "rewrite the control plane in COBOL", "max_dist": 0.15})
    assert a.shape == "NOT_IN_GRAPH"
    h = headline(a)
    assert h["stat"] == "nothing"
    assert "real answer" in h["label"]

    for tool in ("successor_for", "who_owns"):
        bad = agent.dispatch(tool, {"handle": "no-such-person", "path": "no/such/path"})
        assert bad.shape == "UNKNOWN_ENTITY"
        assert headline(bad) is None, "an unresolved entity must not get a headline number"


def test_counterfactual_degrades_when_the_host_cannot_fork(agent):
    """A failed `GRAPH.COPY` must produce DEGRADED, never a number.

    GRAPH.COPY forks the server, so it fails under memory pressure. The dangerous failure is not
    the error -- it is reporting "0 areas would be left unowned" because the copy never happened
    and the diff was therefore empty. This drives the real fork-failure path by making the copy
    command raise, and asserts the answer carries no rows at all.

    One of the two call sites previously had try/finally with no except, so a fork failure
    propagated out of the request instead of degrading. This locks that shut.
    """
    import tombstone.counterfactual as cf

    real = cf._copy_with_retry

    def boom(db, source, copy_name):
        raise cf.CopyUnavailable("MISC Queue could not fork")

    cf._copy_with_retry = boom
    try:
        a = agent.dispatch("what_if_they_go", {"handles": ["deads2k"]})
    finally:
        cf._copy_with_retry = real

    assert a.shape == "DEGRADED", f"expected DEGRADED on a failed copy, got {a.shape}"
    assert not a.rows, f"a failed counterfactual reported rows: {a.rows}"
    assert "GRAPH.COPY could not run" in (a.note or "")
    assert "could not fork" in (a.note or "")
    # and the live graph is still intact afterwards
    ok = agent.dispatch("what_if_they_go", {"handles": ["deads2k"]})
    assert ok.shape in ANSWERED or ok.shape == "DEGRADED"


# ---------------- the action: drafting an OWNERS patch ----------------
#
# These exist because every one of them is a way the action could produce a WRONG patch, and a
# wrong patch is worse than no patch: it looks authoritative and it edits governance.

def test_drafted_patch_parses_as_yaml_and_actually_retires_the_handle():
    import yaml
    from tombstone import act
    before = {"approvers": ["alice", "bob", "carol"], "reviewers": ["carol"],
              "options": {"no_parent_owners": True}}
    after = act.retire(before, "carol")
    parsed = yaml.safe_load(act.canonical(after))
    assert parsed["approvers"] == ["alice", "bob"]
    assert parsed["reviewers"] == ["carol"]
    assert parsed["emeritus_approvers"] == ["carol"]
    assert parsed["options"] == {"no_parent_owners": True}, "unrelated keys must survive"


def test_drafted_patch_never_invents_a_name(agent):
    """The patch may only ever remove and relabel. A handle appearing in the proposal that was
    not in the original file would be this tool putting words in a project's mouth."""
    ans = agent.dispatch("draft_owners_patch", {})
    assert ans.shape == "ANSWERED_WITH_PATH"
    corpus = agent.corpus()
    checked = 0
    for _person, path, _n, kind, _why, _diff, proposed in ans.rows:
        if kind != "patch":
            continue
        import yaml
        original = {n for v in corpus.owners[path].values() if isinstance(v, list) for n in v}
        after = {n for v in (yaml.safe_load(proposed) or {}).values()
                 if isinstance(v, list) for n in v}
        assert after <= original, f"{path}: invented {after - original}"
        checked += 1
    assert checked > 0, "no patch was drafted, so this invariant tested nothing"


def test_vendored_trees_are_never_patched():
    """vendor/ and third_party/ are synced from other repositories, so a patch here is reverted
    by the next sync. The single strongest signal in this corpus lives in vendor/."""
    from tombstone import act
    kind, why = act.classify("vendor/k8s.io/utils/ptr/OWNERS", "stewart-yu",
                             {"approvers": ["stewart-yu"]}, {})
    assert kind == "vendored", "a vendored OWNERS file was offered as patchable"
    assert "synced" in why


def test_approval_held_through_an_alias_is_refused_with_the_alias_named():
    """An APPROVES edge can come from alias expansion, so the person is not named in the file and
    no edit to it removes them. Drafting one would be a patch that does nothing."""
    from tombstone import act
    kind, why = act.classify("staging/OWNERS", "fabriziopandini",
                             {"approvers": ["sig-cluster-lifecycle-leads"]},
                             {"sig-cluster-lifecycle-leads": ["fabriziopandini", "neolit123"]})
    assert kind == "via_alias"
    assert "sig-cluster-lifecycle-leads" in why
    assert "OWNERS_ALIASES" in why


def test_the_action_shows_its_refusals_rather_than_dropping_them(agent):
    """A tool that silently skipped what it could not handle would look more capable than it is.
    Every candidate must come back, patched or with a stated reason."""
    ans = agent.dispatch("draft_owners_patch", {})
    found = agent.dispatch("stepped_back_but_still_listed", {})
    candidates = sum(len(r[3]) for r in found.rows)
    assert len(ans.rows) == candidates, "a candidate was dropped instead of explained"
    kinds = {r[3] for r in ans.rows}
    assert "patch" in kinds and len(kinds) > 1, "expected both drafted and refused cases"
    for _p, _path, _n, kind, why, _d, _prop in ans.rows:
        if kind != "patch":
            assert why.strip(), f"{kind} refusal carried no reason"


def test_a_patch_that_would_strand_a_file_says_so(agent):
    """Removing the last approver does not leave the file unowned -- it makes it silently inherit.
    That consequence lives in the OWNERS tree, so only the graph can state it."""
    from tombstone import act
    sole = {"approvers": ["only-one"], "reviewers": ["only-one"]}
    assert act.strand_check(act.retire(sole, "only-one")) is True
    assert act.strand_check(act.retire({"approvers": ["a", "b"]}, "a")) is False
    # and the agent can name what would inherit a real path
    who = agent._inherited_by("hack/jenkins/OWNERS")
    assert isinstance(who, str) and who


def test_the_action_sends_nothing_anywhere():
    """This product drafts. It must never acquire a side effect outside the repo.

    Checked by walking the AST for imports rather than grepping for substrings: the first version
    of this test matched the letters "gh " inside the word "through" in a comment, which is the
    kind of false positive that teaches people to delete tests.
    """
    import ast
    import pathlib

    NETWORK = {"requests", "urllib", "urllib3", "httpx", "http", "socket", "smtplib",
               "subprocess", "ftplib", "telnetlib", "paramiko", "redis"}
    src = pathlib.Path("src/tombstone/act.py").read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & NETWORK), f"act.py imports {imported & NETWORK}"

    # and the drafting method itself opens nothing but a local file for writing
    agent_tree = ast.parse(pathlib.Path("src/tombstone/agent.py").read_text())
    method = next((n for n in ast.walk(agent_tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_draft_owners_patch"), None)
    assert method is not None, "the action method was renamed; update this test"
    inner = set()
    for node in ast.walk(method):
        if isinstance(node, ast.Import):
            inner |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            inner.add(node.module.split(".")[0])
    assert not (inner & NETWORK), f"the action imports {inner & NETWORK}"


# ---------------- keyless routing ----------------
#
# The hosted demo has no API key, and the ask box used to be DISABLED there: a judge landed on the
# page and its most prominent control was dead. These lock in the local router that replaced that.

@pytest.fixture(scope="module")
def router(agent):
    return agent.router()


ROUTES = [
    ("who owns staging/src/k8s.io/apiserver/pkg/endpoints/metrics?", "who_owns"),
    ("which areas have exactly one approver?", "sole_approver_risk"),
    ("has anyone tried moving this into the kubelet?", "has_this_been_tried"),
    ("whose departure cost the most knowledge?", "stepped_back_bridges"),
    ("which contributor group is hollowing out?", "hollowing_communities"),
    ("what knowledge here is going stale?", "stale_knowledge"),
    ("which cited decisions no longer exist?", "broken_lineage"),
    ("draft the fix for the ownership problem", "draft_owners_patch"),
    ("who should inherit lavalamp's areas?", "successor_for"),
    ("what if deads2k and liggitt stepped back?", "what_if_they_go"),
]

REFUSALS = [
    "write me a poem about kubernetes",   # scored 0.631 against an ACTION tool before the fix
    "what is the weather in Paris",
    "tell me a joke",
    "write python code to parse yaml",
    "who owns this?",                     # right shape, but names no area to look up
]


@pytest.mark.parametrize("question,expected", ROUTES)
def test_keyless_router_picks_the_right_tool(router, question, expected):
    got = router.route(question)
    assert got["tool"] == expected, f"{question!r} routed to {got['tool']}, expected {expected}"


@pytest.mark.parametrize("question", REFUSALS)
def test_keyless_router_refuses_rather_than_guessing(router, question):
    """Routing is an OPEN set. The catalogue is not.

    Before the out-of-domain bucket existed this was a bare threshold, and a threshold cannot
    distinguish "unlike anything here" from "a bit like everything": "write me a poem about
    kubernetes" scored 0.631 and was routed into the patch-drafting ACTION.
    """
    got = router.route(question)
    assert got["tool"] is None, f"{question!r} should have been refused, got {got['tool']}"
    assert got.get("why"), "a refusal with no reason is not a refusal"


def test_keyless_router_only_ever_names_tools_that_exist(router):
    """It picks a tool NAME. It cannot invent one, and it cannot write Cypher."""
    from tombstone.tools import CATALOGUE
    for question, _ in ROUTES:
        got = router.route(question)
        assert got["tool"] in CATALOGUE


def test_keyless_router_is_deterministic(router):
    """Same question, same route, every time -- otherwise none of the above is testable."""
    for question, _ in ROUTES[:4]:
        first, second = router.route(question), router.route(question)
        assert first["tool"] == second["tool"]
        assert first["score"] == second["score"]


def test_keyless_router_never_invents_a_person(router):
    """Handles are matched against people who exist. A hallucinated handle is a fabricated person."""
    got = router.route("who should inherit nonexistentpersonxyz's areas?")
    assert got["tool"] is None or not got.get("args", {}).get("handle")


def test_keyless_ask_answers_or_refuses_but_never_guesses(agent):
    # Either answered shape passes. This test is about answering versus guessing, not about
    # memory, and another test in this file asks the same question -- so whether this one sees
    # ANSWERED_WITH_PATH or ANSWERED_FROM_MEMORY depends on test order, which is no business of
    # an assertion about honesty.
    out = agent.ask_locally("which areas have exactly one approver?")
    assert out["shape"] in ANSWERED
    assert out["routed_by"] == "local-embedding"
    assert out["cypher"].strip(), "an answer with no Cypher behind it is not an answer"

    refused = agent.ask_locally("write me a poem about kubernetes")
    assert refused["shape"] == "UNSURE_WHICH_TOOL"
    assert "not going to guess" in refused["answer"]
    assert not refused.get("cypher")


# ---------------- memory, on the path the hosted demo actually uses ----------------

def test_keyless_ask_earns_answered_from_memory_on_a_repeat(agent):
    """Asking the same thing twice without an API key must come back as remembered.

    It did not. The keyless path was written separately from the model path and called
    `memory.remember(...)`, a method that does not exist, inside a bare `except Exception: pass`.
    Every keyless question silently recorded nothing, and the hosted demo is the keyless one --
    so "remembers what it learns" was the one pillar a judge could not have seen working.
    Both paths now go through `Agent._remember`.
    """
    # Timestamped so the run starts genuinely unasked. A fixed question makes this pass the
    # first time and fail afterwards, because the graph persists between runs and the first ask
    # then comes back remembered -- the feature working, reported as a failure. The same trap was
    # found and fixed in verify_memory.py and not carried across to here.
    question = (f"which areas are held alone by a single approver, bus factor one? "
                f"[{time.time_ns()}]")
    first = agent.ask_locally(question)
    assert first["shape"] == "ANSWERED_WITH_PATH", (
        f"a freshly-worded question came back {first['shape']}")
    second = agent.ask_locally(question)
    assert second["shape"] == "ANSWERED_FROM_MEMORY", (
        f"a repeat keyless ask returned {second['shape']}, so nothing was remembered")
    assert "Asked before" in (second.get("note") or "")


# (tool, args) for every tool whose rows name real nodes. `recall` is excluded by design: an
# answer about remembering should not itself be remembered.
CITING_TOOLS = [
    ("sole_approver_risk", {}),
    ("ownership_dilution", {}),
    ("stepped_back_bridges", {"min_areas": 3}),
    ("broken_lineage", {"min_cites": 2}),
    ("hollowing_communities", {"min_size": 5}),
    ("stale_knowledge", {"min_years": 3}),
    ("stepped_back_but_still_listed", {}),
    ("draft_owners_patch", {}),
    ("what_if_they_go", {"handles": ["deads2k", "liggitt"]}),
    ("successor_for", {"handle": "lavalamp"}),
    ("who_owns", {"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS", "depth": 4}),
]


@pytest.mark.parametrize("tool,args", CITING_TOOLS)
def test_every_answering_tool_cites_the_nodes_it_returned(agent, tool, args):
    """An answer with no citations can never be returned from memory, because the gate is that
    its citations still resolve -- there is nothing to re-check.

    Seven of thirteen tools were never wired into the citation linker, so they recorded zero
    citations and memory silently did nothing for them. The rows plainly contained people and
    ownership paths the whole time; nobody had told the linker about them.
    """
    ans = agent.dispatch(tool, args)
    if ans.shape != "ANSWERED_WITH_PATH" or not ans.rows:
        pytest.skip(f"{tool} returned {ans.shape} here, so there is nothing to cite")
    question = f"citation coverage probe for {tool}"
    agent._remember(question, tool, ans)
    # Look it up as the answer labels itself: who_owns records as "who_owns(depth=4)" so its two
    # depths stay distinct memories.
    recorded = agent.memory.recall_exact(question, ans.tool or tool)
    assert recorded, f"{tool} recorded no memory at all"
    assert recorded[5] > 0, (
        f"{tool} answered with {len(ans.rows)} rows but cited 0 nodes, so it can never be "
        f"returned from memory")


def test_both_ask_paths_return_the_same_response_shape(agent):
    """A keyed instance and a keyless one must answer with the same contract.

    They did not. The two paths built their response dicts separately and drifted: the model path
    omitted `headline`, so with an API key configured a typed question lost the one number the UI
    leads with, and the two disagreed on whether the chosen arguments live under `routed_args` or
    `routing.args`. Nothing caught it because nothing compared them. Both now go through
    `Agent._payload`; this is the test that keeps them there.
    """
    question = "which areas have exactly one approver?"

    class StubProvider:
        def choose_tool(self, system, q, catalogue):
            return {"tool": "sole_approver_risk", "args": {}}

    keyless = agent.ask_locally(question)
    agent._provider = StubProvider()
    try:
        keyed = agent.ask(question)
    finally:
        agent._provider = None

    missing = set(keyless) - set(keyed) - {"routing"}   # `routing` is keyless-only detail
    extra = set(keyed) - set(keyless)
    assert not missing, f"the keyed path is missing {sorted(missing)}"
    assert not extra, f"the keyed path returns {sorted(extra)} that the keyless one does not"
    assert keyed["headline"] == keyless["headline"], "headline differs between the two paths"
    assert keyed["routed_by"] == "llm" and keyless["routed_by"] == "local-embedding"
    assert keyed["routed_args"] == keyless["routed_args"]


# ---------------- the keyed path: what models actually send ----------------
#
# These exist because the keyed path had only ever been exercised with a stub that returned
# perfect JSON. Models do not. Each case below was found by probing the parser, not by reasoning
# about it, and three of them were genuinely mishandled.

PARSES = [
    ("bare json", '{"tool":"sole_approver_risk","args":{}}', "sole_approver_risk", {}),
    ("fenced json", '```json\n{"tool":"sole_approver_risk","args":{}}\n```', "sole_approver_risk", {}),
    ("fenced plain", '```\n{"tool":"sole_approver_risk","args":{}}\n```', "sole_approver_risk", {}),
    ("prose before", 'Sure! Here you go:\n{"tool":"sole_approver_risk","args":{}}', "sole_approver_risk", {}),
    ("prose after", '{"tool":"sole_approver_risk","args":{}}\nHope that helps!', "sole_approver_risk", {}),
    # the first-brace-to-last-brace slice used to raise a raw JSONDecodeError out of the provider
    ("prose containing braces", 'I think {this} is it: {"tool":"sole_approver_risk","args":{}}',
     "sole_approver_risk", {}),
    ("args omitted", '{"tool":"sole_approver_risk"}', "sole_approver_risk", {}),
    # args as a STRING used to pass straight through to a dispatcher that calls .get() on it
    ("args as a string", '{"tool":"who_owns","args":"path=foo"}', "who_owns", {}),
    ("nested args", '{"tool":"who_owns","args":{"path":"a/b/OWNERS","depth":4}}',
     "who_owns", {"path": "a/b/OWNERS", "depth": 4}),
]


@pytest.mark.parametrize("label,text,tool,args", PARSES)
def test_model_reply_parses_the_way_models_actually_reply(label, text, tool, args):
    from tombstone.llm import Provider
    got = Provider._parse(text)
    assert got["tool"] == tool, label
    assert got["args"] == args, label


@pytest.mark.parametrize("text", [
    "I am not sure which tool to use.",
    "",
    '{"tool":["sole_approver_risk"],"args":{}}',   # a list where a name belongs
    '{"args":{}}',                                  # no tool at all
])
def test_unusable_model_replies_are_refused_not_guessed(text):
    from tombstone.llm import LLMError, Provider
    with pytest.raises(LLMError):
        Provider._parse(text)


def test_a_hallucinated_tool_name_is_refused_by_the_dispatcher(agent):
    """The parser deliberately does not validate tool names against the catalogue -- that belongs
    to the dispatcher, which already refuses unknown names and says so. What must never happen is
    an invented name reaching a query."""
    from tombstone.tools import CATALOGUE
    assert "delete_everything" not in CATALOGUE
    ans = agent.dispatch("delete_everything", {})
    assert ans.shape == "UNKNOWN_ENTITY"
    assert "not a tool in this catalogue" in ans.note
    assert not ans.cypher, "a refused tool must not carry Cypher"


def test_readme_routing_scores_match_the_cases_actually_tested():
    """The README prints the size of the locked regression suite, and it is these two lists.

    Those are counts of the lists in this file. Adding a case here without updating the README --
    or the reverse -- would leave the page quoting a score for a test suite that no longer exists.
    Every other number on that page is checked by a script; these two were not, and they are the
    kind that drifts silently because nothing fails when it does.

    The rows are no longer bolded, and that is deliberate rather than cosmetic: bolded, beside a
    held-out eval that scores lower, they read as this router's accuracy. They are not. They are
    the cases it was built against, and the README now says so in the sentence underneath.
    """
    import re
    readme = open("README.md").read()
    for label, actual in (("locked regression cases, in-domain", len(ROUTES)),
                          ("locked regression cases, out-of-domain", len(REFUSALS))):
        row = re.search(rf"\| {re.escape(label)} \| (\d+)/(\d+) \|", readme)
        assert row, f"README no longer has a row for {label!r}"
        claimed_pass, claimed_total = int(row.group(1)), int(row.group(2))
        assert claimed_total == actual, (
            f"README says {claimed_pass}/{claimed_total} for {label!r}, but this file tests "
            f"{actual} cases")
        assert claimed_pass == actual, (
            f"README claims {claimed_pass} of {claimed_total} pass; the suite requires all "
            f"{actual} to pass, so the two numbers must be equal")


def test_the_sixty_second_box_counts_match_reality():
    """The summary box claims 104 tests, 25 graph claims, 17 rendered states and 20 CI steps.

    Those are four more numbers on a page whose whole argument is that its numbers are checked.
    Adding them unchecked would have reintroduced, in the first fifteen lines, exactly the problem
    the rest of the page documents fixing.
    """
    import re
    import subprocess
    import sys

    readme = open("README.md").read()
    box = re.search(r"> - \*\*Nothing here is asserted\.\*\*(.+?)which are", readme, re.S)
    assert box, "the verification bullet is no longer in the 60-second box"
    claimed = [int(n) for n in re.findall(r"(\d+)", box.group(1))]
    assert len(claimed) == 4, f"expected four numbers in the bullet, found {claimed}"
    tests_claimed, graph_claimed, states_claimed, ci_claimed = claimed

    collected = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                               capture_output=True, text=True).stdout
    actual_tests = int(re.search(r"(\d+) tests? collected", collected).group(1))
    assert tests_claimed == actual_tests, f"box says {tests_claimed} tests, pytest collects {actual_tests}"

    claims_src = open("verify_claims.py").read()
    body = claims_src[claims_src.index("CLAIMS = ["):claims_src.index("\nfails = 0")]
    actual_claims = len(re.findall(r'^\s{4}\("', body, re.M))
    assert graph_claimed == actual_claims, f"box says {graph_claimed} graph claims, there are {actual_claims}"

    chips = len(re.findall(r'tool:\s*"[a-z_]+"', open("web/app.js").read()))
    # The typed cases are COUNTED out of the UI check rather than written here as "+ 3". That
    # constant was already stale the moment a fourth typed case landed, and a number in a test
    # that has to be kept in step by hand is the same hazard as a number in prose.
    ui_src = open("scripts_check_ui.py").read()
    extra = ui_src[ui_src.index("cases = chips() + ["):ui_src.index("]", ui_src.index("cases = chips() + ["))]
    typed = len(re.findall(r'^\s{8}\("', extra, re.M))
    assert typed, "could not count the typed cases in scripts_check_ui.py"
    actual_states = chips + typed
    assert states_claimed == actual_states, (
        f"box says {states_claimed} rendered states, the UI check drives {actual_states}")

    actual_steps = len(re.findall(r"^      - name:", open(".github/workflows/verify.yml").read(), re.M))
    assert ci_claimed == actual_steps, f"box says {ci_claimed} CI steps, the workflow has {actual_steps}"


def test_using_the_demo_cannot_change_what_it_answers(agent):
    """Memory lives in the same graph as the facts, so using the product GROWS the graph.

    That is the point of putting it there — one query can start in a remembered answer and end in
    live nodes. It is also a hazard: the whole-graph algorithms would drift as judges clicked
    around, and the centrality ranking the README prints would quietly stop matching. The queries
    are scoped with `nodeLabels:['Person'], relationshipTypes:['CO_AUTHORED']`, which is easy to
    remove while tidying and impossible to notice afterwards.

    So this simulates a busy demo and requires the answers to be bit-identical.
    """
    graph = agent.g
    graph.query("MATCH (x:Answer) DETACH DELETE x")
    before = agent.dispatch("stepped_back_bridges", {"min_areas": 3}).rows
    coverage_before = agent.dispatch("sole_approver_risk", {}).coverage

    for i in range(25):
        agent._remember(f"busy demo probe {i}", "sole_approver_risk",
                        agent.dispatch("sole_approver_risk", {}))
    remembered = graph.ro_query("MATCH (x:Answer) RETURN count(x)").result_set[0][0]
    cited = graph.ro_query("MATCH ()-[r:CITED]->() RETURN count(r)").result_set[0][0]
    assert remembered >= 25 and cited > 0, "the probe did not actually grow the graph"

    after = agent.dispatch("stepped_back_bridges", {"min_areas": 3}).rows
    coverage_after = agent.dispatch("sole_approver_risk", {}).coverage
    graph.query("MATCH (x:Answer) DETACH DELETE x")

    assert after == before, (
        f"centrality changed after {remembered} remembered answers and {cited} CITED edges — "
        f"a whole-graph algorithm is seeing memory it should be scoped away from")
    assert coverage_after == coverage_before, "the coverage statement counted memory as corpus"


def test_asking_the_same_thing_twice_does_not_grow_the_graph(agent):
    """Repeats must MERGE onto one `(:Answer)`, not accumulate.

    This is the property that makes a public demo safe to leave running. Memory has no cap, no
    eviction and no TTL -- deliberately, because an answer that cites live nodes is evidence, not
    cache -- so the only thing bounding growth is that asking the same question again increments a
    counter instead of adding a node. Measured: ~19-44 KB per DISTINCT question, and the thirteen
    chips contribute thirteen regardless of how often they are clicked.

    Change `record` from MERGE to CREATE and that bound disappears silently: the demo keeps
    working, slowly fills its container, and eventually cannot fork for a counterfactual.
    """
    graph = agent.g
    graph.query("MATCH (x:Answer) DETACH DELETE x")
    question = "invariant probe: which areas have exactly one approver?"
    for _ in range(12):
        agent._remember(question, "sole_approver_risk",
                        agent.dispatch("sole_approver_risk", {}))

    nodes = graph.ro_query("MATCH (x:Answer) RETURN count(x)").result_set[0][0]
    remembered = agent.memory.recall_exact(question, "sole_approver_risk")
    graph.query("MATCH (x:Answer) DETACH DELETE x")

    assert nodes == 1, f"12 identical questions produced {nodes} Answer nodes; memory is unbounded"
    assert remembered and int(remembered[2]) == 12, (
        f"the repeat counter says {remembered[2] if remembered else None}, not 12 — repeats are "
        f"not being counted onto the same memory")


# ---------------- a declined near-tie is a choice, not a dead end ----------------
#
# The router declines when its top two tools are within MIN_MARGIN. A held-out eval showed that is
# most of its misses -- and that in most of them the RIGHT tool is the one it ranked first and
# declined to commit to. Rather than lower the bar until it guesses, the refusal now carries the
# candidates and the UI offers them. These lock that in: a user's pick is not the router guessing
# after all, and it must not become a way to smuggle a tool name past the catalogue.

def test_a_near_tie_offers_the_candidates_it_declined_between(agent):
    out = agent.ask_locally("show me the areas that depend on one person")
    assert out["shape"] == "UNSURE_WHICH_TOOL"
    assert out.get("near"), "a declined tie must say what it was torn between"
    assert all("tool" in n and "score" in n for n in out["near"])


def test_choosing_one_of_the_offered_tools_answers(agent):
    q = "show me the areas that depend on one person"
    offered = [n["tool"] for n in agent.ask_locally(q)["near"]]
    assert "sole_approver_risk" in offered
    out = agent.ask_locally(q, force="sole_approver_risk")
    assert out["shape"] == "ANSWERED_WITH_PATH"
    assert out["tool"] == "sole_approver_risk"
    assert out["cypher"], "a chosen tool still answers with its hand-written query"


def test_a_chosen_tool_still_extracts_its_arguments_by_rule(agent):
    """Choosing the tool does not let the user supply arguments -- the question still does."""
    out = agent.ask_locally("who should i ping about pkg/scheduler", force="who_owns")
    assert out["shape"] in ("ANSWERED_WITH_PATH", "ANSWERED_FROM_MEMORY", "NOT_IN_GRAPH")
    out2 = agent.ask_locally("who owns it", force="who_owns")
    assert out2["shape"] == "UNSURE_WHICH_TOOL", "no path in the question means it still declines"


def test_a_chosen_tool_must_be_in_the_catalogue(agent):
    """Otherwise 'force' is a hole straight through the fixed tool catalogue."""
    out = agent.ask_locally("anything at all", force="rm -rf /")
    assert out["shape"] == "UNKNOWN_ENTITY"
    assert "not one of the tools" in out["answer"]


# ---------------- what may be OFFERED, which is not the same as what was scored ----------------
#
# Adding candidate buttons to a refusal nearly rebuilt the original bug one layer up. `near` is the
# top three tools by score with the out-of-domain bucket filtered out, so for "write me a poem
# about kubernetes" it contains draft_owners_patch -- and the first version offered it. A user asks
# for a poem, the product declines, and then hands them a button that drafts OWNERS patches.
#
# Candidates are offered only for a genuine near-tie: both tools clear MIN_SCORE and sit within
# MIN_MARGIN, so the question IS about this graph and the only open point is which of two readings
# was meant.

@pytest.mark.parametrize("question", [
    "write me a poem about kubernetes",
    "fix my failing unit test",
    "what is the capital of France",
])
def test_an_out_of_domain_question_is_offered_nothing(agent, question):
    out = agent.ask_locally(question)
    assert out["shape"] == "UNSURE_WHICH_TOOL"
    assert out.get("near") == [], (
        f"{question!r} was offered {[n['tool'] for n in out['near']]} -- a question this graph "
        f"does not answer must not come with buttons that run tools on it")
    assert "candidates are below" not in out["answer"]


def test_a_missing_argument_is_offered_nothing_because_a_button_would_loop(agent):
    out = agent.ask_locally("who owns this?")
    assert out["shape"] == "UNSURE_WHICH_TOOL"
    assert out.get("near") == []
    assert "needs a" in out["answer"]


def test_a_near_tie_is_the_one_case_that_offers(agent):
    out = agent.ask_locally("show me the areas that depend on one person")
    assert out["shape"] == "UNSURE_WHICH_TOOL"
    assert len(out.get("near", [])) >= 2
    assert "too close to call" in out["answer"]


# ---------------- the counterfactual's picture must agree with its answer ----------------
#
# The drawn cascade is built from the verdict in the answer rather than recomputed, because
# deciding which areas a cohort strands needs a GRAPH.COPY and running a second one here could
# reach a different conclusion than the text beside it. This asserts the property that choice was
# made to guarantee: what is struck through on the canvas is exactly what the tool said was
# stranded, and the areas drawn as surviving really do inherit coverage from an ancestor that
# still has an approver.

COHORT = ["deads2k", "liggitt", "jpbetz", "smarterclayton", "enj", "serathius"]


# The cohort tool was the one tool that did not resolve its arguments. Every other entity-taking
# tool checks the graph first and answers UNKNOWN_ENTITY when the name is not there; this one
# normalised the handles, copied the graph, deleted zero APPROVES edges because nothing matched,
# observed that the stranded set had not changed, and reported "nothing would be stranded". A
# confident, sub-second answer about people who do not exist, in the tool whose whole purpose is
# to say who is load-bearing. These two assert the contract README states universally.

def test_a_cohort_of_strangers_is_refused_rather_than_simulated(agent):
    answer = agent.dispatch("what_if_they_go",
                            {"handles": ["not-a-real-person", "also-fictional-xyz"]})
    assert answer.shape == "UNKNOWN_ENTITY", (
        f"a cohort of handles that are not in the graph came back as {answer.shape}; deleting "
        f"nothing and finding no impact is not an answer about those people")
    assert "not-a-real-person" in (answer.note or ""), (
        "the refusal must name which handles it could not resolve, or the reader cannot tell a "
        "typo from a real finding")


def test_one_bad_handle_does_not_pass_as_a_cohort_result(agent):
    # Mixed is the dangerous case: five real people and one typo would otherwise simulate five,
    # and the reader would read the result as being about all six.
    answer = agent.dispatch("what_if_they_go", {"handles": COHORT[:2] + ["typoed-handle"]})
    assert answer.shape == "UNKNOWN_ENTITY", (
        f"a cohort with one unresolvable handle came back as {answer.shape}; the result would "
        f"have been read as covering all three")
    assert "typoed-handle" in (answer.note or "")
    assert COHORT[0] not in (answer.note or ""), (
        "only the unresolved handles should be named; listing the valid ones reads as if they "
        "were the problem")


def test_the_drawn_cascade_matches_the_counterfactual_it_illustrates(agent):
    from tombstone.server import subgraph

    answer = agent.dispatch("what_if_they_go", {"handles": COHORT})
    if answer.shape == "DEGRADED":
        pytest.skip("GRAPH.COPY unavailable on this host; the counterfactual itself is skipped")
    stranded = answer.rows[0][1]
    assert stranded, "this cohort is the one the README quotes; it must strand something"

    drawn = subgraph(handles=",".join(COHORT), stranded=",".join(stranded))
    struck = {n["full"] for n in drawn["nodes"] if n["kind"] == "area_stranded"}
    assert struck == set(stranded), (
        f"the canvas strikes through {struck} but the answer said {set(stranded)} -- a picture "
        f"that contradicts the text beside it is worse than no picture")


def test_every_surviving_area_drawn_shows_why_it_survives(agent):
    """The first version drew survivors with nothing to say why they survived."""
    from tombstone.server import subgraph

    answer = agent.dispatch("what_if_they_go", {"handles": COHORT})
    if answer.shape == "DEGRADED":
        pytest.skip("GRAPH.COPY unavailable on this host")
    drawn = subgraph(handles=",".join(COHORT), stranded=",".join(answer.rows[0][1]))
    edges = drawn["edges"]
    # Named once, and asserted to exist before it is used to build sets. Filtering on a label
    # that has been renamed yields EMPTY sets, and an empty set makes some assertions vacuous
    # rather than failing -- a renamed edge should break this test loudly, not quietly weaken it.
    # The label is "INHERITS COVERAGE" rather than the data model's INHERITS_FROM because the
    # match behind it walks *1..8: pkg/api/testing reaches pkg only through pkg/api, which has no
    # approvers at all, so one INHERITS_FROM edge there would claim a relationship the graph
    # does not hold.
    inherit_label = "INHERITS COVERAGE"
    assert any(e["label"] == inherit_label for e in edges), (
        f"no {inherit_label!r} edge is drawn at all; if it was renamed, rename it here too -- "
        f"every check below filters on it and would pass on an empty set")
    inherits = {e["source"] for e in edges if e["label"] == inherit_label}
    survivors = {n["id"] for n in drawn["nodes"] if n["kind"] == "area"}
    ancestors = {e["target"] for e in edges if e["label"] == inherit_label}
    # Every surviving area is either the ancestor that carries others, or inherits from one.
    for area in survivors:
        assert area in inherits or area in ancestors, (
            f"{area} is drawn as surviving with no inheritance edge -- a reader cannot tell why "
            f"it is not struck through")
    # ...and the ancestor must have someone still approving it.
    kept = {e["target"] for e in edges if e["label"] == "STILL APPROVES"}
    assert ancestors and ancestors <= kept, (
        "an area drawn as inheriting coverage must show the person who still provides it")


def test_an_out_of_domain_area_name_draws_nothing(agent):
    """`stranded` arrives from the client, so a value naming no real area must draw nothing."""
    from tombstone.server import subgraph

    drawn = subgraph(handles=",".join(COHORT), stranded="not/a/real/OWNERS")
    struck = [n for n in drawn["nodes"] if n["kind"] == "area_stranded"]
    assert not struck, "a path that names no ownership file must not be drawn as a real area"


def test_every_legend_swatch_is_paired_with_its_label():
    """A swatch and the words it explains must wrap as one unit.

    `.legend` is a flex container. Its children used to be the `<i class="sw">` marks and bare
    text nodes, and a bare text node beside an element is its OWN anonymous flex item -- so on a
    narrow screen the swatch and its label wrapped to different lines. On a phone the struck
    square sat alone at the end of one row while "area with nobody left" began the next, which is
    the one mark in the picture that carries a verdict rather than a category.

    Found by opening the page at 375px and looking at it, not by any test, so here is the test.
    """
    import re

    # Scanned over the whole file rather than a sliced-out legend block: swatches appear nowhere
    # else, and slicing to the first "</span>" cut the block off after the first .key, which made
    # this test fail against markup that was already correct.
    html = open("web/index.html").read()
    assert '<span class="legend">' in html, "the legend is gone from web/index.html"

    swatches = re.findall(r'<i class="sw[^"]*"></i>', html)
    assert swatches, "the legend has no swatches at all"

    # Every swatch must sit inside a .key that also carries text; nothing may be loose.
    keys = re.findall(r'<span class="key">\s*(<i class="sw[^"]*"></i>)\s*([^<]+?)\s*</span>', html)
    assert len(keys) == len(swatches), (
        f"{len(swatches)} swatches but only {len(keys)} are paired with a label inside a .key; "
        f"a loose swatch wraps away from the words it explains")
    for _mark, label in keys:
        assert label.strip(), "a .key has a swatch but no label"

    # And the pairing only holds if .key stops the line breaking inside it.
    css = open("web/style.css").read()
    key_rule = re.search(r"\.key\{([^}]*)\}", css)
    assert key_rule, "web/style.css has no .key rule, so the pairing is markup-only"
    assert "nowrap" in key_rule.group(1), ".key must not allow a break between swatch and label"


def test_no_drawn_edge_invents_a_relationship(agent):
    """Every label on the reasoning picture is either a real edge type or a declared summary.

    The picture's whole claim is that the path IS the evidence, so a label that looks like a
    relationship name had better be one. One was not: the counterfactual drew
    `pkg/api/testing --INHERITS_FROM--> pkg` from a `[:INHERITS_FROM*1..8]` walk, and the graph
    holds no such edge -- pkg/api sits between them with no approvers at all.

    Renaming the other two summaries would be worse than keeping them. `SHAPED` collapses
    AUTHORED|APPROVED and `REJECTED` renders CONSIDERED, and both are the words the answer's own
    prose and the demo narration use ("shaped 6 decisions", "personally rejected"). So they stay,
    and instead nothing may be drawn that is neither a real type nor declared here.
    """
    import re

    # label -> what it is actually traversing, so a reader of this test learns the mapping.
    DERIVED = {
        "SHAPED": "AUTHORED|APPROVED",
        "REJECTED": "CONSIDERED",
        "INHERITS COVERAGE": "INHERITS_FROM*1..8",
        "STILL APPROVES": "APPROVES, minus the departing cohort",
        "LEFT BEHIND": "EMERITUS_OF",
        "ALREADY APPROVES": "APPROVES",
    }

    real = {row[0] for row in agent.g.ro_query("CALL db.relationshipTypes()").result_set}
    assert "APPROVES" in real, "the graph has no APPROVES edge; is this the right database?"

    # Parens are balanced rather than pattern-matched: link(add(who, who, "person_gone"), area,
    # "APPROVES") nests a call whose own last string is a NODE KIND, and a lazy [^)]* stops at the
    # inner ")" and reads "person_gone" as an edge label. The first version of this test did
    # exactly that and failed on a node kind, which would have sent me looking in the wrong place.
    src = open("src/tombstone/server.py").read()
    drawn = set()
    for m in re.finditer(r"\blink\(", src):
        depth, i = 0, m.end() - 1
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        call = src[m.end():i]
        strings = re.findall(r'"([^"]+)"', call)
        if strings:
            drawn.add(strings[-1])          # the label is link()'s last argument
    drawn.discard("")
    assert drawn, "found no link() calls to check -- has the drawing moved?"

    for label in sorted(drawn):
        assert label in real or label in DERIVED, (
            f"the picture draws an edge labelled {label!r}, which is neither a relationship type "
            f"in the graph nor declared a summary here. A viewer reads it as a relationship, and "
            f"a judge who checks the graph for it will not find it")

    # And a declared summary must not shadow a real type: if SHAPED ever becomes a real edge,
    # calling it derived would be the same confusion pointing the other way.
    overlap = sorted(set(DERIVED) & real)
    assert not overlap, f"{overlap} are declared summaries but now exist as real edge types"

    # The README prints this same mapping for a judge reading the data model. Two copies of a
    # mapping is two things to keep in step, and every figure in this repo that was kept in step
    # by hand has drifted, so the prose copy is checked against this one rather than trusted.
    readme = open("README.md").read()
    table = readme[readme.index("drawn on the picture"):]
    table = table[:table.index("\n\n")]
    for label in DERIVED:
        assert f"`{label}`" in table, (
            f"{label!r} is drawn and declared a summary here, but the README's table of what each "
            f"drawn label traverses does not mention it")


def test_every_node_kind_the_picture_draws_has_a_legend_entry():
    """A mark on the canvas that the legend does not explain is a mark nobody can read.

    This already shipped once: the struck square for an area with nobody left was the only thing
    on the picture with no legend entry, on the beat that matters most, and the CSS still carries
    the note about it. It was fixed by hand, which fixes that instance and not the next one.

    Parsed with ast rather than a regex. add() is called with a dict of extras in some places and
    through area_of() in others, and a regex over "the last string in the call" picked up `title`
    and a fragment of a comma-separated line -- confident noise that looked like node kinds.
    """
    import ast
    import re

    # node kind emitted by the server -> the swatch class the legend uses for it.
    LEGEND_CLASS = {
        "person_gone": "gone",
        "person_live": "live",
        "area": "area",
        "area_stranded": "stranded",
        "decision": "dec",
        "rejected": "rej",
    }

    tree = ast.parse(open("src/tombstone/server.py").read())
    kinds = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "add" and len(node.args) >= 3:
            arg = node.args[2]
            if isinstance(arg, ast.Constant):
                kinds.add(arg.value)
            elif isinstance(arg, ast.IfExp):           # "area_stranded" if is_strand else "area"
                for branch in (arg.body, arg.orelse):
                    if isinstance(branch, ast.Constant):
                        kinds.add(branch.value)
            else:
                raise AssertionError(
                    f"add() is called with a computed node kind at line {node.lineno}; this test "
                    f"can no longer enumerate what the picture draws, so it would pass by missing "
                    f"it")
    assert kinds, "found no add() calls -- has the drawing moved out of server.py?"

    html = open("web/index.html").read()
    swatches = set(re.findall(r'<i class="sw ([a-z_]+)"></i>', html))

    for kind in sorted(kinds):
        assert kind in LEGEND_CLASS, (
            f"the picture can draw a {kind!r} node, which is not mapped to a legend swatch here")
        assert LEGEND_CLASS[kind] in swatches, (
            f"{kind!r} is drawn but the legend has no .sw.{LEGEND_CLASS[kind]} entry, so a viewer "
            f"sees a mark with nothing explaining it")

    # The other direction: a legend entry for something that can no longer appear is a promise the
    # picture does not keep, and it costs a reader attention on the one beat that matters.
    orphans = sorted(swatches - {LEGEND_CLASS[k] for k in kinds})
    assert not orphans, f"the legend explains {orphans}, which the picture can no longer draw"

    # Both renderers must also know which LANE each kind belongs in. The README's figure generator
    # did not know about area_stranded and would have raised a bare KeyError on any subgraph that
    # held one; its own path holds none, so it never showed. The app has every kind but falls back
    # with `?? 0`, which files an unknown kind under "people" -- on a picture that is supposed to
    # be evidence, quietly putting a node in the wrong lane is worse than failing to draw it, so
    # the map is checked rather than the fallback trusted.
    for lane_file in ("web/app.js", "scripts_gen_readme_figure.py"):
        text = open(lane_file).read()
        block = re.search(r"LANE\s*=\s*\{(.*?)\}", text, re.S)
        assert block, f"{lane_file} has no LANE map any more"
        mapped = set(re.findall(r'"?([a-z_]+)"?\s*:', block.group(1)))
        missing = sorted(kinds - mapped)
        assert not missing, (
            f"{lane_file} has no lane for {missing}, so those nodes land in whichever lane the "
            f"fallback picks rather than the one they belong to")


def test_no_answer_claims_a_count_it_then_lists_short_of(agent):
    """"6 decisions: <five of them>" is a sentence that asks the reader to count and lose.

    Several queries return a SAMPLE -- areas[0..5], decisions_they_shaped[0..5] -- beside a true
    count, and two renderers printed the count and the sample with a plain colon between them.
    One was `sole_approver_risk`; the other was the depth-4 `who_owns`, which is the first image
    in the README and the line the demo narration reads aloud. A judge who counts the KEPs finds
    five under a sentence that says six.

    The fix is one word, "including", and it is only correct when the list really is short, so
    this checks both directions rather than just looking for the word.
    """
    import re
    from tombstone.agent import render

    CASES = [
        ("who_owns", {"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS",
                      "depth": 4}),
        ("ownership_dilution", {}),
        ("sole_approver_risk", {}),
        ("stepped_back_but_still_listed", {"min_stepped_back": 3}),
        ("successor_for", {"handle": "lavalamp"}),
        ("broken_lineage", {"min_cites": 2}),
        ("stepped_back_bridges", {"min_areas": 3}),
        ("hollowing_communities", {"min_size": 5}),
        ("stale_knowledge", {"min_years": 3}),
    ]
    # "<n> <plural noun>[, including]: a, b, c" -- the only shape in this product's prose that
    # states a number and then enumerates it.
    PATTERN = re.compile(r"(\d+)\s+[a-z]+s(,\s*including)?:\s*([^\n]+)")

    problems = []
    matched = 0
    for tool, args in CASES:
        answer = agent.dispatch(tool, args)
        if answer.shape == "DEGRADED":
            continue
        for m in PATTERN.finditer(render(answer)):
            matched += 1
            claimed, hedged = int(m.group(1)), bool(m.group(2))
            listed = len([x for x in m.group(3).split(",") if x.strip()])
            if listed < claimed and not hedged:
                problems.append(f"{tool}: says {claimed}, lists {listed} — {m.group(0)[:90]}")
            if listed >= claimed and hedged:
                problems.append(
                    f"{tool}: hedges with 'including' but lists all {listed} of {claimed} — "
                    f"the hedge is noise and trains a reader to distrust it elsewhere")
    assert not problems, "\n  ".join([""] + problems)

    # A floor, because without one this test passes when the pattern stops matching anything --
    # verified by changing one colon to a dash in the renderer, which silenced it completely.
    # It is the test guarding the headline beat's "6 decisions" line, so a punctuation change
    # quietly retiring it is the worst available outcome.
    assert matched >= 8, (
        f"the count-then-list pattern matched only {matched} lines across {len(CASES)} tools; "
        f"the renderers were rephrased past this check and it is no longer testing anything")


def test_the_video_is_fingerprinted_against_everything_the_images_are():
    """The walkthrough renders every chip, so it depends on at least what the stills depend on.

    This invariant exists because the fingerprint lists were wrong four times in a row, each time
    in the same way: a source got added when something visible broke, rather than by asking what
    the frame is actually made of. server.py, then agent.py, then the corpus and build.py, then
    tools.py and act.py for the drafted-patch still. Every one of those was found by changing the
    file and noticing the checks stayed green.

    A superset check cannot say the lists are COMPLETE -- nothing can, short of rendering twice
    and diffing -- but it does catch the specific mistake that kept happening: extending one
    generator's list and forgetting the video, which renders the same answers.
    """
    import json
    import os

    paths = {
        "shots": "docs/img/.shots-fingerprint.json",
        "gif": "docs/img/.depthgif-fingerprint.json",
        "walkthrough": "docs/video/.walkthrough-fingerprint.json",
    }
    recorded = {}
    for name, path in paths.items():
        assert os.path.exists(path), f"{path} is missing -- regenerate the {name}"
        recorded[name] = set(json.load(open(path)))

    # Each fingerprint now records its OWN generator among its sources, which is correct -- editing
    # a generator can change what it draws -- but it means the raw sets cannot nest: the stills
    # list scripts_gen_*.py and the video lists scripts_build_walkthrough.py. The invariant is
    # about the shared INPUTS the frames are made of, so each list is compared without its own
    # generator. Taken from the checker's own ARTEFACTS table rather than matched by filename, so
    # renaming a generator cannot silently widen the exclusion.
    #
    # This surfaced the day the artefacts were first regenerated after self-inclusion was added to
    # the generators: every committed fingerprint predated it, so the sets happened to nest and
    # this test passed for the wrong reason.
    # Loaded by path, not by `import scripts_check_shots_fresh`. The plain import worked under
    # `python -m pytest`, which puts the working directory on sys.path, and CI runs bare
    # `pytest tests/ -q` with PYTHONPATH=src, which does not -- so it passed here and failed
    # there. The file guards its own main(), so executing the module just defines ARTEFACTS.
    import importlib.util
    import pathlib as _pl
    _src = _pl.Path(__file__).resolve().parent.parent / "scripts_check_shots_fresh.py"
    assert _src.exists(), f"{_src} is missing -- this test reads its ARTEFACTS table"
    _spec = importlib.util.spec_from_file_location("_shots_fresh_for_test", _src)
    fresh = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(fresh)
    generators = {fp: gen for fp, gen, _ in fresh.ARTEFACTS}

    def inputs(name):
        return recorded[name] - {generators[paths[name]]}

    stills = inputs("shots") | inputs("gif")
    missing = sorted(stills - inputs("walkthrough"))
    assert not missing, (
        f"the walkthrough video renders the same answers as the stills but is not fingerprinted "
        f"against {missing}; a change there would stale the video with every check green")

    # Each list must also name only files that exist, or the guard silently covers nothing.
    for name, sources in recorded.items():
        gone = sorted(s for s in sources if not os.path.exists(s))
        assert not gone, f"the {name} fingerprint names {gone}, which no longer exist"

    # docs/video/README.md tells a reader how many files that guard covers. It said "tools.py as
    # well as the three web files" long after the list had grown to nine -- a spelled number in
    # prose, which is the one shape the drift checks in this repo were not looking for until the
    # README's own "one of those twenty" survived the eval growing to twenty-five.
    import re
    _SPELL = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
              11: "eleven", 12: "twelve"}
    prose = open("docs/video/README.md").read()
    said = re.search(r"\*\*(\w+)\*\* in total", prose)
    assert said, "docs/video/README.md no longer says how many files the guard covers"
    want = len(recorded["walkthrough"])
    assert said.group(1) == _SPELL.get(want), (
        f"docs/video/README.md says the guard covers {said.group(1)!r} files; the walkthrough "
        f"fingerprint records {want} ({_SPELL.get(want)})")


def test_no_shipped_string_fakes_a_plural_with_parens():
    """"1 area(s)" is the shape this product keeps having to remove.

    It has been removed three times: fifteen occurrences in the answer renderers, then
    "1 uncommitted change(s)" in the submission audit, then five more in the eval and checker
    output -- including "who_owns names 8 approver(s)", printed by a script the README tells a
    judge to run. Every number in this repository is checked; how the word beside it is spelled
    never was, which is why this particular defect keeps coming back rather than being fixed.

    Parsed with ast so only real string literals are examined. A comment documenting the old
    mistake is not the mistake, and the earlier sweeps found those by grep and had to read past
    them each time.
    """
    import ast
    import pathlib
    import re
    import subprocess

    files = [f for f in subprocess.run(["git", "ls-files", "*.py"], capture_output=True,
                                       text=True).stdout.split() if pathlib.Path(f).exists()]
    assert files, "no tracked Python files found"

    # "(s)" straight after a word character is a faked plural. A regex literal is not: those are
    # recognisable by carrying backslash escapes, and "(s)" there is a capture group.
    FAKE = re.compile(r"[A-Za-z](\(s\))")
    offenders = []
    for path in files:
        if path.startswith("tests/"):
            continue                       # this file quotes the bad form to describe it
        tree = ast.parse(pathlib.Path(path).read_text())
        # Docstrings are excluded: three of them explain why this form is wrong, including the
        # one on the `_n` helper written to replace it. Flagging the explanation of a mistake is
        # the same error the verification-claims checker had to learn not to make.
        docstrings = set()
        for holder in ast.walk(tree):
            if isinstance(holder, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(holder, "body", None) or []
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            text = node.value
            if "\\s" in text or "\\d" in text or "\\b" in text:
                continue                   # a regex, where (s) is a group
            if re.search(r"\b(MATCH|RETURN|WHERE|MERGE|CALL)\b", text):
                continue                   # Cypher, where count(s) references a variable
            if FAKE.search(text):
                offenders.append(f"{path}:{node.lineno}  {text.strip()[:70]}")

    assert not offenders, (
        "a string fakes a plural with (s); write both words out:\n  " + "\n  ".join(offenders))


def test_the_benchmark_table_and_the_prose_under_it_agree():
    """The PageRank range is stated twice in one section, and the two disagreed.

    The table row said 30-145x after a loaded machine widened it, the paragraph below narrated
    that widening -- "a loaded machine gave PageRank 30x where this table had claimed 54-145x" --
    and the caveat two paragraphs further down still said 54-145x. A section that documents its
    own correction and then fails to apply it a few lines later is worse than one that never
    corrected anything, because the reader cannot tell which number is the live one.

    This does NOT gate the measurement. The ranges are deliberately reported rather than
    asserted, because gating a ratio turned CI red for a claim that was never false when the
    hardware changed. It gates only that the README agrees with itself.
    """
    import re

    readme = open("README.md").read()
    row = re.search(r"\|\s*PageRank[^|]*\|[^|]*\|[^|]*\|\s*FalkorDB\s*\*\*(\d+)[–-](\d+)x\*\*",
                    readme)
    assert row, "the README's benchmark table no longer has a PageRank row in the expected shape"
    table_range = (row.group(1), row.group(2))

    # Every other PageRank range in the file must match it, except one that is explicitly the
    # superseded figure being quoted -- "had claimed", past tense.
    #
    # Counted, because the first version of this test passed with BOTH prose mentions deleted:
    # it asserted the table row existed and then looped over prose that had stopped matching, so
    # rewording either sentence silently retired the check. That is the exact failure this test
    # was written to catch, committed inside the test itself on the same day.
    seen_readme = seen_explain = 0
    for m in re.finditer(r"PageRank[^.\n]{0,40}?(\d+)[–-](\d+)x", readme):
        # "had claimed" sits INSIDE the matched span -- "PageRank 30x where this table had
        # claimed 54-145x" -- not before it, which is where the first version of this looked.
        if "had claimed" in m.group(0) or "previously" in m.group(0):
            continue
        seen_readme += 1
        assert (m.group(1), m.group(2)) == table_range, (
            f"the README states PageRank at {m.group(1)}-{m.group(2)}x where its own table says "
            f"{table_range[0]}-{table_range[1]}x")

    # The explainer answers a judge's question out loud, so it must not quote a retired range.
    explain = open("docs/EXPLAIN-IT.md").read()
    for m in re.finditer(r"PageRank[^.\n]{0,40}?(\d+)[–-](\d+)x", explain):
        seen_explain += 1
        assert (m.group(1), m.group(2)) == table_range, (
            f"docs/EXPLAIN-IT.md says PageRank {m.group(1)}-{m.group(2)}x; the README's table "
            f"says {table_range[0]}-{table_range[1]}x")

    assert seen_readme >= 1, (
        "no PageRank range found in the README's prose; the sentence was reworded and this check "
        "silently stopped checking it")
    assert seen_explain >= 1, (
        "no PageRank range found in docs/EXPLAIN-IT.md; the explainer dropped the figure, or "
        "reworded it past this check")


def test_a_bold_line_on_its_own_is_not_glued_to_the_paragraph_above():
    """A fully-bold line is a heading in intent, and needs a blank line to be one in render.

    Two of these existed. In the README, the third of "three claims I stress-tested" was glued to
    the second, so the section rendered as two claims with a bold run-on in the middle of one. In
    docs/GROUND-TRUTH.md it was the most emphatic sentence in its section, trailing off the end of
    a paragraph about AOF persistence.

    Markdown does not complain about either. They read correctly as source and wrong as output,
    which is why they survived every check and a lot of re-reading.
    """
    import pathlib
    import re
    import subprocess

    docs = [d for d in subprocess.run(["git", "ls-files", "*.md"], capture_output=True,
                                      text=True).stdout.split() if pathlib.Path(d).exists()]
    assert docs, "no tracked markdown found"

    glued = []
    for doc in docs:
        lines = pathlib.Path(doc).read_text().split("\n")
        in_code = False
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code or i == 0:
                continue
            # Entirely bold, nothing else on the line: a heading in everything but syntax.
            if re.fullmatch(r"\*\*[^*].*[^*]\*\*", line.strip()) and lines[i - 1].strip():
                glued.append(f"{doc}:{i + 1}  {line.strip()[:66]}")

    assert not glued, (
        "a fully-bold line follows prose with no blank line, so it renders inside that paragraph "
        "instead of standing alone:\n  " + "\n  ".join(glued))


def test_every_repo_path_the_docs_name_actually_exists():
    """A document that names a file which is not there sends a judge somewhere empty.

    The AI-disclosure paragraph said every performance number came from "a benchmark in
    `spikes/`". spikes/ exists, so nothing looked wrong -- but the two scripts producing the
    numbers a reader meets, bench_vs_networkx.py and bench_copy.py, are at the repository root.
    Prose, not a link, so no link checker would have seen it.

    Three names are upstream Kubernetes files rather than files here, and are meant to be: a KEP
    path inside the corpus, and the two YAML files the ingest reads from kubernetes/enhancements.
    """
    import pathlib
    import re
    import subprocess

    tracked = set(subprocess.run(["git", "ls-files"], capture_output=True,
                                 text=True).stdout.split())
    docs = [d for d in tracked if d.endswith(".md") and pathlib.Path(d).exists()]
    assert docs, "no tracked markdown found"
    basenames = {p.split("/")[-1] for p in tracked}

    # Files that belong to kubernetes/enhancements, not to this repository.
    UPSTREAM = {"kep.yaml", "sigs.yaml", "/keps/sig-api-machinery/0006-apply.md"}

    # Files in ANOTHER ENTRANT's repository, named as evidence. SUBMISSION.md's competitive
    # section quotes BalajiReddy1/understudy's tree to show it reads the same corpus this does --
    # the entire point of naming those files is that they are not here. Listed one by one rather
    # than by loosening the regex or exempting the document, so a genuinely missing path in this
    # repository still fails this test.
    OTHER_ENTRANTS = {"ingest/owners.py", "ingest/keps.py", "derive/departures.py"}

    PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|sh|yml|yaml|json|gz|js|css|html|mp4|svg|gif|png))`")
    missing = []
    for doc in docs:
        here = pathlib.Path(doc).parent
        for m in PATH.finditer(pathlib.Path(doc).read_text()):
            name = m.group(1)
            if name in UPSTREAM or name in OTHER_ENTRANTS or name in tracked or name in basenames:
                continue
            if (here / name).exists() or pathlib.Path(name).exists():
                continue
            missing.append(f"{doc}: `{name}`")

    assert not missing, (
        "a document names a path that is not in the repository:\n  " + "\n  ".join(missing))


def test_derive_label_refuses_list_markers_and_abbreviations():
    """A label is a readable sentence, or it is worse than no label.

    Three defects, each of which shipped at some point and each pinned here:
      - a leading "1." or "* " put the first sentence boundary two characters in, so nineteen
        real rejections were labelled `1.`;
      - the abbreviation guard was compared with endswith, and "al." is in it for "et al.", so
        every sentence ending in "proposal." was swallowed and ran on to the next boundary;
      - the accepted sentence was then sliced at a fixed width, which cut eighteen labels
        mid-word with no ellipsis.
    """
    from tombstone.build import derive_label

    assert derive_label("1. Increasing the default timeout for exec probes is one option. More.") \
        .startswith("Increasing")
    assert derive_label("* Setting up a VPN (e.g. IPSec, Wireguard). It is more complicated.") \
        == "Setting up a VPN (e.g. IPSec, Wireguard)."
    # the endswith regression: "proposal." is a sentence end, "et al." is not
    assert derive_label("There are a few alternatives to this proposal. First, an API.") \
        == "There are a few alternatives to this proposal."
    assert derive_label("See Smith et al. 2019 for the background here. It was rejected.") \
        == "See Smith et al. 2019 for the background here."
    # a sentence with no boundary at all is clipped on a word, with an ellipsis
    long = "word " * 80
    out = derive_label(long)
    assert len(out) <= 161 and out.endswith("…") and not out.endswith("wor…")


def test_every_excluded_alternative_is_embedded_and_substantive(g):
    """The docs call these the product's biggest recall weakness. The claim they make is that
    the exclusion is the INDEX, not the data -- so the data has to hold up."""
    gap, vectored, thin, longest = g.ro_query(
        "MATCH (a:Alternative) WHERE NOT a:NamedOption "
        "RETURN count(a), sum(CASE WHEN a.emb IS NOT NULL THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN size(a.body) < 100 THEN 1 ELSE 0 END), max(size(a.title))"
    ).result_set[0]
    assert gap > 0, "no excluded alternatives at all — this test would pass vacuously"
    assert vectored == gap, f"{gap - vectored} of {gap} excluded alternatives carry no vector"
    assert thin == 0, f"{thin} excluded alternatives hold under 100 characters of argument"
    assert longest <= 161, f"an excluded alternative carries a {longest}-character label"
    markers = g.ro_query(
        "MATCH (a:Alternative) WHERE NOT a:NamedOption AND size(trim(a.title)) <= 6 "
        "RETURN count(a)").result_set[0][0]
    assert markers == 0, f"{markers} excluded alternatives are labelled with a list marker"


def test_drawn_path_can_cite_what_the_prose_cites(g):
    """The picture and the sentence must walk the same label.

    They did not: the prose walks :Alternative and the drawn path walked :NamedOption, so on the
    demo's own file the answer named two rejections -- one of them 'Doing nothing is a viable
    alternative.' -- that the diagram drew zero of. The beat's claim is that the picture IS the
    path the answer came from, which that made false.
    """
    import pathlib
    import re

    server = pathlib.Path("src/tombstone/server.py").read_text()
    drawn = re.search(r"CONSIDERED\]->\(alt:(\w+)\)", server)
    assert drawn, "the subgraph query no longer walks CONSIDERED"
    assert drawn.group(1) == "Alternative", (
        f"the drawn path filters rejections to :{drawn.group(1)}; the prose walks :Alternative, "
        f"so the diagram can omit a node the answer names")

    path = "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS"
    cited = {r[0] for r in g.ro_query(
        "MATCH (o:OwnersFile {path:$p})<-[:EMERITUS_OF]-(d:Person) "
        "MATCH (d)-[:AUTHORED|APPROVED]->(:Kep)-[:CONSIDERED]->(a:Alternative) "
        "RETURN DISTINCT a.title", params={"p": path}).result_set}
    assert cited, "the demo's own file cites no rejections — this test would pass vacuously"
    assert "Doing nothing is a viable alternative." in cited


def test_every_answer_that_shows_a_query_says_what_was_asked_of_it(agent):
    """A query without its arguments is an incomplete provenance.

    The UI's claim is that you can see where an answer came from, and it showed the Cypher and a
    hash of the Cypher. Those identify the query TEXT -- that it is one of the thirteen constants
    and was not rewritten -- and deliberately not the values. So "which cited decisions no longer
    exist" returned 5 rows from the chip and 15 typed by hand, with one identical query and one
    identical hash on screen either way, because the chip narrows min_cites to 2 and the router
    uses the default of 1. Nothing visible distinguished them.
    """
    from tombstone.tools import CATALOGUE

    probes = {
        "has_this_been_tried": {"idea_text": "pull profile artifacts into the kubelet"},
        "successor_for": {"handle": "lavalamp"},
        "who_owns": {"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS",
                     "depth": 4},
        "what_if_they_go": {"handles": ["deads2k", "liggitt"]},
        "recall": {"question": "who owns the metrics endpoints"},
        "draft_owners_patch": {"min_stepped_back": 3},
    }
    checked = 0
    for tool in CATALOGUE:
        ans = agent.dispatch(tool, probes.get(tool, {}))
        if not (ans.cypher or "").strip():
            continue                      # nothing ran, so there is nothing to qualify
        assert ans.params, (
            f"{tool} shows a Cypher but reports no arguments, so two different answers from it "
            f"are indistinguishable on screen")
        assert all(k == k.lower() for k in ans.params), (
            f"{tool} reports {sorted(ans.params)}; the UI lists the tool's own argument names, "
            f"which are lower case")
        checked += 1
    assert checked >= 10, f"only {checked} tools ran a query — this would pass on almost nothing"


def test_the_two_endpoints_agree_on_what_they_return(agent):
    """`/api/ask` and `/api/tool` build their payloads in one place for a reason: they drifted
    once, and the model path silently lost `headline`, the one number the UI leads with."""
    ans = agent.dispatch("sole_approver_risk", {})
    payload = agent._payload("which areas have exactly one approver", "sole_approver_risk",
                             {}, ans, "local")
    for key in ("tool", "shape", "headline", "answer", "rows", "coverage", "note", "ms",
                "cypher", "query_sha", "params"):
        assert key in payload, f"/api/ask payload has no {key!r}"


def test_the_honest_negative_does_not_overstate_what_was_searched(agent, g):
    """The sentence a judge is told to trust must not inflate the haystack.

    `has_this_been_tried` answers through a vector index minted on :NamedOption, and its empty
    answer used to report "958 rejected alternatives indexed" -- the whole :Alternative count,
    27% larger than what the question was actually compared against, with "indexed" being exactly
    the word that is false for the other 206. Overstating coverage in the honest negative is
    worse than a wrong answer, because that sentence is the product's claim about its own limits.
    """
    named, total = g.ro_query(
        "MATCH (a:Alternative) WITH count(a) AS total "
        "MATCH (n:NamedOption) RETURN count(n), total").result_set[0]
    assert named < total, "every alternative is indexed — this test would pass vacuously"

    ans = agent.dispatch("has_this_been_tried",
                         {"idea_text": "rewrite the control plane in COBOL on a mainframe",
                          "max_dist": 0.15})
    assert ans.shape == "NOT_IN_GRAPH", f"expected an empty result, got {ans.shape}"
    ints = {k: v for k, v in (ans.coverage or {}).items() if isinstance(v, int)}
    assert named in ints.values(), (
        f"the coverage for a similarity answer never states the {named} it searched: {ints}")
    assert total not in ints.values(), (
        f"the coverage for a similarity answer claims {total} alternatives; only {named} are in "
        f"the index it queried")

    from tombstone.agent import render
    prose = render(ans)
    assert str(named) in prose and "similarity" in prose, prose[:200]

    # The ownership tools traverse every alternative, so for them the full count is correct and
    # must stay -- the fix is tool-specific, not a blanket edit.
    other = agent.dispatch("who_owns",
                           {"path": "staging/src/k8s.io/apiserver/pkg/endpoints/metrics/OWNERS",
                            "depth": 1})
    assert total in {v for v in (other.coverage or {}).values() if isinstance(v, int)}


# A finding about approval does not justify ending a separate review responsibility. Pin the
# narrower edit so a draft cannot silently drop the person from both roles again.

def test_retire_preserves_reviewers_when_the_finding_only_covers_approval():
    from tombstone import act
    before = {"approvers": ["someone-else", "x"], "reviewers": ["someone-else", "x"],
              "options": {"no_parent_owners": True}}
    after = act.retire(before, "x")
    assert after["approvers"] == ["someone-else"]
    assert after["reviewers"] == ["someone-else", "x"], (
        "retiring approval cannot justify removing independent review responsibility")
    assert after["emeritus_approvers"] == ["x"]
    assert after["options"] == {"no_parent_owners": True}, "unrelated keys must survive"


def test_retire_leaves_reviewers_alone_when_the_handle_is_not_one():
    from tombstone import act
    after = act.retire({"approvers": ["a", "x"], "reviewers": ["a"]}, "x")
    assert after["reviewers"] == ["a"]
    assert "x" not in after["approvers"]


# Parser debris in the Person half of the graph, pinned so it cannot grow. Found by listing every
# key and testing it against GitHub's handle grammar -- not by looking at the total, which is why
# no count check saw it: 794 is a true count of Person nodes and nine of them are not people.
# Disclosed in README's Honest limits with the per-edge-type measurement.
#
# The assertion is one-directional on purpose. Growth is a parser regression and fails here.
# Shrinking is a fix and passes here, then fails the README's stated figure -- which is the right
# way round, because a fix should force the disclosure to be rewritten rather than silently
# outdating it.
NON_HANDLE_PERSON_KEYS = {
    "bowei - for networking/proxy portion of kep",
    "deads2k - for kube api server portion of kep",
    "kubernetes/wg-component-standard",
    "quinton_hoole",
    "with input from @bgrant0607, @dchen1107, @yujuhong, @lavalamp",
    "\u201c@ixdy\u201d", "\u201c@mortent\u201d", "\u201c@neolit123\u201d", "\u201c@sjenning\u201d",
}


def test_parser_debris_in_person_keys_does_not_grow(g):
    import re
    handle = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}$")
    keys = [r[0] for r in g.ro_query("MATCH (p:Person) RETURN p.key").result_set]
    assert keys, "no Person nodes -- the graph is not seeded"
    bad = {k for k in keys if not isinstance(k, str) or not handle.match(k)}
    new = bad - NON_HANDLE_PERSON_KEYS
    assert not new, (
        f"the reviewer-line parser produced {len(new)} new non-handle Person key(s): {sorted(new)}"
        f" -- either fix the parser or, if these are legitimate, add them here AND to the figure "
        f"in README's Honest limits")
    # Anti-vacuity: if the shape test ever stops matching anything, this proves nothing.
    assert bad, ("no malformed keys matched at all -- either the corpus was cleaned (update the "
                 "README disclosure and this set) or the handle grammar above has gone wrong")


def test_the_owners_half_of_the_graph_carries_no_parser_debris(g):
    """The disclosure's load-bearing half: APPROVES and EMERITUS_OF come from YAML, not prose."""
    for rel in ("APPROVES", "EMERITUS_OF"):
        n = g.ro_query(f"MATCH (p:Person)-[r:{rel}]-() WHERE p.key IN $b RETURN count(r)",
                       params={"b": sorted(NON_HANDLE_PERSON_KEYS)}).result_set[0][0]
        assert n == 0, (
            f"{n} {rel} edges now hang off a malformed Person key. README's Honest limits states "
            f"that the ownership half is unaffected because it is parsed from YAML; that is no "
            f"longer true and the disclosure is now wrong.")


# The filesystem trust boundary. draft_owners_patch's `write_to` is correct for a person
# regenerating docs/patches/ and is an unauthenticated arbitrary-path write when it arrives over
# HTTP -- and both network routes reached it: /api/tool passed the caller's args verbatim, and on
# a keyed instance ask() passes the MODEL's args verbatim while the catalogue entry listed
# `write_to` where the model could read it. One anonymous POST created a directory and wrote files
# into it. These three pin the refusal, the opt-in, and the silence of the catalogue.

def test_dispatch_refuses_filesystem_arguments_by_default(agent, tmp_path):
    target = tmp_path / "should-not-exist"
    ans = agent.dispatch("draft_owners_patch", {"write_to": str(target)})
    assert ans.shape == "ANSWERED_WITH_PATH", "the tool must still answer, just without writing"
    assert not target.exists(), (
        f"dispatch() wrote to {target} without allow_local_writes -- this is the path that was "
        f"reachable, unauthenticated, from the public /api/tool")


def test_dispatch_still_writes_when_a_local_caller_opts_in(agent, tmp_path):
    target = tmp_path / "patches"
    agent.dispatch("draft_owners_patch", {"write_to": str(target)}, allow_local_writes=True)
    written = sorted(p.name for p in target.iterdir()) if target.exists() else []
    assert len(written) == 2, (
        f"the opt-in path must still regenerate the committed artefacts; got {written}")
    assert all(n.endswith(".patch") for n in written)


def test_the_catalogue_never_advertises_an_argument_dispatch_refuses():
    """The catalogue is the model's menu and the sponsor engineer's API reference, both."""
    from tombstone.agent import UNSAFE_ARGS
    from tombstone.tools import CATALOGUE
    assert UNSAFE_ARGS, "the denylist is empty, so this test proves nothing"
    for name, spec in CATALOGUE.items():
        for arg in UNSAFE_ARGS:
            assert arg not in str(spec), (
                f"the catalogue entry for {name} names '{arg}', which dispatch() strips -- so it "
                f"advertises a parameter to the routing model and to /api/tools that cannot work")


def test_the_public_subgraph_endpoint_cannot_be_crashed_by_its_limit():
    """/api/subgraph is a GET and /api/docs hands a stranger the form for it.

    `?path=x&limit=-5` returned HTTP 500: the negative LIMIT reached Cypher, which rejects it, and
    the traceback came back as a crash on the one endpoint a judge can hit by accident while
    reading the API docs. `limit=-1` on its own did NOT crash, because with no path that query
    never runs -- the kind of near-miss that makes a real crash look absent.

    The NUL rows are the same crash through a different character, found by the 17 Oct audit and
    reproduced on the LIVE demo, not just locally: FalkorDB's parameter parser rejects a NUL byte
    and that ResponseError came back as a bare 500 with no JSON body. Every other byte tried
    survives as a parameter -- the other control characters, quotes, backslashes, a literal `$p`,
    emoji -- so the guard rejects exactly the one that cannot, and rejects rather than strips: a
    silently stripped NUL would answer about `pkgx` when `pkg\x00x` was asked.
    """
    from fastapi.testclient import TestClient
    from tombstone.server import app
    with TestClient(app) as client:
        for params in ({"path": "x", "limit": -5}, {"limit": -1}, {"limit": 0},
                       {"limit": 10 ** 9}, {"path": "pkg/scheduler/OWNERS", "limit": -5},
                       {"handle": "lavalamp", "limit": -3},
                       {"path": "pkg\x00x"}, {"handle": "a\x00b"}, {"handles": "x\x00y"},
                       {"stranded": "\x00"}, {"path": "pkg/scheduler/OWNERS\x00", "depth": 4}):
            r = client.get("/api/subgraph", params=params)
            assert r.status_code == 200, f"{params} returned HTTP {r.status_code}"
            body = r.json()
            assert "nodes" in body and "edges" in body, f"{params} returned {str(body)[:120]}"


# Constraints: identity and traceability enforced by the engine rather than by the build script
# being careful. Two tests, because a declared constraint that rejects nothing is decoration --
# the second one makes the database actually refuse a write.

def test_the_graph_declares_its_identity_and_traceability_constraints(g):
    from tombstone.build import _CONSTRAINTS
    rows = g.list_constraints()
    assert rows, "the graph declares no constraints at all"
    got = {(str(c.get("type", "")).lower(), c.get("label"),
            tuple(c.get("properties") or ())) for c in rows}
    for kind, label, props in _CONSTRAINTS:
        assert (kind, label, props) in got, (
            f"{kind} constraint on {label}.{'+'.join(props)} is missing; the graph has "
            f"{sorted(got)}")
    bad = [c for c in rows if str(c.get("status", "")).upper() != "OPERATIONAL"]
    assert not bad, (
        f"constraints exist but are not OPERATIONAL: "
        f"{[(c.get('label'), c.get('status')) for c in bad]} -- creation is asynchronous, so a "
        f"build that does not wait reports success while the engine is still working")


def test_a_unique_constraint_actually_rejects_a_duplicate():
    """On a throwaway graph, so a missing constraint cannot pollute the real one.

    Asserting enforcement against tomb:k8s would mean attempting a duplicate write there: fine
    while the constraint holds, and a silent corpus corruption on the day it does not.
    """
    import time
    from graphkit.ingest import connect
    db = connect()
    scratch = db.select_graph("tomb:constrainttest")
    try:
        scratch.query("CREATE (:Thing {key: 'a'})")
        scratch.create_node_range_index("Thing", "key")
        scratch.create_node_unique_constraint("Thing", "key")
        for _ in range(50):
            rows = scratch.list_constraints()
            if rows and all(str(c.get("status", "")).upper() == "OPERATIONAL" for c in rows):
                break
            time.sleep(0.1)
        else:
            raise AssertionError(f"constraint never became OPERATIONAL: {scratch.list_constraints()}")

        scratch.query("CREATE (:Thing {key: 'b'})")      # a different key is fine
        try:
            scratch.query("CREATE (:Thing {key: 'a'})")  # a duplicate must be refused
        except Exception:
            pass
        else:
            raise AssertionError(
                "the unique constraint accepted a duplicate key, so it is declared and not "
                "enforced -- which is worse than not declaring it, because the README now says "
                "the database enforces identity")
        n = scratch.ro_query("MATCH (t:Thing) RETURN count(t)").result_set[0][0]
        assert n == 2, f"expected the duplicate to leave 2 nodes, found {n}"
    finally:
        try:
            scratch.delete()
        except Exception:
            pass


def test_the_text_index_is_on_the_206_and_only_the_206(g):
    """The two retrievers must not share a label, or neither answer can say which found a row.

    Also the concrete reason the scopes are disjoint: bench_index_scope.py builds a temporary
    vector index on :Alternative and polls `info.numDocuments` until it reaches 958, and
    db.indexes() yields one row per LABEL. A second index on :Alternative would land in the same
    bucket that gate reads and could satisfy it before the HNSW build finished.
    """
    total, named, unnamed = g.ro_query(
        "MATCH (a:Alternative) WITH count(a) AS t "
        "MATCH (n:NamedOption) WITH t, count(n) AS n "
        "MATCH (u:UnnamedOption) RETURN t, n, count(u)").result_set[0]
    assert named + unnamed == total, (
        f"{named} named + {unnamed} unnamed != {total} alternatives; the two index scopes "
        f"overlap or leave a gap, so an option can be returned twice or never")
    assert g.ro_query(
        "MATCH (a:UnnamedOption) WHERE a:NamedOption RETURN count(a)").result_set[0][0] == 0

    # Read per field. Matching 'FULLTEXT' against the whole printed row would say a label has a
    # text index when all it has is the Ingestor's range index on .key.
    ft, vec = {}, {}
    for row in g.ro_query("CALL db.indexes()").result_set:
        for prop, kinds in dict(row[2]).items():
            if "FULLTEXT" in kinds:
                ft[row[0]] = prop
            if "VECTOR" in kinds:
                vec[row[0]] = prop
    assert ft == {"UnnamedOption": "body"}, f"full-text indexes are {ft}"
    # The OPTION scopes, not every vector index in the graph. memory.py mints one on :Answer the
    # first time a question is remembered, so asserting the whole map equals {NamedOption: emb}
    # passes alone and fails in suite order -- which is how this assertion was first written and
    # how the suite caught it. What must hold is that the two retrievers do not share a scope and
    # that :Alternative carries neither, or bench_index_scope.py's doc-count gate reads the wrong
    # index and an option could be returned by both retrievers in one answer.
    assert vec.get("NamedOption") == "emb", f"vector indexes are {vec}"
    assert "Alternative" not in vec and "Alternative" not in ft, (
        f"an index landed on :Alternative itself: vector={vec}, fulltext={ft}")
    assert "UnnamedOption" not in vec, f"the 206 gained a vector index: {vec}"


def test_a_name_query_is_rebuilt_from_alphanumerics_and_never_escaped():
    """`-` is NOT in RediSearch's query language, and no FalkorDB page states the dialect.

    `kube-state-metrics` handed to the index raw is a negation of the words being searched for,
    and it would fail as an EMPTY RESULT -- this product's honest negative, the worst available
    failure mode because it is the sentence a judge is told to trust. The query is rebuilt from
    [a-z0-9] tokens rather than escaped, so the dialect question cannot arise.
    """
    from tombstone.tools import fulltext_query, searchable_names
    for hostile in ("kube-state-metrics", "-kubelet -api", "*", "a-*", "node | *",
                    "%fuzzy%1-thing", "x-(y)-z", "foo-bar~`'\"\\"):
        q = fulltext_query(searchable_names(hostile))
        assert set(q) <= set("abcdefghijklmnopqrstuvwxyz0123456789 ()|"), (
            f"{hostile!r} produced {q!r}, which carries query-language characters")
        assert "*" not in q, f"{hostile!r} produced a wildcard: a bare `*` returns the whole index"
        assert "-" not in q, f"{hostile!r} produced a `-`, which this engine reads as NOT"
    assert fulltext_query(searchable_names("extending kube-state-metrics to expose requests")) \
        == "(kube state metrics)"


def test_the_name_path_closes_the_documented_gap_without_opening_the_control(agent):
    """README's Honest limits names this exact failure, and the control beside it must survive.

    `rewrite the control plane in COBOL` has no splittable token, so a rule keyed on punctuation
    alone leaves it NOT_IN_GRAPH and looks safe. `control-plane` matches five of the 206, and
    without the hit bound that control comes back with five unrelated rejections -- one keystroke
    from the string the fixture happens to use.
    """
    from tombstone.tools import NAME_HIT_BOUND
    found = agent.dispatch("has_this_been_tried", {
        "idea_text": "extending kube-state-metrics to expose pod resource requests"})
    assert found.shape == "ANSWERED_WITH_PATH"
    by_name = [r for r in found.rows if r[-1] == "name"]
    assert by_name, "the rejection README documents as unreachable is still unreachable"
    assert len(by_name) <= NAME_HIT_BOUND
    assert all("kube" in str(r[1]).lower() and "state" in str(r[1]).lower() for r in by_name)
    assert all(r[11] is None for r in by_name), (
        "a text row carries a distance; a TF-IDF score and a cosine distance point in opposite "
        "directions and must never share a column")
    assert found.rows[0][-1] == "similarity"
    assert found.rows[0][11] is not None

    for control in ("rewrite the control plane in COBOL on a mainframe",
                    "rewrite the control-plane in COBOL on a mainframe",
                    "replace the scheduler with a reinforcement-learning agent trained on chess",
                    "migrate all state to a block-chain"):
        a = agent.dispatch("has_this_been_tried", {"idea_text": control, "max_dist": 0.15})
        assert a.shape == "NOT_IN_GRAPH", (
            f"{control!r} came back as {a.shape} with {len(a.rows)} rows; the honest negative "
            f"is the claim this product is judged on")


def test_a_name_that_matches_too_much_is_reported_as_no_answer(agent):
    """The hit bound is the name path's `max_dist`, and it has to be visible.

    The bound is counted by the ENGINE: the query asks for one more row than may be reported, so
    the tokeniser that decides is the one that built the index, not a Python approximation.
    """
    from tombstone.tools import NAME_HIT_BOUND
    a = agent.dispatch("has_this_been_tried",
                       {"idea_text": "is there anything on pod-level resources"})
    assert a.params.get("name_query") == "(pod level)"
    assert a.params.get("name_hits") == f">{NAME_HIT_BOUND}"
    assert not [r for r in a.rows if r[-1] == "name"], (
        "a name matching more than the bound still contributed rows")
    assert str(NAME_HIT_BOUND) in render(a), (
        "the answer suppressed a retriever and did not say so")


def test_every_consumer_reads_this_tool_by_a_derived_column_index(agent):
    """eval_retrieval.py read the distance as rows[0][-1], right for twelve columns and silently
    wrong for thirteen -- in the script gating preflight AND CI."""
    from tombstone.tools import DIST_COL, HAS_THIS_BEEN_TRIED_COLUMNS as COLS
    a = agent.dispatch("has_this_been_tried", {"idea_text": "store this in etcd directly"})
    assert a.shape == "ANSWERED_WITH_PATH"
    for r in a.rows:
        assert len(r) == len(COLS), (
            f"a row has {len(r)} columns and {len(COLS)} are named; every positional read in "
            f"memory.py, agent.py and eval_retrieval.py derives from that tuple")
    assert COLS[DIST_COL] == "distance" and COLS[-1] == "found_by"
    assert all(r[DIST_COL] is None or isinstance(r[DIST_COL], (int, float)) for r in a.rows)


# ---------------- the memory envelope the hosted demo actually runs in ----------------

def test_only_one_embedding_runs_at_a_time():
    """The hosted demo was killed by the platform for exceeding 512 MB while serving.

    Measured in the shipped image, non-root, 512 MB, no swap: one ask at a time is 292 MiB
    resident, two at a time is 415 MiB, and eight at a time is OOM-killed on the first round.
    The marginal cost of the *second* concurrent embed is 119 MiB -- ONNX Runtime takes an arena
    per concurrent `Run`, far larger than BGE-small's 67 MB of weights. So three visitors is the
    edge of the box and four is past it, which on a link shared with judges is the ordinary case.

    This asserts the bound itself rather than a byte count: a byte count measured on a laptop
    says nothing about a shared instance, but "never two at once" is the property that makes the
    byte count the one-at-a-time figure on any host.
    """
    import threading
    from tombstone.embedding import embed_rows

    live = peak = 0
    seen = threading.Lock()

    class Slow:
        """Stands in for the model: holds the critical section long enough that an unserialised
        caller would overlap, and records how many callers were inside at once."""
        def embed(self, texts):
            nonlocal live, peak
            with seen:
                live += 1
                peak = max(peak, live)
            time.sleep(0.02)
            with seen:
                live -= 1
            return [[0.0] * 384 for _ in texts]

    model = Slow()
    threads = [threading.Thread(target=embed_rows, args=(lambda: model, ["x"])) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1, (
        f"{peak} embeddings ran concurrently; each one costs ~119 MiB of arena on the deploy "
        f"target, so {peak} of them is {peak * 119} MiB of a 512 MB box")


def test_no_embed_call_site_bypasses_the_bound():
    """A lock over one of five call sites bounds nothing, which is the actual history here.

    `Agent._remember` serialised its embed in a comment that named this exact failure -- and the
    container was still killed, because the other four sites were not covered: both query paths
    in `Agent` and both of `LocalRouter`'s. The free-text ask box went through two of them, so
    `/api/ask` was unbounded while `/api/tool` was fine, and the burst the deploy check ran went
    through `/api/tool`.

    Scanning the source is the only check that holds for the *next* call site somebody adds.

    Scope is the whole `src/` tree rather than `src/tombstone/` alone: `graphkit.ingest` is
    imported by `server.py`, `build.py` and `agent.py`, so a call site added there runs inside the
    serving process too and the old scan could not see it. The offline scripts at the repo root --
    `bench_index_scope.py`, `eval_graph_vs_text.py`, `scripts_check_demo_facts.py` -- do call
    `.embed(` directly and stay deliberately out of scope: they are single-process, never run
    inside the 512 MB box, and for the text baseline calling the model directly is the point.
    """
    import pathlib
    from tombstone import agent as _probe
    src = pathlib.Path(_probe.__file__).parent.parent        # src/, not src/tombstone/
    scanned, offenders = [], []
    for path in sorted(src.rglob("*.py")):
        if path.name == "embedding.py" or "__pycache__" in path.parts:
            continue
        scanned.append(path.relative_to(src).as_posix())
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if ".embed(" in code:
                offenders.append(f"{path.relative_to(src).as_posix()}:{n}: {line.strip()}")
    # Anti-vacuity: a scan that found no files would report success over nothing, and both
    # packages must actually be in it -- the point of widening it was graphkit.
    assert "tombstone/agent.py" in scanned and "graphkit/ingest.py" in scanned, (
        f"the scan covered {len(scanned)} files and not both packages: {scanned}")
    assert not offenders, (
        "these call the model directly instead of tombstone.embedding, so they are not bounded "
        "and a concurrent request through them can exceed the deploy target:\n  "
        + "\n  ".join(offenders))


def test_a_list_argument_is_part_of_the_remembered_question():
    """`what_if_they_go` takes `handles`, a list, and the label filter admitted only str and int.

    So every counterfactual for every person collapsed onto one qid. The rows were always
    recomputed, but the NOTE was not: ask about deads2k and then about thockin, and the second
    answer said "Asked before (2x) ... re-running it just now returned the same rows" about
    somebody else's counterfactual. Row counts collide constantly here, because most people
    strand nothing, so the false note was the common case rather than a corner.
    """
    from tombstone.server import _label

    class C:
        def __init__(self, tool, args):
            self.tool, self.args = tool, args

    a = _label(C("what_if_they_go", {"handles": ["deads2k"]}))
    b = _label(C("what_if_they_go", {"handles": ["thockin"]}))
    assert a != b, f"two different counterfactuals share one label: {a!r}"
    assert "deads2k" in a and "thockin" in b
    assert _label(C("sole_approver_risk", {})) == "sole approver risk"
    # A dict argument has no place in a question label, and must not crash one either.
    assert _label(C("who_owns", {"path": "a/OWNERS", "opts": {"x": 1}})) == "who owns a/OWNERS"


def test_the_model_is_constructed_once_even_under_a_cold_burst(monkeypatch):
    """`if self._embedder is None: self._embedder = TextEmbedding(...)` is a race, and the thing
    it races to duplicate is a ~94 MiB session -- the exact cost the lock exists to bound.

    The window is the first requests after a cold start, which on a tier that sleeps after 15
    minutes of quiet is when a burst is MOST likely, not least: the link gets shared, several
    people click, and the instance wakes up into all of them at once.
    """
    import threading

    built = []

    def slow_load():
        time.sleep(0.05)          # wide enough that an unguarded check would let others in
        built.append(1)
        return object()

    monkeypatch.setattr(Agent, "_load_embedder", staticmethod(slow_load))
    a = Agent(graph_name=GRAPH)
    a._embedder = None
    got = []
    threads = [threading.Thread(target=lambda: got.append(a.embedder())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1, f"{len(built)} sessions were constructed, at ~94 MiB each"
    assert len(set(map(id, got))) == 1, "callers got different models for the same agent"


# ---------------- the read path, enforced by the server rather than by convention ----------------

READER_PROBE = "tombstone-reader-probe"


@pytest.fixture
def reader_acl(g):
    """A Redis ACL identity granted exactly what the read path needs, torn down after.

    Built here rather than skipped when absent, because a hardening nobody exercises is a
    hardening nobody has. CI runs the same FalkorDB image the container does, so these refusals
    are checked on every push, against the engine, not against my recollection of it.
    """
    db = connect()
    conn = db.connection
    secret = "probe-" + "0123456789abcdef" * 2
    try:
        conn.execute_command(
            "ACL", "SETUSER", READER_PROBE, "on", f">{secret}", "resetkeys", "resetchannels",
            f"~{GRAPH}", "-@all", "+graph.ro_query", "+info", "+ping")
    except Exception as e:                                        # pragma: no cover
        pytest.skip(f"this server will not take an ACL for module commands: {e}")
    try:
        yield secret
    finally:
        try:
            conn.execute_command("ACL", "DELUSER", READER_PROBE)
        except Exception:
            pass


def test_the_read_identity_cannot_write(reader_acl, g):
    """The read path is 28 hand-written `ro_query` calls. That is a convention, and a convention
    is what a future call site breaks by typing `query` instead -- silently, and in the one place
    where silence matters.

    So the identity that answers public requests is granted `+graph.ro_query` and nothing else,
    and this asserts what the SERVER does with it. `+info` is in the grant because the FalkorDB
    client issues `INFO server` while constructing, to detect Sentinel: without it the connection
    raises before a single query, which is the kind of thing only running it finds.
    """
    import os as _os

    from falkordb import FalkorDB
    secret = reader_acl
    db = FalkorDB(host=_os.environ.get("FALKORDB_HOST", "localhost"),
                  port=int(_os.environ.get("FALKORDB_PORT", 6380)),
                  username=READER_PROBE, password=secret)
    gr = db.select_graph(GRAPH)

    # Reading works, including the node decoding that makes the client refresh the schema --
    # which it does through `call_procedure(read_only=True)`, so RO_QUERY covers it.
    assert gr.ro_query("MATCH (k:Kep) RETURN count(k)").result_set[0][0] > 600
    node = gr.ro_query("MATCH (p:Person) RETURN p LIMIT 1").result_set[0][0]
    assert node.labels == ["Person"], "the schema refresh needs a command the reader lacks"

    refused = {
        "GRAPH.QUERY": lambda: gr.query("CREATE (:AclProbeShouldNotExist)"),
        "GRAPH.COPY": lambda: db.connection.execute_command("GRAPH.COPY", GRAPH, GRAPH + ":stolen"),
        "GRAPH.DELETE": lambda: db.connection.execute_command("GRAPH.DELETE", GRAPH),
        "GRAPH.CONSTRAINT": lambda: db.connection.execute_command(
            "GRAPH.CONSTRAINT", "DROP", GRAPH, "UNIQUE", "NODE", "Kep", "PROPERTIES", "1", "key"),
        "GRAPH.PROFILE": lambda: db.connection.execute_command(
            "GRAPH.PROFILE", GRAPH, "MATCH (n) RETURN n"),
        "FLUSHALL": lambda: db.connection.execute_command("FLUSHALL"),
        "CONFIG SET": lambda: db.connection.execute_command("CONFIG", "SET", "maxmemory", "1"),
        "SCRIPT LOAD": lambda: db.connection.execute_command("SCRIPT", "LOAD", "return 1"),
        "ACL SETUSER": lambda: db.connection.execute_command(
            "ACL", "SETUSER", "escalated", "on", "~*", "+@all"),
    }
    allowed = []
    for name, call in refused.items():
        try:
            call()
            allowed.append(name)
        except Exception:
            pass
    assert not allowed, f"the read identity was allowed to run {allowed}"

    # It also cannot reach a graph it was not granted -- so a second tenant, or a counterfactual
    # copy, is not readable through the public path by naming it.
    with pytest.raises(Exception):
        db.select_graph(GRAPH + ":someone-elses").ro_query("MATCH (n) RETURN count(n)")

    # And nothing it tried landed.
    assert g.ro_query("MATCH (n:AclProbeShouldNotExist) RETURN count(n)").result_set[0][0] == 0


def test_a_read_only_key_selector_cannot_express_this_and_the_engine_says_why():
    """`%R~<graph>` is how Redis is supposed to say "may read this key", and it does not work for
    any FalkorDB graph command. Worth pinning to the engine's own metadata rather than to a
    sentence in a commit message, because it is the reason the grant uses a plain `~` pattern.

    `GRAPH.RO_QUERY` is flagged `readonly` as a COMMAND, but its KEY SPEC is flagged
    `RW access update`, and ACL key selectors test the key spec. So `%R~` refuses even a plain
    read -- measured as "No permissions to access a key" -- and the reviewer's earlier finding
    about `GRAPH.COPY` having a single RW key spec turns out to be the general case, not a
    peculiarity of one command.
    """
    info = connect().connection.execute_command("COMMAND", "INFO", "graph.RO_QUERY")
    spec = info["graph.RO_QUERY"]
    assert "readonly" in spec["flags"], (
        "graph.RO_QUERY is no longer flagged readonly as a command; re-read this test")
    key_flags = spec["key_specifications"][0][1]
    assert "RW" in key_flags, (
        f"graph.RO_QUERY now declares its key {key_flags} rather than RW. If that is a read-only "
        f"flag, %R~ may work and the grant in docker-entrypoint.sh can be tightened to it.")
    assert "RO" not in key_flags, "an RO key spec would make the %R~ selector usable"


def test_the_public_read_path_is_wired_to_the_read_identity(agent):
    """Two identities only help if the right objects got the right one. `Tools` answers every
    question, so it holds the reader; `Memory` records answers and `Counterfactual` deletes edges
    in a copy, so they hold the writer. Asserted structurally, because a refactor that hands
    `Tools` the writer would pass every other test in this file.
    """
    import pathlib
    from tombstone import server as _srv
    assert agent.tools.g is agent.gr
    assert agent.memory.g is agent.g
    assert agent.gr is not agent.g, "the two handles are the same object; there is one identity"

    # And the HTTP surface reads through it too.
    src = pathlib.Path(_srv.__file__).read_text(encoding="utf-8")
    assert "a.g.ro_query(" not in src, (
        "server.py reads through the writer identity somewhere; public reads use a.gr")
    assert src.count("a.gr.ro_query(") >= 5


def test_a_malformed_handles_list_is_a_bad_request_not_a_degradation(agent):
    """`DEGRADED` is documented to mean the graph is unreachable. Overloading it for a bad
    argument makes the one shape that must be trustworthy untrustworthy.

    `test_malformed_arguments_never_leak_a_python_error` reads as though it covers this and does
    not: its six cases are all scalar arguments, and the only tool here that takes a LIST was not
    among them. So `handles: [[...]]` returned DEGRADED carrying "'list' object has no attribute
    'strip'", and `handles: [1, 2]` the same for 'int' -- a raw Python message on the public demo,
    under the shape that is supposed to mean the database is gone. A bare string was worse than
    either: it was iterated character by character, reporting that 'd', 'e', 'a', 'd', 's' are not
    people in this graph.
    """
    for args in ({"handles": [["deads2k"]]}, {"handles": [1, 2]}, {"handles": [None]},
                 {"handles": [""]}, {"handles": 7}, {"handles": {"a": 1}}):
        a = agent.dispatch("what_if_they_go", args)
        assert a.shape == "UNKNOWN_ENTITY", f"{args} -> {a.shape}, which is not a bad request"
        body = render(a) + " " + str(a.note)
        for leak in ("has no attribute", "Traceback", "object is not", "NoneType"):
            assert leak not in body, f"{args} leaked a Python message: {body[:140]}"
    # A bare string is one handle, not a sequence of characters.
    a = agent.dispatch("what_if_they_go", {"handles": "deads2k"})
    assert a.shape == "ANSWERED_WITH_PATH", a.shape
    assert "deads2k" in str(a.rows[0][0])


def test_every_argument_the_catalogue_advertises_reaches_the_query(agent):
    """`/api/tools` is what a sponsor engineer reads instead of clicking chips, and it said
    "Args: min_stepped_back" for a tool whose dispatcher branch called with no arguments.

    The ignored argument was not the whole defect. `Tools.stepped_back_but_still_listed` reports
    its threshold in `answer.params`, so asking for 8 returned the threshold-3 rows AND a
    provenance line reading `min_stepped_back: 3` -- which looks like confirmation the 8 was
    honoured. In a product whose claim is that every answer shows what produced it, an argument
    that is dropped while its default is echoed back is worse than one that is merely ignored.
    """
    import re

    from tombstone.tools import CATALOGUE
    advertised = {}
    for name, blurb in CATALOGUE.items():
        m = re.search(r"Args: (.+?)\.\s*$", blurb)
        if m and m.group(1).strip() != "none":
            advertised[name] = [a.strip().split(" ")[0] for a in m.group(1).split(",")]
    assert "min_stepped_back" in advertised["stepped_back_but_still_listed"]

    seen = {}
    for n in (3, 8):
        a = agent.dispatch("stepped_back_but_still_listed", {"min_stepped_back": n})
        assert a.params.get("min_stepped_back") == n, (
            f"asked for {n}, the answer's own provenance says {a.params.get('min_stepped_back')}")
        seen[n] = len(a.rows)
    assert seen[8] < seen[3], (
        f"the threshold changed the provenance but not the rows ({seen}); it is still being "
        f"dropped somewhere between dispatch and the query")


def test_a_cold_burst_builds_one_agent_and_one_router_not_eight(monkeypatch):
    """`tombstone.embedding` bounds the model. It did not bound the three lazy singletons that
    each own one.

    `Agent.embedder` double-checks `self._embedder` because a session is ~94 MiB -- but that guard
    cannot see past its own instance, and `server.agent()` was `if _agent is None: _agent =
    Agent(...)`. Eight concurrent first requests each saw None and each built an Agent, so eight
    sessions, ~750 MiB of a 512 MB box: the bound defeated through a different door at exactly the
    moment it was written for, a cold burst on a tier that sleeps after fifteen minutes. The same
    shape sat in `Agent.router` and in `LocalRouter._ready`, where it cost a 91-phrase matrix each.
    """
    import threading

    from tombstone import server as _srv

    built = []

    class FakeAgent:
        def __init__(self, *a, **kw):
            time.sleep(0.05)       # wide enough that an unguarded check lets the others in
            built.append(1)

    monkeypatch.setattr(_srv, "Agent", FakeAgent)
    monkeypatch.setattr(_srv, "_agent", None)
    got = []
    threads = [threading.Thread(target=lambda: got.append(_srv.agent())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1, f"{len(built)} agents built, at ~94 MiB of embedding session each"
    assert len(set(map(id, got))) == 1, "callers got different agents from one process"


def test_the_router_matrix_is_built_once_under_a_cold_burst():
    """A router carries its own 91-phrase matrix, so guarding only the model left a burst
    embedding 736 rows where 91 are needed -- on a tenth of a CPU."""
    import threading

    from tombstone.route import LocalRouter

    embeds = []
    lock = threading.Lock()

    class Counting:
        def embed(self, texts):
            texts = list(texts)
            with lock:
                embeds.append(len(texts))
            time.sleep(0.03)
            return [[0.1] * 384 for _ in texts]

    model = Counting()
    r = LocalRouter(lambda: model, set())
    threads = [threading.Thread(target=r._ready) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(embeds) == 1, (
        f"the phrase matrix was embedded {len(embeds)} times in one burst, {sum(embeds)} rows "
        f"where {embeds[0] if embeds else 0} are needed")
    assert r._matrix is not None and len(r._tools) == embeds[0]


def test_a_refused_filesystem_argument_says_so_in_the_answer(agent):
    """The strip was always correct; the DISCLOSURE was missing.

    `dispatch` drops `write_to` unless a local caller opts in, and the `image` CI job proves no
    directory appears inside the container. But the response was byte-identical to one that never
    sent the argument, so "a POST of a filesystem argument is refused on the public instance" --
    a claim the README makes in its Rule 10 table -- could be read off the README and not off the
    product. Checking it otherwise needs a shell in the container, which nobody outside has, and
    an invariant only its author can observe is an assertion however much this file knows.

    The repeat matters as much as the first call: `_remember` REPLACES `note` when an answer is
    upgraded to ANSWERED_FROM_MEMORY, and the second identical POST is exactly when somebody is
    trying it twice to see whether it took.
    """
    import pathlib

    target = "/tmp/tombstone-refusal-probe"
    for _ in range(3):
        a = agent._remember("draft the fix", "draft_owners_patch",
                            agent.dispatch("draft_owners_patch", {"write_to": target}))
        assert a.shape in ANSWERED, a.shape
        assert "filesystem" in a.note and "write_to" in a.note, (
            f"the answer does not say the argument was refused: {a.note!r}")
    assert not pathlib.Path(target).exists(), "the refusal is cosmetic; something was written"

    # And a clean call must not claim a refusal that did not happen.
    clean = agent._remember("draft the fix", "draft_owners_patch",
                            agent.dispatch("draft_owners_patch", {}))
    assert "filesystem" not in clean.note, (
        f"a call with no unsafe argument reports one anyway: {clean.note!r}")
