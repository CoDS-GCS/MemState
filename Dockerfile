FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./

COPY src ./src

RUN pip install --no-cache-dir .

ENV MEMSTATE_KUZU_PATH=/data/memstate.kuzu

EXPOSE 8765

CMD ["python", "-m", "memstate.api.cli"]

