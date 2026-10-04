FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FIN_RISK_AUDIT_DATA_DIR=/app/data \
    FIN_RISK_AUDIT_LOG_DIR=/app/data/logs \
    AI_WORKSPACE_ROOT=/app/workspace

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY agent ./agent
COPY scripts/sync_skills.py ./scripts/sync_skills.py

EXPOSE 2024
CMD ["sh", "-c", "python scripts/sync_skills.py && uvicorn agent.app:app --host 0.0.0.0 --port 2024"]
