# One image: FalkorDB + the app, seeded from the committed snapshot on boot.
#
# Built this way on purpose. The deploy target is a free tier with no persistent disk, and
# FalkorDB Cloud's free tier stops after a day idle and is deleted after seven. Carrying the data
# in the image and rebuilding the graph at startup (~1.1s) means a judge's link works whenever they
# click it, with no external database to go stale and nothing to restore.
FROM falkordb/falkordb:v4.22.1

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379 \
    PORT=8099 \
    HF_HOME=/tmp/hf \
    FASTEMBED_CACHE_PATH=/tmp/fastembed

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
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')" \
 && chmod -R 777 /tmp/fastembed /tmp/hf 2>/dev/null || true

ENV PYTHONPATH=/app/src
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8099
HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT}/api/health" | grep -q '"falkordb":"up"' || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
