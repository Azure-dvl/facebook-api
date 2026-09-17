# HOSTING — facebook-api (Render, SOLO TESTING)

Este repositorio se despliega en **Render** como `docker runtime` (Chromium va
dentro del contenedor). README de despliegue completo en
[`/home/azure/Projects/HOSTING.md`](../HOSTING.md).

## 1. Variables de entorno — llenar manualmente en Render

> `render.yaml` ya las declara con `sync: false`; léelas y en el panel de Render
> (service → Environment) pon estos valores:

| Variable                | Valor que llenas                                                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `DB_HOST`               | Host del Postgres **de facebook-api** (ej: `dpg-xxx-a.onrender.com`)                                                                        |
| `DB_PORT`               | `5432`                                                                                                                                      |
| `DB_USER`               | Usuario del Postgres                                                                                                                        |
| `DB_PASSWORD`           | Password del Postgres                                                                                                                       |
| `DB_NAME`               | `facebook_api` (la base que crees para esta API)                                                                                            |
| `ENCRYPTION_KEY`        | Fernet: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`                                          |
| `APP_PUBLIC_URL`        | `https://<tu-facebook-api>.onrender.com` (la URL pública **de esta API**)                                                                   |
| `PORT`                  | Lo pone Render solo (`$PORT`) — no llenar                                                                                                  |

Además Render inyecta el host del contenedor automáticamente.

## 2. Despliegue en Render
1. Sube este repo a GitHub (Necesita: `Dockerfile`, `render.yaml`, `src`, `main.py`, `alembic/`, `pyproject.toml`, `uv.lock`).
2. **Render → New → Blueprint** → pega la URL del repo → Render detecta `render.yaml` y crea el servicio + te pide llenar las variables `sync:false` de la tabla de arriba. **Titulo del servicio y nombre del repo deben coincidir** con lo que pongas en `APP_PUBLIC_URL`.
3. DB: crea un **PostgreSQL** en Render (o usa uno existente) con una base llamada `facebook_api`.
4. En el servicio `web` llena las variables de la tabla; en el Postgres llena el host/usuario/password/nombre y copia esos valores en `DB_*`.
5. Espera el deploy (el build instala Chromium + deps, tarda varios minutos). Healthcheck: `GET /health` → `{"status":"ok"}`.

## 3. Riesgos (TESTING)
- IPs de datacenter (Render) son objetivo de Facebook → posibles checkpoints/bloqueos. Para pruebas largas es más fiable correrlo en tu casa.
- Plan free duerme a los 15 min → las sesiones se pierden y las publicaciones programadas se retrasan. Para testing activo usa "Never sleep" o un keepalive.
- Necesita ≥1 GB RAM en Render (Chromium). Usa plan starter o superior.

## Archivos incluidos
- `Dockerfile` (python 3.13-slim + uv + playwright chromium con deps)
- `.dockerignore`
- `.env.example` (comentado con TODOs)
- `render.yaml`
- endpoint `/health` añadido en `main.py`