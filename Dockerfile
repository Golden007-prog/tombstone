# One image: FalkorDB + the app, seeded from the committed snapshot on boot.
#
# Built this way on purpose. The deploy target is a free tier with no persistent disk, and
# FalkorDB Cloud's free tier stops after a day idle and is deleted after seven. Carrying the data
# in the image and rebuilding the graph at startup (~1.1s) means a judge's link works whenever they
# click it, with no external database to go stale and nothing to restore.
FROM falkordb/falkordb:v4.22.1

# Hugging Face Spaces runs containers as UID 1000 with no write access outside a few paths, so
# every cache lives under /app/.cache (owned by that UID) rather than $HOME or /tmp, which the
# platform may mount differently. Verified by running this image with `--user 1000:1000`.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379 \
    PORT=8099 \
    HOME=/app \
    HF_HOME=/app/.cache/hf \
    XDG_CACHE_HOME=/app/.cache \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY web/ ./web/
COPY data/ ./data/

# Warm the embedding model into the image. Downloading BGE-small on first request would make a
# judge's opening question take ~12s, and on a sleeping free tier it would look broken.
RUN mkdir -p /app/.cache \
 && python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')" \
 && chmod -R 777 /app/.cache

ENV PYTHONPATH=/app/src
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# FalkorDB's data dir must be writable by the runtime UID even though the entrypoint disables
# both RDB and AOF -- redis still opens it at startup.
RUN mkdir -p /var/lib/falkordb/data && chmod -R 777 /var/lib/falkordb/data /app

EXPOSE 8099
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT}/api/health" | grep -q '"falkordb":"up"' || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
