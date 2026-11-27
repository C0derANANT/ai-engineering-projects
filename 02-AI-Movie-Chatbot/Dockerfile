# Container for the public demo (Render builds this; any Docker host works).
# Only the app's own files are copied in, so a local .env can never end up in the image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GRADIO_ANALYTICS_ENABLED=False

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py ./
COPY movie/ movie/
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app

# Render passes the port in $PORT (10000 by default); app.py then listens on 0.0.0.0:$PORT
ENV PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
