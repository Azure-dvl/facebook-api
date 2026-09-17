import asyncio
import json
import logging
import os
import random
import tempfile
import time
from datetime import datetime, timezone

import httpx
from playwright.async_api import BrowserContext, Page

from facebook_api.utils.browser import browser_manager, random_user_agent
from facebook_api.utils.crypto import decrypt_data, encrypt_data

logger = logging.getLogger("facebook-api")


async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def clean_group_name(raw_name: str) -> str:
    name = raw_name.strip()
    for marker in [
        "\nActivo",
        "Activo por última vez",
        "Activo hace",
        "Activo en los últimos",
        "Activo esta",
        "Activo hoy",
        "Activo ",
    ]:
        idx = name.find(marker)
        if idx > 0:
            name = name[:idx]
            break
    return name.strip()


async def _safe_close_context(context: BrowserContext) -> None:
    try:
        await context.close()
    except Exception:
        pass


async def _goto(page: Page, url: str, timeout: int = 45000) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception:
        pass
    for _ in range(2):
        try:
            await page.reload(wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception:
            await random_delay(2, 4)
    raise TimeoutError(f"No se pudo cargar {url}")


def _cookies_are_session_cookies(cookies: list[dict]) -> bool:
    names = {c.get("name") for c in cookies}
    if "c_user" not in names:
        return False
    if not any(k in names for k in ("xs", "datr")):
        return False
    return True


async def verify_cookies(cookies: list[dict]) -> dict:
    context = await browser_manager.create_context(cookies=cookies)
    try:
        page = context.pages[0]
        try:
            await page.goto(
                "https://www.facebook.com/",
                wait_until="domcontentloaded",
                timeout=20000,
            )
        except Exception:
            return {"valid": False, "reason": "Facebook no respondio; la sesion parece invalida"}
        await random_delay(1, 2)

        fb_user_id = None
        for cookie in cookies:
            if cookie.get("name") == "c_user":
                fb_user_id = cookie["value"]
                break

        if not fb_user_id:
            return {"valid": False, "reason": "Falta la cookie c_user"}

        login_form = page.locator('input[name="email"]')
        login_btn = page.locator('[type="submit"][value*="Iniciar"], [type="submit"][value*="Log"]')
        try:
            is_login_page = await login_form.count() > 0
        except Exception:
            is_login_page = False

        if "checkpoint" in page.url:
            return {"valid": False, "reason": "Facebook pide verificacion adicional (checkpoint)"}
        if is_login_page:
            return {"valid": False, "reason": "La sesion no es valida: Facebook muestra la pagina de login"}

        return {"valid": True, "fb_user_id": fb_user_id}
    except Exception as e:
        return {"valid": False, "reason": str(e)}
    finally:
        await _safe_close_context(context)


async def _get_authenticated_context(
    encrypted_cookies: str,
    decrypt_fn,
    user_agent: str | None = None,
) -> tuple[BrowserContext, Page]:
    raw = decrypt_fn(encrypted_cookies)
    cookies = json.loads(raw)
    context = await browser_manager.create_context(cookies=cookies, user_agent=user_agent)
    page = await context.new_page()
    return context, page


_context_cache: dict[str, tuple[BrowserContext, float]] = {}
_MAX_CONTEXT_IDLE = 900


def _stable_user_agent(session) -> str:
    ua = getattr(session, "user_agent", None) or ""
    if not ua or ua in ("extension", "default"):
        return random_user_agent()
    return ua


async def _evict_old_contexts() -> None:
    now = time.time()
    for sid in list(_context_cache):
        ctx, ts = _context_cache[sid]
        try:
            closed = ctx.is_closed()
        except Exception:
            closed = True
        if closed or now - ts > _MAX_CONTEXT_IDLE:
            await _safe_close_context(ctx)
            _context_cache.pop(sid, None)


async def _acquire_context(session) -> BrowserContext:
    await _evict_old_contexts()
    entry = _context_cache.get(session.id)
    if entry:
        ctx, _ = entry
        try:
            if not ctx.is_closed():
                _context_cache[session.id] = (ctx, time.time())
                return ctx
        except Exception:
            pass
        _context_cache.pop(session.id, None)

    cookies = json.loads(decrypt_data(session.encrypted_cookies))
    ctx = await browser_manager.create_context(
        cookies=cookies, user_agent=_stable_user_agent(session)
    )
    _context_cache[session.id] = (ctx, time.time())
    return ctx


async def _release_failed_context(session) -> None:
    entry = _context_cache.pop(session.id, None)
    if entry:
        await _safe_close_context(entry[0])


async def _wait_for_first(
    page: Page, selectors: list[str], timeout_ms: int = 15000
) -> object | None:
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, state="attached", timeout=timeout_ms)
            locator = page.locator(sel).first
            try:
                await locator.scroll_into_view_if_needed()
            except Exception:
                pass
            return locator
        except Exception:
            continue
    return None


