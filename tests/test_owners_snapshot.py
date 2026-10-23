"""Original OWNERS bytes survive ingestion and remain required for safe drafts."""
from __future__ import annotations

import gzip
import json
from types import SimpleNamespace

import yaml

from tombstone.agent import Agent
from tombstone.corpus import Corpus
from tombstone.snapshot import export, load
from tombstone.tools import Answer


SOURCE = ("# Policy belongs to the upstream maintainers.\n\n"
          "options:\n  no_parent_owners: true\n"
          "approvers:\n  - alice\n  - bob\n"
          "reviewers:\n  - bob\n")


def test_corpus_keeps_original_owners_text(tmp_path):
    keps, repo = tmp_path / "keps", tmp_path / "k8s"
    keps.mkdir()
    repo.mkdir()
    (repo / "OWNERS").write_text(SOURCE, encoding="utf-8")
    aliases = tmp_path / "aliases.yaml"
    aliases.write_text("aliases: {}\n", encoding="utf-8")
    corpus = Corpus().load(str(keps), str(repo), str(aliases))
    assert corpus.owners_texts == {"OWNERS": SOURCE}
    assert corpus.owners["OWNERS"] == yaml.safe_load(SOURCE)


def test_snapshot_round_trip_keeps_original_text(tmp_path):
    corpus = Corpus()
    corpus.owners = {"OWNERS": yaml.safe_load(SOURCE)}
    corpus.owners_texts = {"OWNERS": SOURCE}
    target = str(tmp_path / "corpus.json.gz")
    export(corpus, target)
    restored = load(target)
    assert restored.owners == corpus.owners
    assert restored.owners_texts == corpus.owners_texts


def test_legacy_snapshot_has_no_invented_source(tmp_path):
    target = tmp_path / "legacy.json.gz"
    with gzip.open(target, "wt", encoding="utf-8") as stream:
        json.dump({"keps": {}, "owners": {"OWNERS": yaml.safe_load(SOURCE)},
                   "aliases": {}, "alternatives": {}}, stream)
    assert load(str(target)).owners_texts == {}


def draft(corpus, write_to=None):
    found = Answer("ANSWERED_WITH_PATH", "stepped_back_but_still_listed",
                   rows=[["bob", 3, [], ["OWNERS"]]])
    agent = SimpleNamespace(
        tools=SimpleNamespace(stepped_back_but_still_listed=lambda **_: found),
        corpus=lambda: corpus,
        _inherited_by=lambda _: "the ancestor",
    )
    return Agent._draft_owners_patch(agent, write_to=write_to)


def test_draft_uses_original_bytes_and_preserves_reviewers(tmp_path):
    corpus = SimpleNamespace(owners={"OWNERS": yaml.safe_load(SOURCE)},
                             owners_texts={"OWNERS": SOURCE}, aliases={})
    answer = draft(corpus, str(tmp_path / "drafts"))
    row = answer.rows[0]
    assert row[3] == "patch"
    assert row[6].startswith("# Policy belongs")
    assert yaml.safe_load(row[6])["reviewers"] == ["bob"]
    assert row[6].index("options:") < row[6].index("approvers:")
    written = (tmp_path / "drafts" / "bob-OWNERS.patch").read_text(encoding="utf-8")
    assert "not preserved" not in written
    assert "does not by itself justify" not in written
    assert "# Policy belongs" in written
    assert "\n# \n" not in written


def test_missing_source_is_refused_without_writing(tmp_path):
    corpus = SimpleNamespace(owners={"OWNERS": yaml.safe_load(SOURCE)}, aliases={})
    answer = draft(corpus, str(tmp_path / "must-not-exist"))
    assert answer.rows[0][3] == "missing_source"
    assert answer.rows[0][5:] == ["", ""]
    assert not (tmp_path / "must-not-exist").exists()


def test_stale_source_is_refused_without_writing(tmp_path):
    corpus = SimpleNamespace(owners={"OWNERS": yaml.safe_load(SOURCE)},
                             owners_texts={"OWNERS": SOURCE.replace("alice", "carol")}, aliases={})
    answer = draft(corpus, str(tmp_path / "must-not-exist"))
    assert answer.rows[0][3] == "unpatchable_source"
    assert not (tmp_path / "must-not-exist").exists()
