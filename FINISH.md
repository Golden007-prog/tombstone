# Finishing this — four steps, about two hours

Everything buildable is done and verified. What remains needs your accounts and your voice.

**Steps 1 and 2 do not block each other — start the deploy, then record while it builds.** This
file used to say the deploy unblocked the video, which was simply wrong: every beat in
`docs/DEMO-SCRIPT.md` is recorded against your local `./run.sh`, and the 2:31 beat *stops the
FalkorDB container*, which is not a thing you can do to a Space. The video needs nothing from the
deploy. Both are needed for step 4.

---

## 1. Deploy (~20 min, mostly waiting on the build)

```bash
export HF_TOKEN=hf_xxxxxxxxxxxx      # huggingface.co/settings/tokens -> New token -> WRITE
./deploy_hf.sh
```

The script creates the Space, swaps in the Space README (Spaces reads config from its own
front-matter, not this repo's) and uploads 96 files / 3.2 MB. First build takes a few minutes;
after that it boots in seconds.

**This path has already been verified on the committed tree**, so the token is the only thing
missing. `./scripts_verify_deploy.sh` reproduces the Space locally — same `linux/amd64` platform,
same non-root UID, no volumes — and on `99df19d` it built, booted, answered, drafted a patch,
refused the one it cannot justify, served every static route, peaked at **450 MiB in serial use
against the 512 MiB ceiling**, survived six concurrent `GRAPH.COPY` requests (five answered, one
degraded honestly, no hard failures), and — with FalkorDB killed inside the container — reported
down, returned `DEGRADED` for a question it had just answered, and kept serving the page. Re-run
it yourself if you change anything before deploying; it needs no token.

**Then verify it the way a judge will** — different network, private window, no sign-in:

```bash
curl -s https://aviralgarg05-tombstone.hf.space/api/health | python3 -m json.tool
```

Expect `"falkordb": "up"` and 681 decisions. Then click the chips in the UI.

`deploy_hf.sh` sets the repo's homepage to the live app itself on its way out, so there is
nothing to run here — and do **not** set it by hand to the `huggingface.co/spaces/...` page
instead, which is what this file used to tell you: that replaces a link to the running demo with
a link to its project page. If the script could not reach `gh` it prints the exact command to run.

One thing it does not do: the README's 60-second block has a **Live demo** line reading _"not
deployed yet"_. Replace that with the URL — it is the first thing on the page a judge reads.

## 2. Record the video (~45 min including retakes)

`docs/DEMO-SCRIPT.md` is written and timed to 3:00, beat by beat, staged on the apiserver
example (falls back to **one** approver — the sharpest row in the data).

**Read `docs/DEMO-NARRATION.md` while you record**, not the script. Same words, nothing else —
cue times and one sentence per line, so you are not skipping over stage directions with a clock
running. It is generated from the script, and the push gate fails if the two ever disagree.

Three things that save a bad night:
- **Record the voiceover separately** from the screen capture. Narrating live while clicking is
  the single biggest cause of ten retakes.
- **Pre-click every chip, then run `./run.sh --forget` before you hit record.** Pre-clicking warms
  the caches, but answering also *records* the answer, so without the clear every chip on camera
  reads `ANSWERED_FROM_MEMORY` with a timestamp from before the take — and the 2:17 beat ends up
  citing answers the viewer never saw you ask. Do not clear it again mid-take: 2:17 has nothing to
  recall unless 0:32 ran earlier in the same recording.
- **Record it twice.** The second take is always better and costs ten minutes.

You do **not** need to fix ffmpeg first. It is broken on this machine and nothing here needs it:
the voiceover goes over the capture in iMovie, and the committed artefacts that do call ffmpeg
fall back to a container.

Upload unlisted to YouTube, and set **"Not for Kids"** — that setting is what blocks judges from
viewing. Then open the link in a private window and confirm it plays.

## 3. Publish the blog post (~45 min, most of it reading)

`docs/BLOG-POST.md` is finished, ~4,800 words — long enough that the read-through is most
of the 45 minutes, and worth doing, because it goes out under your name to people who
cannot run anything. Its factual claims are re-checked against the live graph by
`verify_blog.py`, which runs in `./preflight.sh`. Publish to **dev.to**, tagged `falkordb` and
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

**Nothing is required of you after you submit.** Checked on 16 Oct: the schedule page publishes a
registration window, a start and the deadline, and no judging session, no live demo slot, no
presentation and no office hours; it does not announce a results date either. So the deadline is
the last thing in your calendar for this, and there is no reason to stay up past it.

For what it is worth on the way in: Track 3's prize is an M6 Mac Mini, the best-blog-post side
prize is one winner, and the top 50 submissions each get a t-shirt per member — which, in a field
of 85 Track 3 entries alone, makes the blog post the cheapest additional shot at something.

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
Measured, not argued: `eval_graph_vs_text.py`, graph 24/25 versus TF-IDF 9/25 and dense
retrieval 10/25 over the same 2,224
documents. The graph loses the title-lookup question on purpose, and on the control category —
lookups whose answer sits in one document — the text index ties it 9 to 9. Volunteer that tie: it
is what makes the other fifteen mean anything.

**"How do I know the numbers are real?"**
`python verify_claims.py` re-checks all 36 against the live graph, and CI runs it on every push.
Every row the product returns carries a `github.com` URL you can click.

**"What's the weakest part?"**
The UI, and I would say so first. It is 100 lines of HTML. The engineering is where the time went.