async def _dom_evidence(page: Page) -> str:
    try:
        dialogs = await page.locator('[role="dialog"]').count()
        ce = await page.locator('[contenteditable="true"]').count()
        buttons = await page.locator('[role="button"]').count()
        publics = await page.locator('[aria-label="Publicar"]').count()
        extras = []
        locs = page.locator('[aria-label]')
        total = await locs.count()
        for i in range(min(total, 8)):
            try:
                t = (await locs.nth(i).inner_text() or "").strip().replace("\n", " ")[:40]
                if t:
                    extras.append(t)
            except Exception:
                pass
        return (
            f"url={page.url} dialogs={dialogs} ce={ce} buttons={buttons} "
            f"publicar={publics} aria={extras}"
        )
    except Exception as e:
        return f"evidence-error={e}"


async def _dismiss_account_chooser(page: Page) -> None:
    """Cierra el selector de perfil que Facebook muestra al no reconocer la
    sesion en un contexto nuevo."""

    for _ in range(3):
        try:
            picker = page.locator("[role='dialog']").filter(
                has_text="Usar otro perfil"
            )
            if await picker.count() == 0:
                return
            cont = picker.locator(
                '[aria-label="Continuar"], button:has-text("Continuar")'
            ).first
            if await cont.count() == 0:
                return
            await cont.click(timeout=4000)
            await random_delay(2, 4)
        except Exception:
            return


async def _open_composer_textbox(
    page: Page, composer, attempt: int = 0
) -> object | None:
    if attempt > 2:
        return None
    try:
        await composer.click()
    except Exception:
        pass
    await random_delay(1.5, 2.5)
    textbox = await _wait_for_first(
        page,
        [
            '[role="dialog"] [data-lexical-editor="true"]',
            '[role="dialog"] [contenteditable="true"]',
            '[role="dialog"] [role="textbox"]',
            '[role="dialog"] [contenteditable="true"][aria-label]',
            '[role="dialog"] [contenteditable="true"][aria-placeholder]',
        ],
        timeout_ms=12000,
    )
    if textbox is not None:
        return textbox
    logger.warning(
        "[composer] textbox no hallado intento=%s %s", attempt, await _dom_evidence(page)
    )
    return await _open_composer_textbox(page, composer, attempt + 1)


