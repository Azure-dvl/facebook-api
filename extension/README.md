# Extensión - Exportador de sesión de Facebook (Firefox)

Extensión **solo para Firefox** que exporta las cookies de tu sesión de Facebook a
la API para que la automatización pueda publicar usando tu cuenta real (sin que la
API tenga que hacer login automatizado, que Facebook bloquea).

Sustituye a la antigua extensión de Chrome/Edge.

## Cómo se autentica (flujo)

1. La API está corriendo (`uv run python main.py`).
2. Abres `https://www.facebook.com` en tu navegador y haces login normal
   (captcha/2FA fluyen naturalmente porque es tu sesión real).
3. Pulsas el icono de la extensión -> "Exportar sesión".
4. La extensión lee las cookies de `.facebook.com` (incluidas las `httpOnly`,
   que Javascript normal no puede leer) y las envía a `POST /auth/import-cookies`.
5. La API valida que la sesión sea real (abre facebook.com con esas cookies),
   las cifra y las guarda en la base de datos.
6. El servidor imprime `Se ha logueado correctamente`.

A partir de ahí puedes usar `POST /posts/create` para publicar en tu perfil o
en grupos con esa sesión.

## Instalación (modo desarrollador)

1. Abre `about:debugging#/runtime/this-firefox` en Firefox.
2. Pulsa "Cargar extensión temporalmente..." y selecciona el archivo
   `manifest.json` de esta carpeta (`extension/`).
3. La extensión aparece en la barra; fijala para que sea fácil pulsarla.

> Nota: la carga temporal se pierde al reiniciar Firefox. Para tenerla siempre
> disponible, puedes usar Firefox Developer Edition / Nightly y firmarla, o
> instalar vía `about:addons` si está firmada (AMO).

## Uso

1. Logueate en facebook.com en la misma ventana del navegador.
2. Pulsa el icono de la extensión.
3. Verifica que la "URL de la API" sea correcta (default `http://localhost:8000`).
   Si la API está en otro host, cámbiala y se guardará.
   > TODO (HOSTING): para el despliegue de testing en Render, escribe
   > `https://<tu-facebook-api>.onrender.com` en el campo *URL de la API*.
   > Ver [`../HOSTING.md`](../HOSTING.md).
4. Pulsa "Exportar sesión".
5. En la consola donde corre la API debería aparecer
   `Se ha logueado correctamente. Session ID: ...`.

## Diseño

El popup usa el mismo tema oscuro azul que la web de administración (`face-web`):
fondo `#0a0f1f`, acento primario `#3b82f6` y subrayado degradado tipo "huella de gato".

## Notas

- Las cookies de sesión de Facebook duran aprox. 90 días. Cuando caduquen,
  vuelve a hacer login en facebook.com y repite la exportación.
- Si Facebook detecta movimiento sospechoso al usar la cuenta desde el servidor
  (IP de datacenter, etc.), es posible que pida verificación. Es normal y se
  resuelve haciendo login normal en tu navegador.
- La extensión pide permiso para leer cookies de todas las páginas para poder
  exportar la sesión de Facebook y enviarla a la URL de la API que tú
  configures (puede ser localhost o un servidor remoto). Solo lee las cookies
  de `.facebook.com` y solo envía datos a la URL que pongas en el popup.

## Estructura

```
extension/
  manifest.json   Manifiesto MV2 de Firefox
  background.js   Script de fondo: lee cookies y hace POST a la API
  popup.html      UI del popup
  popup.css       Estilos con el tema de la web (oscuro azul)
  popup.js        Lógica del popup
  icons/          Iconos
```