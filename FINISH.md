# Finishing this — four steps, about two hours

Everything buildable is done and verified. What remains needs your accounts and your voice.

**Steps 1 and 2 do not block each other — start the deploy, then record while it builds.** This
file used to say the deploy unblocked the video, which was simply wrong: every beat in
`docs/DEMO-SCRIPT.md` is recorded against your local `./run.sh`, and the 2:31 beat *stops the
FalkorDB container*, which is not a thing you can do to a Space. The video needs nothing from the
deploy. Both are needed for step 4.

---

## 1. Deploy (~20 min, mostly waiting on the build)

> **Hugging Face refused this, and the refusal is measured rather than predicted.** Run on
> 17 Oct, `./deploy_hf.sh` reached `POST /api/repos/create` and got **HTTP 402 Payment
> Required**: *"Static Spaces are free for everyone, but hosting Gradio and Docker Spaces on
> free cpu-basic requires a PRO subscription."* The script failed fast and loudly at exactly the
> step it was written to fail at, before staging or uploading anything.
>
> **I had predicted the opposite, and was wrong.** This block used to say free accounts were
> creating Docker Spaces that morning, because of the sixty most recently created Spaces on
> 16 Oct, three were `sdk: docker` and all three owners returned `isPro: false` from HF's public
> user endpoint. That evidence was real and the inference from it was not: `isPro` on a profile
> is not the same as the entitlement checked at repository creation, and reading a listing is not
> the same as attempting the thing. The only test that settled it was running it.
>
> **So pick one of these — all three are already configured and documented in `DEPLOY.md`:**
> - **Render free** (`deploy/render.yaml`): costs nothing, and the honest caveats are measured.
>   This is the one that is live, and on **17 Oct it was killed for exceeding 512 MB while
>   serving** — four concurrent free-text asks did it, each concurrent embed taking its own
>   ~119 MiB ONNX arena. Fixed and re-measured at the hosted size on the host's own architecture:
>   **the live instance reports 91.6 MiB idle and 263.7 MiB after sixteen concurrent asks, all
>   sixteen answered**, where the same flood before the
>   fix was OOM-killed on the first round. It still spins down after 15 minutes, so a judge's
>   first click waits ~1 minute.
> - **HF PRO**, $9/month, which is the only way to get the 16 GB CPU Basic box this image was
>   sized for. Your call and your money; I am not making that decision for you.
> - **No deployment.** Rule 10 is satisfied without one — complete local setup plus the committed
>   walkthrough — so this costs the bonus the FAQ calls "preferred", not the submission.
>
> Do not spend the last hours fighting it; spend them on the video.

```bash
export HF_TOKEN=hf_xxxxxxxxxxxx      # huggingface.co/settings/tokens -> New token -> WRITE
./deploy_hf.sh
```

