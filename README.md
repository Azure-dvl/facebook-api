# Facebook API

API en Python (FastAPI + SQLAlchemy async + Playwright) para automatizar la
publicacion en Facebook **sin usar la API oficial de Facebook** (que prohibe
este tipo de automatizacion y esta reservada para apps aprobadas).

**Alcance:** autenticacion (via extension de navegador), listar grupos y
publicar texto + imagenes en perfil/grupos. La programacion/agendado de
publicaciones se maneja en un programa externo.

## Flujo de autenticacion

El login NUNCA se automatiza (Facebook lo bloquea). El usuario se loguea en su
propio navegador con su cuenta real, y la extension exporta las cookies de
sesion a la API:

1. Arranca la API: `uv run python main.py`. Imprime
   "Esperando autenticacion via la extension de navegador...".
2. Instala la extension en Chrome/Edge desde `extension/` (ver su README).
3. Haz login normal en `https://www.facebook.com`.
4. Pulsa el icono de la extension -> "Exportar sesion".
5. La extension envia las cookies (incluidas las `httpOnly`) a
   `POST /auth/import-cookies`. La API las valida contra Facebook, las cifra
   (Fernet) y las guarda en PostgreSQL.
6. El servidor imprime `Se ha logueado correctamente. Session ID: ...`.

Las cookies de sesion duran aprox. 90 dias; luego se repite la exportacion.

Al reiniciar la API (`uv run python main.py`), esta carga automaticamente la
ultima sesion activa guardada en PostgreSQL; solo hay que re-autenticar si no
hay ninguna sesion guardada.

## Requisitos

- Python 3.13 (via `uv`)
- PostgreSQL
- Chromium (solo se usa para la validacion de cookies y la publicacion):
  `uv run playwright install chromium`

## Instalacion

```bash
uv sync
cp .env.example .env          # editar con tus datos de BD y ENCRYPTION_KEY
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
uv run playwright install chromium
```

Crear la BD y aplicar migraciones:

```bash
createdb facebook_api   # o la que pongas en DB_NAME
uv run alembic upgrade head
```

## Uso

```bash
uv run python main.py             # arranca el servidor y espera la autenticacion
```

Autenticate con la extension (seccion anterior). Luego:

```bash
uv run python src/test/test.py    # publica "Prueba" en el perfil
```

### Endpoints

- `POST /auth/import-cookies` — recibe la sesion exportada (usado por la extension).
- `GET  /auth/sessions` — lista sesiones activas.
- `DELETE /auth/sessions/{id}` — elimina una sesion.
- `GET  /groups/list?session_id={id}` — lista los grupos de la cuenta.
- `POST /posts/create` — publica (perfil o grupo) con las cookies de una sesion.

  Body de `POST /posts/create`:
  ```json
  {
    "session_id": "<id de sesion>",
    "target": "profile",              // o "group"
    "target_id": "<group_id>",        // solo si target=group
    "text": "Hola mundo",
    "image_urls": ["https://.../img.jpg"]
  }
  ```
- `GET  /posts/history?session_id={id}` — historial de publicaciones.

Documentacion interactiva en `http://localhost:8000/docs`.

## Estructura

```
main.py                    Entry point: servidor + espera de autenticacion
src/facebook_api/
  config.py                Settings (.env)
  database.py              SQLAlchemy async + asyncio (PostgreSQL)
  models/                  FacebookSession, PostLog
  schemas/                 Pydantic
  routers/                 auth, groups, posts
  services/
    auth.py                import_cookies() + get_last_active_session()
    facebook.py            Playwright: verify_cookies, list_groups, post_*
  utils/
    browser.py             BrowserManager (lazy, tolerante a crashes)
    crypto.py              Fernet (cifra cookies)
    state.py               LoginState (asyncio.Event)
extension/                 Extension Chrome/Edge que exporta la sesion
src/test/
  test.py                  Publica "Prueba" en el perfil
```

## Nota legal

La automatizacion de publicaciones en Facebook puede violar sus
Terminos de Servicio. Usa este proyecto bajo tu propia responsabilidad y con
cuentas autorizadas.