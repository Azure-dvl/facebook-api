import asyncio
import logging
import urllib.request

import uvicorn

from facebook_api.config import settings
from facebook_api.main import app
from facebook_api.utils.qrcode import create_qr_token, generate_qr_ascii
from facebook_api.utils.state import login_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("facebook-api")


async def wait_for_server_ready(host: str, port: int, timeout: float = 30.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    url = f"http://{host}:{port}/"
    while loop.time() < deadline:
        try:
            await loop.run_in_executor(None, lambda: urllib.request.urlopen(url, timeout=1))
            return
        except Exception:
            await asyncio.sleep(0.25)
    raise TimeoutError("Server did not become ready in time")


async def run() -> None:
    print("=" * 60)
    print("   FACEBOOK API - Automatizacion de publicaciones")
    print("=" * 60)
    print(f"   Servidor:      http://{settings.APP_HOST}:{settings.APP_PORT}")
    print(f"   Documentacion: http://localhost:{settings.APP_PORT}/docs")
    print("=" * 60)

    config = uvicorn.Config(
        app, host=settings.APP_HOST, port=settings.APP_PORT, log_level="info"
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    await wait_for_server_ready(settings.APP_HOST, settings.APP_PORT)

    token = create_qr_token()
    login_url = f"http://localhost:{settings.APP_PORT}/auth/login?t={token}"

    print(f"\n[*] Escanea el siguiente QR para iniciar sesion en Facebook:")
    print(f"    O abre manualmente: {login_url}\n")
    print(generate_qr_ascii(login_url))
    print()

    logger.info("Esperando autenticacion de Facebook...")
    session_id = await login_state.wait_for_login()
    logger.info(f"Se ha logueado correctamente. Session ID: {session_id}")

    try:
        await server_task
    except asyncio.CancelledError:
        server.should_exit = True


if __name__ == "__main__":
    asyncio.run(run())
