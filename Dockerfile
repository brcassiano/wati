FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

COPY .env.example .env

ENTRYPOINT ["python", "-m", "wati_agent"]
