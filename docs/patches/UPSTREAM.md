# Sending these upstream

The two patches in this directory are local drafts from the graph. Both now preserve the
original policy comments, key order and reviewer membership, addressing the drafting defect in
[#13](https://github.com/aviralgarg05/tombstone/issues/13). Neither has been sent upstream.

Both source files were re-checked against Kubernetes `master` on **23 Oct 2026**, at commit
`061e55d37f0219a7ca8f0b980c8e86b7cd706347`. Their parsed contents still match this snapshot;
the original text is now retained with it. The finding is still a question about intent, not
evidence that either person should stop approving an area. Re-check upstream before using a
draft and ask the person or area maintainers to confirm the intended change.

---

## Draft: `hack/jenkins/OWNERS`

Upstream today:

```yaml
# See the OWNERS docs at https://go.k8s.io/owners

approvers:
  - bentheelder
  - cblecker
  - spiffxp
reviewers:
  - sig-testing-reviewers
```

`spiffxp` is recorded in `emeritus_approvers` in **nine** other OWNERS files and is still an
active approver here. They appear only in `approvers`, not in `reviewers`, so moving them is a
clean single change.

The draft retains the leading comment and changes only approval membership and the new
emeritus entry. Its proposed file is:

```yaml
# See the OWNERS docs at https://go.k8s.io/owners

approvers:
  - bentheelder
  - cblecker
reviewers:
  - sig-testing-reviewers
emeritus_approvers:
  - spiffxp
```

### PR body

> **What type of PR is this?**
>
> /kind cleanup
>
> **What this PR does / why we need it**:
>
> `spiffxp` is listed in `emeritus_approvers` in nine other OWNERS files across this repository,
> and is still listed as an active approver in `hack/jenkins/OWNERS`. This moves them to
> `emeritus_approvers` here for consistency with the rest of the tree.
>
> I found this by building a graph over this repository's OWNERS files and looking for people
> whose record is inconsistent across files — recorded as having stepped back in many places,
> still named as an active approver in one or two. This was the clearest case.
>
> **If `spiffxp` is deliberately still approving this area, please close this** — the inconsistency
> is then in the other nine files, not this one, and only they can say which.
>
> **Special notes for your reviewer**:
>
> The drafting tool preserves reviewer membership independently of approval membership. Any
> similar change for `pkg/scheduler/framework/autoscaler_contract/OWNERS` also needs the named
> person's or area maintainers' confirmation; these graph findings do not establish intent.
>
> **Does this PR introduce a user-facing change?**
>
> ```release-note
> NONE
> ```

Add `/sig testing` if the bot does not label it automatically — `hack/jenkins` sits under
sig-testing's `reviewers` line.

### Before you open it

- Read [the contributor guide](https://github.com/kubernetes/community/blob/master/contributors/guide/README.md)
  and sign the CLA if you have not. The bot will block the PR otherwise.
- One file, one change, no other edits in the branch.
- Expect it to sit for a while. OWNERS changes usually want an ack from the person named.

---

## Draft: `pkg/scheduler/framework/autoscaler_contract/OWNERS`

Upstream today:

```yaml
# See the OWNERS docs at https://go.k8s.io/owners

# Disable inheritance as code changes under this package should be known to sig-autoscaling team.
options:
  no_parent_owners: true
approvers:
  - sig-autoscaling-maintainers
  - x13n
reviewers:
  - sig-autoscaling-maintainers
  - x13n
```

`x13n` is emeritus in three other files and still an active approver here. The draft now moves
`x13n` out of `approvers` only and leaves `reviewers`, `options` and both comments intact. It
does not claim that approval responsibility in this area has ended: that requires human
confirmation. A missing or stale original source is refused, so a legacy parsed-only snapshot
cannot silently recreate this file without its policy comments.
