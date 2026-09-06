# Extension - Exportador de sesion de Facebook

Esta extension de Chrome/Edge exporta las cookies de tu sesion de Facebook a la
API para que la automatizacion pueda publicar usando tu cuenta real (sin que la
API tenga que hacer login automatizado, que Facebook bloquea).

## Como se autentica (flujo)

1. La API esta corriendo (`uv run python main.py`).
2. Abres `https://www.facebook.com` en tu navegador y haces login normal
   (captcha/2FA fluyen naturalmente porque es tu sesion real).
3. Pulsas el icono de la extension -> "Exportar sesion".
4. La extension lee las cookies de `.facebook.com` (incluidas las `httpOnly`,
   que Javascript normal no puede leer) y las envia a `POST /auth/import-cookies`.
5. La API valida que la sesion sea real (abre facebook.com con esas cookies),
   las cifra y las guarda en la base de datos.
6. El servidor imprime `Se ha logueado correctamente`.

A partir de ahi puedes usar `POST /posts/create` para publicar en tu perfil o
en grupos con esa sesion.

## Instalacion (modo desarrollador)

1. Abre `chrome://extensions` (o `edge://extensions`).
2. Activa "Modo de desarrollador" (esquina superior derecha).
3. Pulsa "Cargar descomprimida" y selecciona esta carpeta (`extension/`).
4. La extension aparece en la barra; fijala para que sea facil pulsarla.

## Uso

1. Logueate en facebook.com en la misma pestana/ventana del navegador.
2. Pulsa el icono de la extension.
3. Verifica que la "URL de la API" sea correcta (default `http://localhost:8000`).
   Si la API esta en otro host, cambiala y se guardara.
4. Pulsa "Exportar sesion".
5. En la consola donde corre la API deberia aparecer
   `Se ha logueado correctamente. Session ID: ...`.

## Notas

- Las cookies de sesion de Facebook duran aprox. 90 dias. Cuando caduquen,
  vuelve a hacer login en facebook.com y repite la exportacion.
- Si Facebook detecta movimiento sospechoso al usar la cuenta desde el servidor
  (IP de datacenter, etc.), es posible que pidas verificacion. Eso es normal y
  se resuelve haciendo login normal en tu navegador.
- La extension pide permiso para leer cookies de todas las paginas para poder
  exportar la sesion de Facebook y poder enviarla a la URL de la API que tu
  configures (puede ser localhost o un servidor remoto). Solo lee las cookies
  de `.facebook.com` y solo envia datos a la URL que tu pongas en el popup.

## Estructura

```
extension/
  manifest.json   Permisos MV3 (cookies, storage)
  background.js   Service worker: lee cookies y hace POST a la API
  popup.html/js   UI de la extension
  icons/          Iconos
```