#!/bin/sh
set -e

# El esquema lo crea la propia API al arrancar (database.init_db -> create_all);
# no hay migraciones Alembic que aplicar (alembic/versions esta vacio). Lo que si
# hace falta es que PostgreSQL ya acepte conexiones: init_db() corre en el lifespan
# de FastAPI, asi que si la BD aun no esta lista el arranque falla.
echo "[entrypoint] waiting for PostgreSQL..."
python - <<'PY'
import asyncio
import sys

from sqlalchemy import text

from facebook_api.database import engine

RETRIES = 30
DELAY = 2.0


async def main() -> None:
    for attempt in range(1, RETRIES + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
            return
        except Exception as exc:
            if attempt == RETRIES:
                sys.exit(f"[entrypoint] PostgreSQL no responde: {exc}")
            await asyncio.sleep(DELAY)


asyncio.run(main())
PY

echo "[entrypoint] starting API..."
exec python main.py
