FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PROOFLINE_ASGI_APP=proofline.main:app \
    PROOFLINE_HOST=0.0.0.0 \
    PROOFLINE_PORT=8000

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY apps/api /app/apps/api
RUN python -m pip install .

RUN addgroup --system proofline \
    && adduser --system --ingroup proofline --home /app proofline \
    && chown -R proofline:proofline /app

USER proofline

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PROOFLINE_PORT', '8000') + os.getenv('PROOFLINE_HEALTH_PATH', '/health'), timeout=3)" || exit 1

CMD ["sh", "-c", "exec uvicorn \"${PROOFLINE_ASGI_APP}\" --host \"${PROOFLINE_HOST}\" --port \"${PROOFLINE_PORT}\""]
