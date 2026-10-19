# Sending these upstream

The two patches in this directory were drafted from the graph. One is ready to send to
`kubernetes/kubernetes` after a small hand-edit. The other is not, and the reason it is not is
filed as [#13](https://github.com/aviralgarg05/tombstone/issues/13).

Both findings were re-checked against `master` on **19 Oct 2026** and both files still match the
snapshot this project was built from, so the contradictions are live.

---

## Ready: `hack/jenkins/OWNERS`

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

**Hand-edit before sending:** keep the leading comment. The drafted diff is against a canonical
re-serialisation of the parsed file, so it drops the `# See the OWNERS docs` line. Make the edit
by hand in the real file instead of applying the patch:

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
> I deliberately did not send a second, similar change for
> `pkg/scheduler/framework/autoscaler_contract/OWNERS`: there the person is listed in both
> `approvers` and `reviewers`, and stepping back from approving is not the same as giving up
> reviewing, so that one needs a human decision I am not in a position to make.
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

## Not ready: `pkg/scheduler/framework/autoscaler_contract/OWNERS`

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

`x13n` is emeritus in three other files and still an active approver here — the finding is real.
But the drafted patch also **removes them from `reviewers`**, and the patch's own header says that
part is not justified by the finding. It additionally drops the comment explaining why
inheritance is disabled.

Sending a change that deletes a policy comment and makes an edit the tool itself disclaims is how
you get a reputation with maintainers. Fix [#13](https://github.com/aviralgarg05/tombstone/issues/13)
first, or hand-write the narrow version: move `x13n` out of `approvers` only, leave `reviewers`,
`options` and both comments exactly as they are.