The script creates the Space, swaps in the Space README (Spaces reads config from its own
front-matter, not this repo's) and uploads 108 files / 3.3 MB. First build takes a few minutes;
after that it boots in seconds.

**`./deploy_hf.sh` needs the token and nothing else — not Docker.** It stages from
`git archive HEAD` and pushes; the Space builds the image on Hugging Face's side. So you can
deploy from a laptop with Docker shut down, and a Dockerfile problem would surface in the Space's
own build log rather than silently.

**What has and has not been verified, because the honest answer changed today.**
`./scripts_verify_deploy.sh` reproduces the Space locally — same `linux/amd64` platform, same
non-root UID, no volumes — and on `99df19d` it built, booted, answered, drafted a patch, refused
the one it cannot justify, served every static route, peaked at **450 MiB in serial use against
the 512 MiB ceiling** (a figure since re-measured at **288 MiB under eight concurrent asks**,
after the hosted instance was killed for exceeding that ceiling on 17 Oct and the cause turned out
to be the embedder rather than `GRAPH.COPY`), and — with FalkorDB killed inside the container — reported down, returned
`DEGRADED` for a question it had just answered, and kept serving the page.
**That run dates from 16 Oct and is now ~90 commits old** — a date rather than a count, because a count re-rots on every push — and `server.py`, `agent.py` and `tools.py` have all changed
since. Saying "already verified" without that caveat was the stale half of this file.
What runs against the current tree: **190 tests and `./preflight.sh` 24/24 against a live graph**,
and — added since — a CI **`image` job on every push that builds this Dockerfile, boots it as the
Space does, requires the graph to seed to 681 decisions inside the container, answers a real
question, and proves the HTTP trust boundary holds on the built image.** So the thing that used to
be uncovered — does the container a judge gets actually build and work — is now checked by CI
without anyone running Docker locally.
What is still only in `./scripts_verify_deploy.sh`: the 512 MiB serial ceiling, the six-way
concurrency burst, and killing FalkorDB inside the container. Re-run it before deploying if you
want those too — Docker, a few minutes, no token — or skip it, because the Space's own build log
and the `image` job now cover the part that would actually stop a judge.

On concurrency, one correction from today: six concurrent `GRAPH.COPY` requests always come back,
every one either answering or degrading honestly, with no hard failure and no hang. The **split**
is not a property and should not be quoted as one — which fork loses the race varies. It was 5
answered / 1 degraded in that container run and 4 / 2 against a local instance on 16 Oct.

**That SHA is deliberately specific, and here is what has changed since it.** Exactly one file
on the deploy surface: `deploy/README-hf-space.md`, which gained a `short_description` line and
had its memory figure corrected. Nothing in the `Dockerfile`, the entrypoint, `deploy_hf.sh` or
`scripts_verify_deploy.sh` — so the image that was verified is behaviourally the same image, and
the Space README is not in it at all; the deploy swaps it in as the Space's own README. Its
front-matter is validated on every push now. If you want the full end-to-end run again anyway
it is one command and needs Docker, which is currently stopped on this machine.

**Then verify it the way a judge will** — different network, private window, no sign-in. The
host below is Render's, because Render is the deployment that is live. This line named
`aviralgarg05-tombstone.hf.space` until the 17 Oct audit — written on 15 Oct, before the 402 — and
that host returns **404**, in the same file that records the 402:

```bash
curl -s https://tombstone-vvn9.onrender.com/api/health | python3 -m json.tool
```

Expect `"falkordb": "up"` and 681 decisions; the first call waits ~1 minute if the instance has
spun down. Then click the chips in the UI.

`deploy_hf.sh` sets the repo's homepage to the live app itself on its way out, so there is
nothing to run here — and do **not** set it by hand to the `huggingface.co/spaces/...` page
instead, which is what this file used to tell you: that replaces a link to the running demo with
a link to its project page. If the script could not reach `gh` it prints the exact command to run.

One thing it does not do: the README's 60-second block has a **Live demo** line reading _"not
deployed yet"_. Replace that with the URL — it is the first thing on the page a judge reads.

## Optional, if you have ten spare minutes with Docker up

Nothing is broken. The committed artefacts are certified against the code they depict — I staled
them for about an hour with a comment and then un-staled them by moving the comment out of a
fingerprinted file, which is written up in `docs/GROUND-TRUTH.md`.

Two things would still be better, and both need the app serving, so they share one window:

```bash
./run.sh                               # one shell
python scripts_gen_readme_shots.py     # another — regenerate with phone-legible type
python scripts_gen_depth_gif.py
python scripts_build_walkthrough.py
./preflight.sh                         # all 23, including freshness and the live path.svg check
```

The figures are desktop captures and illegible on a phone (measured; see **Honest limits** in the
README), and `scripts_check_shots_fresh.py` runs only in `./preflight.sh` — not CI, not the push
gate — which is why an hour passed before I noticed my own mistake. CI already serves the app for
the UI check, so that check belongs there too, and once the figures are regenerated it can go in.

Skip all of it if you would rather spend the time on the video. Rule 10 asks that the video exists
and shows the working product; it does, and the figures are disclosed rather than hidden.

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

Upload **Unlisted**, not Private. That is the one that matters, and it is the one I had the
reason wrong for: this file used to say the "Made for Kids" setting is "what blocks judges from
viewing", which YouTube's own documentation does not support — the list of what that setting
restricts is autoplay, cards, comments, playlists, the miniplayer and notifications, and viewing
by link is not on it. What actually locks a judge out is **Private**, which is viewable only by
email addresses you invite one at a time. **Unlisted** is viewable by anyone with the link and
YouTube says explicitly that they do not need a Google account.

Still set **Not for Kids**, because a technical demo is not children's content and declaring it
otherwise is a false declaration — just not for the reason this file gave. Then open the link in
a private window and confirm it plays with no sign-in, which is the check that catches a wrong
visibility setting whatever the cause.

## 3. Publish the blog post (~45 min, most of it reading)

`docs/BLOG-POST.md` is finished, ~6,050 words — long enough that the read-through is most
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
of 134 Track 3 entries alone, makes the blog post the cheapest additional shot at something.

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
