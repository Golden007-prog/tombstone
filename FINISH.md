# Finishing this — four steps, about two hours

Everything buildable is done and verified. What remains needs your accounts and your voice.
Order matters: the deploy unblocks the video, and the video unblocks the submission.

---

## 1. Deploy (~20 min, mostly waiting on the build)

```bash
export HF_TOKEN=hf_xxxxxxxxxxxx      # huggingface.co/settings/tokens -> New token -> WRITE
./deploy_hf.sh
```

The script creates the Space, swaps in the Space README (Spaces reads config from its own
front-matter, not this repo's) and uploads 57 files / 1.4 MB. First build takes a few minutes;
after that it boots in seconds.

**Then verify it the way a judge will** — different network, private window, no sign-in:

```bash
curl -s https://aviralgarg05-tombstone.hf.space/api/health | python3 -m json.tool
```

Expect `"falkordb": "up"` and 681 decisions. Then click the chips in the UI.

Once it is live:
```bash
gh repo edit aviralgarg05/tombstone --homepage https://huggingface.co/spaces/aviralgarg05/tombstone
```
and add the link to the top of `README.md` — the 60-second block has a slot for it.

## 2. Record the video (~45 min including retakes)

`docs/DEMO-SCRIPT.md` is written and timed to 3:00, beat by beat, staged on the apiserver
example (falls back to **one** approver — the sharpest row in the data).

Two things that save a bad night:
- **Record the voiceover separately** from the screen capture. Narrating live while clicking is
  the single biggest cause of ten retakes.
- **Record it twice.** The second take is always better and costs ten minutes.

Upload unlisted to YouTube, and set **"Not for Kids"** — that setting is what blocks judges from
viewing. Then open the link in a private window and confirm it plays.

## 3. Publish the blog post (~30 min)

`docs/BLOG-POST.md` is finished, ~1,750 words. Publish to **dev.to**, tagged `falkordb` and
`graphhacks`. Add the live Space link and `docs/img/path.svg` as the header image.

This is the least contested prize on the board — the validators found exactly one published
competitor. It is a separate prize with its own winner.

## 4. Submit (do this by 18:00 IST Sunday, not 23:59)

On the WeMakeDevs panel: repo URL, live URL, video URL, **Track 3 — Company Brain**.

Before you hit submit:
- [ ] `git clone` the repo into an empty directory and run `./run.sh` — the README promises it
- [ ] open the live URL in a private window on a different network
- [ ] confirm the video plays without signing in
- [ ] confirm the repo is public and CI is green

---

## If a judge asks a hard question

**"Isn't 'emeritus means not an approver' circular?"**
No. 28 of the 111 are emeritus in one area and still approve elsewhere — `sttts` is emeritus in 1
file and approves 70. If emeritus meant gone, that number would be zero.

**"Aren't those directories just covered by the parent OWNERS?"**
Yes, and that is the finding. Nothing in Kubernetes is unowned. These lost every *dedicated*
approver, so approval silently widened to people who never signed up for that code. I claimed
"orphaned" at first, was wrong, and the correction is in the README.

**"Could a text search do this?"**
Measured, not argued: `eval_graph_vs_text.py`, graph 7/8 versus TF-IDF 2/8 over the same 2,224
documents. The graph loses the title-lookup question on purpose.

**"How do I know the numbers are real?"**
`python verify_claims.py` re-checks all 21 against the live graph, and CI runs it on every push.
Every row the product returns carries a `github.com` URL you can click.

**"What's the weakest part?"**
The UI, and I would say so first. It is 100 lines of HTML. The engineering is where the time went.
