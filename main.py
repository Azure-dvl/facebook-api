import asyncio
import logging
import sys
import urllib.request

import uvicorn

from facebook_api.config import settings
from facebook_api.database import async_session, init_db
from facebook_api.main import app
from facebook_api.services.auth import get_last_active_session
from facebook_api.utils.state import login_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("facebook-api")


async def wait_for_server_ready(
    server_task: asyncio.Task, host: str, port: int, timeout: float = 60.0
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    url = f"http://{host}:{port}/"
    while loop.time() < deadline:
        if server_task.done():
            exc = server_task.exception()
            if exc:
                raise exc
            raise RuntimeError("El servidor se detuvo antes de arrancar")
        try:
            await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=1)
            )
            return
        except Exception:
            await asyncio.sleep(0.25)
    raise TimeoutError("El servidor no respondio a tiempo")


async def run() -> None:
    print("=" * 60)
    print("   FACEBOOK API - Automatizacion de publicaciones")
    print("=" * 60)
    print(f"   Servidor:        http://{settings.APP_HOST}:{settings.APP_PORT}")
    print(f"   URL publica:      {settings.PUBLIC_BASE_URL}")
    print(f"   Documentacion:    {settings.PUBLIC_BASE_URL}/docs")
    print("=" * 60)

    config = uvicorn.Config(
        app, host=settings.APP_HOST, port=settings.APP_PORT, log_level="info"
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    try:
        await wait_for_server_ready(server_task, "127.0.0.1", settings.APP_PORT)
    except Exception as e:
        logger.error(f"Error al arrancar el servidor: {e}")
        print("\n[ERROR] El servidor no pudo arrancar. Revisa la BD y el entorno.")
        return

    print(f"\n[*] Esperando autenticacion via la extension de navegador...")
    print(f"    1. Instala la extension (carpeta extension/) en Chrome o Edge.")
    print(f"    2. Logueate en https://www.facebook.com con tu cuenta.")
    print(f"    3. Pulsa el icono de la extension y 'Exportar sesion'.\n")
    sys.stdout.flush()

    await init_db()
    async with async_session() as db:
        saved_session = await get_last_active_session(db)

    if saved_session:
        logger.info(
            f"Se encontro una sesion guardada ({saved_session.session_name}). "
            "Cargando sin necesidad de re-autenticar..."
        )
        login_state.mark_logged_in(str(saved_session.id))
    else:
        logger.info("Esperando autenticacion de Facebook (via extension)...")
        session_id = await login_state.wait_for_login()
        logger.info(f"Se ha logueado correctamente. Session ID: {session_id}")

    try:
        await server_task
    except asyncio.CancelledError:
        server.should_exit = True


if __name__ == "__main__":
    asyncio.run(run())