async def _dialog_editor(
    page: Page, timeout: float = 12.0
) -> object | None:
    """Espera (polling) el editor dentro del dialogo de publicacion."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            dce = page.locator('[role="dialog"] [contenteditable="true"]')
            if await dce.count():
                loc = dce.first
                try:
                    await loc.scroll_into_view_if_needed()
                except Exception:
                    pass
                return loc
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None


async def _click_visible_composer(page: Page, texts: tuple[str, ...]) -> bool:
    """Clic directo (JS) sobre el composer visible de "Escribe algo...", evitando
    la cabecera sticky que intercepta eventos de puntero."""
    try:
        await page.evaluate("window.scrollTo(0,0)")
        await asyncio.sleep(0.5)
        clicked = await page.evaluate(
            """(texts) => {
                const rectOk = (r) => r && r.width > 20 && r.height > 10
                    && r.bottom > 0 && r.top < window.innerHeight;
                const el = Array.from(document.querySelectorAll('[role="button"]')).find(c => {
                    const t = (c.innerText || '').trim();
                    return texts.some(x => t.startsWith(x)) && rectOk(c.getBoundingClientRect());
                });
                if (!el) return false;
                try {
                    el.click();
                } catch (e) {
                    el.dispatchEvent(new MouseEvent('click', {
                        bubbles: true, cancelable: true, view: window,
                    }));
                }
                return true;
            }""",
            list(texts),
        )
        return bool(clicked)
    except Exception:
        return False


async def _reset_extra_dialogs(page: Page) -> None:
    """Cierra diálogos/composers sobrantes (p. ej. de una página anterior en el
    mismo contexto) para no componer ni publicar en el destino equivocado."""
    try:
        for _ in range(2):
            closed = await page.evaluate(
                """() => {
                    const sel = [
                        '[role="dialog"] [aria-label="Cerrar"]',
                        '[role="dialog"] [aria-label="Close"]',
                        '[role="dialog"] [aria-label="Cancelar"]',
                        '[role="dialog"] button[aria-label*="Cerrar"]',
                        '[role="dialog"] button[aria-label*="Close"]',
                    ].join(',');
                    const btn = document.querySelector(sel);
                    if (!btn) return false;
                    btn.click();
                    return true;
                }"""
            )
            await asyncio.sleep(0.6)
            if not closed:
                break
    except Exception:
        pass
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.4)
    except Exception:
        pass


async def _open_group_composer(page: Page) -> object | None:
    """Abre el composer del grupo actual de forma determinista: clic sobre el
    "Escribe algo..." visible y espera el editor del diálogo. Nunca reusa un
    editor preexistente (podría pertenecer a otra página/destino)."""
    texts = ("Escribe algo", "Write something", "Escribir algo", "Escribe un")
    if not await _click_visible_composer(page, texts):
        comp = await _wait_for_first(
            page,
            [
                '[role="button"]:has-text("Escribe algo")',
                '[role="button"]:has-text("Write something")',
                '[aria-label*="Escribir algo"]',
            ],
            timeout_ms=8000,
        )
        if comp is not None:
            try:
                bb = await comp.bounding_box()
                if bb:
                    await page.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
            except Exception:
                pass
    await random_delay(1.5, 2.5)
    return await _dialog_editor(page, timeout=15.0)


async def _persist_session_cookies(
    context: BrowserContext, session, db
) -> None:
    try:
        cookies = await context.cookies()
        if cookies and _cookies_are_session_cookies(cookies):
            session.encrypted_cookies = encrypt_data(json.dumps(cookies))
            session.last_used = datetime.now(timezone.utc)
            await db.commit()
    except Exception:
        pass


async def _attach_images(page: Page, image_urls: list[str] | None) -> list[str]:
    """Adjunta imágenes al composer abierto y espera a que la subida termine.
    Devuelve la lista de URLs que realmente se adjuntaron (vacía si nada)."""
    if not image_urls:
        return []

    attached: list[str] = []
    try:
        dialogs = page.locator('[role="dialog"]')
        file_input = None
        if await dialogs.count():
            dlg_inputs = page.locator('[role="dialog"] input[type="file"]')
            if await dlg_inputs.count():
                file_input = dlg_inputs.first
        if file_input is None:
            page_inputs = page.locator('input[type="file"][accept*="image"]')
            if await page_inputs.count():
                file_input = page_inputs.first
            else:
                try:
                    await page.wait_for_selector('input[type="file"]', timeout=5000)
                except Exception:
                    pass
                page_inputs = page.locator('input[type="file"]')
                if await page_inputs.count():
                    file_input = page_inputs.first
        if file_input is None:
            return []

        temp_paths = []
        async with httpx.AsyncClient() as client:
            for url in image_urls:
                try:
                    resp = await client.get(url, timeout=30)
                    if resp.status_code != 200:
                        continue
                    base = url.split("/")[-1].split("?")[0]
                    ext = os.path.splitext(base)[1] or ".jpg"
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    tmp.write(resp.content)
                    tmp.close()
                    temp_paths.append((tmp.name, url))
                except Exception:
                    continue

        if not temp_paths:
            return []

        await file_input.set_input_files([p for p, _ in temp_paths])
        attached = [u for _, u in temp_paths]

        for _ in range(50):
            try:
                imgs = await page.locator('[role="dialog"] img').count()
                if imgs >= len(temp_paths):
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        await asyncio.sleep(1)
        for p, _ in temp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
    except Exception as e:
        logger.warning("[imagen] fallo adjuntando %s", e)
    return attached


_COMPOSER_DIALOGS = (
    '[role="dialog"][aria-label="Crear publicación"]',
    '[role="dialog"][aria-label="What\'s on your mind"]',
    '[role="dialog"][aria-label="Crear publicación/account"]',
)

_ERR_PATTERNS = (
    "no se pudo",
    "no pudimos",
    "no se puede",
    "hubo un problema",
    "intenta de nuevo",
    "vuelve a intentar",
    "se produjo un error",
    "no está disponible",
    "no se ha completado",
    "couldn't",
    "something went wrong",
    "please try again",
)

_REVIEW_BUTTON_LABELS_RAW = (
    "Enviar para revisión",
    "Submit for review",
    "Solicitar revisión",
    "Enviar",
)
_REVIEW_BUTTON_LABELS = tuple(label.lower() for label in _REVIEW_BUTTON_LABELS_RAW)

_REVIEW_PATTERNS = (
    "revisión",
    "revision",
    "aprobación",
    "aprobacion",
    "aprobado por",
    "aprobada por",
    "será revisada",
    "sera revisada",
    "serán revisadas",
    "seran revisadas",
    "en espera",
    "se envió",
    "se envio",
    "se ha enviado",
    "se enviará",
    "se enviara",
    "por el administrador",
    "por los administradores",
    "administración",
    "pendiente",
    "pending",
    "review",
    "approval",
    "approve",
    "awaiting",
    "submitted",
)


async def _wait_publish_enabled(page: Page, timeout: float = 90.0):
    """Espera a que exista un botón de envío habilitado dentro del composer
    (Publicar / Enviar para revisión; la subida de imágenes debe terminar
    antes de habilitarse). Prioriza los botones de revisión del admin."""
    t0 = time.monotonic()
    candidates: list[str] = []
    for label in _REVIEW_BUTTON_LABELS_RAW:
        candidates.append(f'[role="dialog"] [role="button"][aria-label="{label}"]')
        candidates.append(f'[role="dialog"] [aria-label="{label}"]')
    candidates += [
        '[role="dialog"] [role="button"][aria-label="Publicar"]',
        '[role="dialog"] [aria-label="Publicar"]',
        '[role="dialog"] [role="button"][aria-label="Post"]',
        '[role="dialog"] [role="button"]:has-text("Publicar")',
    ]
    while time.monotonic() - t0 < timeout:
        for sel in candidates:
            try:
                loc = page.locator(sel)
                n = await loc.count()
                for i in range(n):
                    btn = loc.nth(i)
                    aria_disabled = await btn.get_attribute("aria-disabled")
                    try:
                        disabled = await btn.is_disabled()
                    except Exception:
                        disabled = False
                    if aria_disabled != "true" and not disabled:
                        return btn
            except Exception:
                continue
        await asyncio.sleep(0.5)
    return None


async def _toast_text(page: Page) -> str:
    try:
        toasts: list[str] = []
        locs = page.locator('[role="alert"], div[class*="toast"]')
        n = await locs.count()
        for i in range(min(n, 8)):
            try:
                t = (await locs.nth(i).inner_text() or "").strip().replace("\n", " ")
                if t:
                    toasts.append(t[:200])
            except Exception:
                pass
        return " | ".join(toasts)
    except Exception:
        return ""


async def _wait_publish_result(page: Page, timeout: float = 180.0) -> dict:
    """Confirma con certeza el resultado del envío: cierre del composer o toast
    de éxito (publicado) o de revisión del administrador (pendiente de aprobación).
    Devuelve {"ok": bool, "error": str, "pending_approval": bool}."""
    t0 = time.monotonic()
    in_progress = ("publicando", "subiendo", "uploading", "procesando", "processing")
    composer = page.locator(f"{_COMPOSER_DIALOGS[0]}, {_COMPOSER_DIALOGS[1]}")

    def _flag(text: str) -> str | None:
        low = (text or "").lower()
        if any(p in low for p in ("publicado", "se publicó", "se ha publicado", "publicada en")):
            return "success"
        if any(p in low for p in _ERR_PATTERNS):
            return "error"
        if any(p in low for p in _REVIEW_PATTERNS):
            return "pending"
        return None

    while time.monotonic() - t0 < timeout:
        toast = await _toast_text(page)
        if toast:
            flag = _flag(toast)
            if flag:
                if flag == "success":
                    await asyncio.sleep(1.5)
                    return {"ok": True, "error": "", "pending_approval": False}
                if flag == "pending":
                    await asyncio.sleep(1.0)
                    return {"ok": True, "error": "", "pending_approval": True}
                return {"ok": False, "error": f"Facebook: {toast[:200]}", "toast": toast}
        try:
            if await composer.count():
                dlg_text = (await composer.first.inner_text() or "").lower()
                if any(p in dlg_text for p in _ERR_PATTERNS):
                    return {
                        "ok": False,
                        "error": f"Facebook (en diálogo): {dlg_text[:200]}",
                        "toast": dlg_text[:200],
                    }
        except Exception:
            pass
        try:
            if await composer.count() == 0:
                await asyncio.sleep(2)
                toast = await _toast_text(page)
                if toast:
                    flag = _flag(toast)
                    if flag == "error":
                        return {"ok": False, "error": f"Facebook: {toast[:200]}", "toast": toast}
                    if flag == "pending":
                        return {"ok": True, "error": "", "pending_approval": True}
                return {"ok": True, "error": "", "pending_approval": False}
        except Exception:
            pass
        await asyncio.sleep(0.75)
    toast = await _toast_text(page)
    low = toast.lower()
    if toast and any(p in low for p in in_progress):
        return {"ok": False, "error": "La publicación quedó en proceso; no se confirmó el envío. Revisa Facebook.", "toast": toast[:200]}
    if toast:
        return {"ok": False, "error": f"La publicación no se completó. Facebook: {toast[:200]}", "toast": toast}
    return {"ok": False, "error": "La publicación no se completó (el diálogo del composer siguió abierto)"}


async def _confirm_publish(page: Page) -> dict:
    btn = await _wait_publish_enabled(page)
    if btn is None:
        raise Exception("El botón Publicar no está disponible (subida pendiente o error del composer)")
    label = ""
    try:
        label = ((await btn.inner_text()) or "").strip().lower()
    except Exception:
        pass
    if not label:
        try:
            label = ((await btn.get_attribute("aria-label")) or "").strip().lower()
        except Exception:
            pass
    button_is_review = any(m in label for m in _REVIEW_BUTTON_LABELS)
    try:
        await btn.evaluate(
            """(el) => {
                // Un único disparo programático: evita dobles envios por
                // activaciones multiples del onClick de Facebook.
                el.click();
            }"""
        )
    except Exception:
        try:
            await btn.click(force=True)
        except Exception:
            pass
    result = await _wait_publish_result(page)
    result["pending_approval"] = button_is_review or result.get("pending_approval", False)
    if not result["ok"]:
        raise Exception(result["error"])
    return result


_MAX_GROUPS = 2000
_SCROLL_STALL_LIMIT = 4


def _group_id_from_href(href: str) -> str | None:
    try:
        parts = href.rstrip("/").split("/")
        idx = parts.index("groups")
        candidate = parts[idx + 1].split("?")[0]
        return candidate if candidate.isdigit() else None
    except (ValueError, IndexError):
        return None


async def _collect_group_links(page: Page, seen: dict[str, str]) -> None:
    try:
        links = await page.query_selector_all(
            'a[href*="/groups/"][target="_self"], a[href*="/groups/"]'
        )
    except Exception:
        return
    for link in links:
        try:
            href = await link.get_attribute("href")
            if not href or "/groups/" not in href:
                continue
            gid = _group_id_from_href(href)
            if not gid or gid in seen:
                continue
            name = await link.inner_text()
            seen[gid] = clean_group_name(name) or f"Grupo {gid}"
        except Exception:
            continue


async def _scroll_to_bottom(page: Page) -> None:
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    await random_delay(1.2, 1.8)
    try:
        await page.keyboard.press("End")
    except Exception:
        pass
    await asyncio.sleep(0.5)


async def _scroll_all_groups(page: Page, max_scrolls: int = 90) -> dict[str, str]:
    """Recorre la lista de grupos haciendo scroll hasta que dejen de aparecer
    ids nuevos (o se alcance el tope)."""
    seen: dict[str, str] = {}
    stall = 0
    for _ in range(max_scrolls):
        before = len(seen)
        await _collect_group_links(page, seen)
        if len(seen) >= _MAX_GROUPS:
            break
        if len(seen) == before:
            stall += 1
            if stall >= _SCROLL_STALL_LIMIT:
                break
        else:
            stall = 0
        await _scroll_to_bottom(page)
    return seen


async def list_groups(encrypted_cookies: str, decrypt_fn) -> list[dict]:
    context, page = await _get_authenticated_context(encrypted_cookies, decrypt_fn)
    try:
        seen: dict[str, str] = {}
        for url in (
            "https://www.facebook.com/groups/joins/",
            "https://www.facebook.com/groups/?category=membership",
            "https://www.facebook.com/groups/feed",
        ):
            try:
                await _goto(page, url)
                await random_delay(2, 4)
                await _dismiss_account_chooser(page)
                await random_delay(1, 2)
                found = await _scroll_all_groups(page)
                seen = {**found, **seen}  # la primera página tiene prioridad
                if len(seen) >= _MAX_GROUPS:
                    break
            except Exception:
                continue

        if not seen:
            found = await _scrape_groups_via_search(page)
            seen = {**found, **seen}

        return [{"id": gid, "name": name} for gid, name in seen.items()]
    finally:
        await _safe_close_context(context)


async def _scrape_groups_via_search(page: Page) -> dict[str, str]:
    try:
        await _goto(page, "https://www.facebook.com/groups")
    except Exception:
        return {}
    await random_delay(2, 3)

    seen: dict[str, str] = {}
    stall = 0
    for _ in range(40):
        before = len(seen)
        try:
            cards = await page.query_selector_all('[class*="x1i10hfl"]')
            for card in cards:
                try:
                    link = await card.query_selector('a[href*="/groups/"]')
                    if not link:
                        continue
                    href = await link.get_attribute("href")
                    if not href:
                        continue
                    gid = _group_id_from_href(href)
                    if not gid or gid in seen:
                        continue
                    name = await card.inner_text()
                    seen[gid] = clean_group_name(name) or f"Grupo {gid}"
                except Exception:
                    continue
        except Exception:
            pass
        if len(seen) >= _MAX_GROUPS:
            break
        if len(seen) == before:
            stall += 1
            if stall >= _SCROLL_STALL_LIMIT:
                break
        else:
            stall = 0
        await _scroll_to_bottom(page)
    return seen


async def post_to_group(
    session,
    db,
    group_id: str,
    text: str,
    image_urls: list[str] | None = None,
) -> dict:
    context = await _acquire_context(session)
    page = await context.new_page()
    try:
        page.set_default_timeout(30000)
        await _goto(page, f"https://www.facebook.com/groups/{group_id}")
        await random_delay(2, 4)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await _dismiss_account_chooser(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.set_default_timeout(15000)

        await _reset_extra_dialogs(page)
        opened = await _open_group_composer(page)
        if not opened:
            logger.warning("[grupo] composer no hallado %s", await _dom_evidence(page))
            raise Exception("Could not find post composer")

        textbox = await _dialog_editor(page, timeout=4.0)
        if textbox is None:
            raise Exception("Could not find text input")

        try:
            await textbox.click(force=True)
        except Exception:
            pass
        await random_delay(0.3, 0.5)
        await textbox.fill(text)
        await random_delay(1, 2)

        if image_urls:
            await _attach_images(page, image_urls)

        result = await _confirm_publish(page)

        await _persist_session_cookies(context, session, db)
        if result.get("pending_approval"):
            logger.info("[grupo] enviado para revisión del admin group=%s", group_id)
            return {
                "status": "pending_approval",
                "group_id": group_id,
                "group_requires_approval": True,
                "error": "Publicación enviada; queda pendiente la aprobación del administrador del grupo.",
            }
        logger.info("[grupo] publicado group=%s text=%r", group_id, text[:40])
        return {"status": "success", "group_id": group_id}
    except Exception as e:
        await _release_failed_context(session)
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def post_to_profile(
    session,
    db,
    text: str,
    image_urls: list[str] | None = None,
) -> dict:
    context = await _acquire_context(session)
    page = await context.new_page()
    try:
        page.set_default_timeout(30000)
        await _goto(page, "https://www.facebook.com/")
        await random_delay(2, 4)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await _dismiss_account_chooser(page)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.set_default_timeout(15000)

        await _reset_extra_dialogs(page)
        composer = await _wait_for_first(
            page,
            [
                '[role="button"]:has-text("Qué estás pensando")',
                '[role="button"]:has-text("What\'s on your mind")',
                '[role="button"]:has-text("What")',
                '[aria-label*="on your mind"]',
                '[contenteditable="true"][aria-label*="on your mind"]',
            ],
            timeout_ms=15000,
        )
        if composer is None:
            logger.warning("[perfil] composer no hallado %s", await _dom_evidence(page))
            raise Exception("Could not find profile post composer")

        textbox = await _open_composer_textbox(page, composer)
        if textbox is None:
            raise Exception("Could not find text input")

        try:
            await textbox.click(force=True)
        except Exception:
            pass
        await random_delay(0.3, 0.5)
        await textbox.fill(text)
        await random_delay(1, 2)

        if image_urls:
            await _attach_images(page, image_urls)

        await _confirm_publish(page)

        await _persist_session_cookies(context, session, db)
        logger.info("[perfil] publicado text=%r", text[:40])
        return {"status": "success"}
    except Exception as e:
        await _release_failed_context(session)
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            await page.close()
        except Exception:
            pass
