######## Stage 1: install deps (uv) + Playwright Chromium ########
FROM python:3.13-slim-bookworm AS build

# uv 0.12.17: la version con la que esta generado el uv.lock del repo.
# (Si tu red bloquea ghcr.io, sustituye por: RUN pip install --no-cache-dir uv==0.12.17)
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /usr/local/bin/

# El venv vive en /app/.venv en las dos stages (mismo path => symlinks y scripts
# del venv siguen validos al copiarlo) y los navegadores en una ruta fija para
# poder copiarlos al runtime.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Capa de dependencias cacheada: todavia no hace falta el codigo fuente.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Chromium, que usa la API para validar las cookies y publicar. Solo chromium
# (no todos los navegadores); los drivers de Playwright ya vienen en el venv.
RUN playwright install --no-progress chromium

# El proyecto se instala como wheel (uv_build, layout src/) y no editable, asi
# el runtime no necesita el codigo fuente, solo el entrypoint.
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

######## Stage 2: lightweight runtime ########
FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=build /app/.venv ./.venv
COPY --from=build /ms-playwright /ms-playwright

# Las bibliotecas del sistema que Chromium necesita no se heredan de la stage
# anterior (apt se ejecuto ahi), asi que se instalan aqui. Playwright ya pasa
# --no-sandbox y --disable-dev-shm-usage al navegador, por eso root funciona y
# no hace falta agrandar /dev/shm.
RUN playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# El paquete facebook_api ya esta dentro de .venv; solo falta el entrypoint.
# El esquema lo crea la propia API al arrancar (database.init_db -> create_all):
# no hay migraciones Alembic que aplicar (alembic/versions esta vacio).
COPY main.py ./main.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# El puerto lo fija APP_PORT (ver .env.example); 8000 es su valor por defecto.
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
