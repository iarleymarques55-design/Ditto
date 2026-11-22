# API e worker do Ditto. A mesma imagem roda os dois; só o comando muda.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    STORAGE_DIR=/app/storage

WORKDIR /app

# O Chromium só é usado quando o worker roda as tarefas sem a extensão
COPY requirements.txt .
RUN pip install -r requirements.txt \
    && playwright install --with-deps chromium

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Sem root: um site que escapasse do navegador não ganha o container
RUN useradd --create-home --uid 10001 ditto \
    && mkdir -p /app/storage \
    && chown ditto /app/storage
USER ditto

EXPOSE 8000
# O Railway informa a porta em $PORT. As migrações rodam antes de a API aceitar pedidos
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
