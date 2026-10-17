"""One embedding at a time, process-wide, because the second concurrent one costs more than the
host has.

This module exists because of a production outage, not a theory. The hosted demo runs on a free
tier with **512 MB and 0.1 CPU**, and on 17 Oct it was killed and restarted by the platform while
serving. Reproduced in the deploy target's own envelope -- the shipped image, non-root, 512 MB,
no swap -- by asking *distinct* questions concurrently through the public ask box:

    concurrent asks   container resident   the python process   outcome
    1                 292 MiB              252 MiB              flat over four rounds
    2                 415 MiB              371 MiB              survives, 97 MiB of headroom
    8                 --                   --                   OOM-killed on the first round

The marginal cost of the *second* concurrent embed is **119 MiB**: ONNX Runtime allocates an
arena per concurrent `Run`, and BGE-small's is far larger than its 67 MB of weights. Three
visitors at once is the edge of a 512 MB box and four is past it, so on a link shared with judges
the crash was not a tail risk -- it was the expected case.

The fix is not a bigger box. It is that embedding is **serialised**: at most one `embed` runs in
this process at any moment, so resident memory is the one-at-a-time figure no matter how many
people are asking. The queueing is real but small -- an embed is tens of milliseconds -- and the
alternative is not "faster", it is a killed container that answers nothing.

`Agent._remember` already did exactly this, for exactly this reason, and said so in a comment
written after chip clicks began embedding on every tool call. What it did not do was cover the
*other* four embed call sites: the two query paths in `Agent`, and both of `LocalRouter`'s. A
lock over one of five call sites bounds nothing. Hence one lock, in one module, imported by both
-- and `RLock`, so a nested acquisition inside a single request is harmless rather than a
deadlock, since one thread holding it is still one embed in flight.

Not a cache: a memo on the question text would change the answer path, and the vectors are
already written into the graph by `Memory`. This bounds concurrency and nothing else.
"""
from __future__ import annotations

import threading

# Re-entrant on purpose. See the module docstring: the invariant is "one thread embedding", and
# a thread that already holds it is not a second embed.
LOCK = threading.RLock()


def embed_rows(embedder, texts) -> list:
    """Embed `texts` with the lock held. `embedder` is the zero-argument callable that returns the
    model, so the model is still loaded lazily and still injectable in tests."""
    with LOCK:
        return list(embedder().embed(list(texts)))


def embed_one(embedder, text: str) -> list[float]:
    """One vector, as a plain list -- the shape every caller here wants to hand to Cypher."""
    return embed_rows(embedder, [text])[0].tolist()
