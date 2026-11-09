# Public demo image. Only src/ and requirements.txt are copied, so local
# secrets (.env, credentials.json, token.json) and your database can't be baked in.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEMO_MODE=true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

RUN useradd --create-home appuser && mkdir -p data && chown appuser data
USER appuser

EXPOSE 8080

# Keep this at one worker: demo chat history and usage caps live in process memory.
CMD ["sh", "-c", "exec uvicorn src.web.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
