"""An approval-retirement draft preserves the upstream OWNERS policy text."""
from copy import deepcopy

import pytest
import yaml

from tombstone import act


SOURCE = (
    "# Disable inheritance: this team must see changes under this package.\n"
    "options:  # inherited ownership is deliberately disabled\n"
    "  no_parent_owners: true\n"
    "approvers:  # approval is distinct from reviewing\n"
    "  - active-owner  # remaining approval capacity\n"
    "  - bob\n"
    "# A retirement finding says nothing about this review responsibility.\n"
    "reviewers:\n"
    "  - bob  # still reviews this area\n"
    "  - reviewer-only\n"
    "emeritus_approvers:\n"
    "  - zeta  # preserve historical order\n"
    "  - alice\n"
    "labels:\n"
    "  - sig/example  # triage policy\n"
)


def test_retire_preserves_reviewers_and_appends_without_reordering_or_mutation():
    before = yaml.safe_load(SOURCE)
    saved = deepcopy(before)
    after = act.retire(before, "bob")
    assert before == saved
    assert after["approvers"] == ["active-owner"]
    assert after["reviewers"] == saved["reviewers"] == ["bob", "reviewer-only"]
    assert after["emeritus_approvers"] == ["zeta", "alice", "bob"]
    assert after["options"] == saved["options"]
    assert after["labels"] == saved["labels"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_retire_source_preserves_comments_key_order_and_unrelated_bytes(newline):
    source = SOURCE.replace("\n", newline)
    before = yaml.safe_load(source)
    saved = deepcopy(before)
    expected = source.replace("  - bob" + newline, "", 1)
    expected = expected.replace("  - alice" + newline,
                                "  - alice" + newline + "  - bob" + newline, 1)
    after = act.retire_source(source, before, "bob")
    assert after == expected
    assert before == saved
    assert yaml.safe_load(after) == act.retire(saved, "bob")
    assert yaml.safe_load(after)["reviewers"] == saved["reviewers"]
    assert after.index("options:") < after.index("approvers:") < after.index("reviewers:")


def test_retire_does_not_duplicate_an_existing_emeritus_or_reorder_it():
    before = {"approvers": ["bob", "active-owner"], "reviewers": ["bob"],
              "emeritus_approvers": ["zeta", "bob", "alice"]}
    saved = deepcopy(before)
    after = act.retire(before, "bob")
    assert before == saved
    assert after["emeritus_approvers"] == ["zeta", "bob", "alice"]
    assert after["reviewers"] == ["bob"]


def test_source_with_existing_emeritus_only_removes_active_approval_membership():
    source = SOURCE.replace("  - alice\nlabels:", "  - alice\n  - bob\nlabels:")
    owners = yaml.safe_load(source)
    after = act.retire_source(source, owners, "bob")
    assert after == source.replace("  - bob\n", "", 1)
    assert yaml.safe_load(after) == act.retire(owners, "bob")
    assert yaml.safe_load(after)["emeritus_approvers"] == ["zeta", "alice", "bob"]


def test_emeritus_append_keeps_the_following_policy_comment_adjacent_to_its_key():
    source = (
        "approvers:\n  - alice\n  - bob\n"
        "emeritus_approvers:\n  - zeta\n"
        "# Labels are a separate triage policy.\n"
        "labels:\n  - sig/example\n"
    )
    owners = yaml.safe_load(source)
    after = act.retire_source(source, owners, "bob")
    expected = source.replace("  - bob\n", "", 1).replace(
        "  - zeta\n", "  - zeta\n  - bob\n", 1)
    assert after == expected
    assert "# Labels are a separate triage policy.\nlabels:\n" in after
    assert yaml.safe_load(after) == act.retire(owners, "bob")


@pytest.mark.parametrize("source", [
    SOURCE.rstrip("\n"),
    "approvers:\n  - alice\n  - bob\nreviewers:\n  - bob",
])
def test_source_without_final_newline_is_refused_instead_of_drafting_an_invalid_diff(source):
    owners = yaml.safe_load(source)
    with pytest.raises(ValueError):
        act.retire_source(source, owners, "bob")


def test_sole_approver_removal_preserves_policy_comments_and_reviewers():
    source = (
        "# This package deliberately has its own ownership policy.\n"
        "approvers:  # preserve this policy note\n"
        "  # An empty local approver list will inherit from an ancestor.\n"
        "  - bob\n"
        "reviewers:\n"
        "  - bob  # reviewing has not ended\n"
        "options:\n"
        "  no_parent_owners: true\n"
    )
    before = yaml.safe_load(source)
    saved = deepcopy(before)
    after = act.retire_source(source, before, "bob")
    assert before == saved
    assert yaml.safe_load(after) == act.retire(saved, "bob")
    assert "approvers" not in yaml.safe_load(after)
    assert yaml.safe_load(after)["reviewers"] == ["bob"]
    assert yaml.safe_load(after)["emeritus_approvers"] == ["bob"]
    for note in ("# This package deliberately has its own ownership policy.",
                 "# preserve this policy note",
                 "# An empty local approver list will inherit from an ancestor.",
                 "  - bob  # reviewing has not ended\n"):
        assert note in after


@pytest.mark.parametrize("source", [
    "approvers: [active-owner, bob]\nreviewers:\n  - bob\n",
    "approvers:\n  - bob\nreviewers: [bob, reviewer-only]\n",
    "approvers: &active\n  - bob\nreviewers:\n  - other\n",
    "approvers: &active\n  - bob\nreviewers: *active\n",
    "approvers:\n  - active-owner\napprovers:\n  - bob\n",
])
def test_retire_source_refuses_unsupported_yaml_instead_of_reserializing(source):
    owners = yaml.safe_load(source)
    saved = deepcopy(owners)
    with pytest.raises(ValueError):
        act.retire_source(source, owners, "bob")
    assert owners == saved


@pytest.mark.parametrize("changed", [
    {"approvers": ["bob"]},
    {"reviewers": ["someone-else"]},
    {"options": {"no_parent_owners": False}},
    {"emeritus_approvers": ["different-history"]},
])
def test_retire_source_refuses_stale_parsed_data(changed):
    owners = yaml.safe_load(SOURCE)
    owners.update(changed)
    saved = deepcopy(owners)
    with pytest.raises(ValueError):
        act.retire_source(SOURCE, owners, "bob")
    assert owners == saved


def test_reviewer_only_membership_cannot_justify_an_approval_retirement():
    source = "approvers:\n  - active-owner\nreviewers:\n  - bob\n"
    owners = yaml.safe_load(source)
    saved = deepcopy(owners)
    with pytest.raises(ValueError):
        act.retire_source(source, owners, "bob")
    assert owners == saved


def test_unified_text_uses_real_policy_context_without_a_reviewers_edit():
    after = SOURCE.replace("  - bob\n", "", 1).replace(
        "  - alice\n", "  - alice\n  - bob\n", 1)
    diff = act.unified_text("pkg/OWNERS", SOURCE, after)
    assert diff.startswith("--- a/pkg/OWNERS\n+++ b/pkg/OWNERS\n")
    assert "   no_parent_owners: true\n" in diff
    assert " approvers:  # approval is distinct from reviewing\n" in diff
    assert " # A retirement finding says nothing about this review responsibility.\n" in diff
    assert "-  - bob\n" in diff and "+  - bob\n" in diff
    assert "-  - bob  # still reviews this area\n" not in diff
    assert "-reviewers:" not in diff
