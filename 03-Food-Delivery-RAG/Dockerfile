# Container for the public demo (Render builds this; any Docker host works).
# Render's free plan has 512 MB RAM and 0.1 CPU, so the embedding model and the vector DB are
# baked into the image at build time: the live app starts in seconds and only embeds questions.
# Only the app's own files are copied in, so a local .env can never end up in the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    HF_HUB_DISABLE_TELEMETRY=1 \
    ANONYMIZED_TELEMETRY=False \
    EMBEDDING_CACHE_DIR=/app/.cache/fastembed

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py ingest.py ./
COPY rag/ rag/
COPY knowledge-base/ knowledge-base/

# Download the model and build the vector DB now, then run as a normal user
RUN python ingest.py \
    && useradd --create-home --uid 1000 app \
    && chown -R app /app
USER app

# Render passes the port in $PORT (10000 by default); app.py then listens on 0.0.0.0:$PORT
ENV PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
