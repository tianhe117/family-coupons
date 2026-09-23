# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_FILE=/app/data/data.json
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install --no-cache-dir -r /tmp/requirements.txt
EXPOSE 8000
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8000", "--timeout", "30", "app:create_app()"]
