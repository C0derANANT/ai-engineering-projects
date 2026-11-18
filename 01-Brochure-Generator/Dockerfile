# Container for the public demo (Render builds this; any Docker host works).
# Only the app's own files are copied in, so a local .env can never end up in the image.
FROM python:3.14-slim

# Fonts so Hindi, Chinese, Japanese and Korean text shows up in the PDFs
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY brochure/ brochure/

ENV BROCHURE_HOSTED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_ANALYTICS_ENABLED=False \
    PYTHONUNBUFFERED=1

# Render passes the port to listen on in $PORT (7860 when run elsewhere)
CMD ["sh", "-c", "GRADIO_SERVER_PORT=${PORT:-7860} exec python app.py"]
