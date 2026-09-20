FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README_繁體中文.md ./
COPY app ./app
COPY config ./config
COPY migrations ./migrations
COPY scripts ./scripts

RUN pip install --no-cache-dir .

EXPOSE 8767

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8767"]
