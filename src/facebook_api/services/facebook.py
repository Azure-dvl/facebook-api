import asyncio
import json
import random

from playwright.async_api import BrowserContext, Page

from facebook_api.utils.browser import browser_manager


async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _safe_close_context(context: BrowserContext) -> None:
    try:
        await context.close()
    except Exception:
        pass


async def _goto(page: Page, url: str, timeout: int = 30000) -> None:
    attempt = 0
    while True:
        attempt += 1
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            return
        except Exception as e:
            if attempt >= 2:
                raise TimeoutError(f"No se pudo cargar {url}: {e}")
            await random_delay(2, 3)


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
    encrypted_cookies: str, decrypt_fn
) -> tuple[BrowserContext, Page]:
    raw = decrypt_fn(encrypted_cookies)
    cookies = json.loads(raw)
    context = await browser_manager.create_context(cookies=cookies)
    page = await context.new_page()
    return context, page


async def _wait_for_first(
    page: Page, selectors: list[str], timeout_ms: int = 15000
) -> object | None:
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout_ms)
            return page.locator(sel).first
        except Exception:
            continue
    return None


async def list_groups(encrypted_cookies: str, decrypt_fn) -> list[dict]:
    context, page = await _get_authenticated_context(encrypted_cookies, decrypt_fn)
    try:
        await _goto(page, "https://www.facebook.com/groups/feed")
        await random_delay(2, 4)

        groups = []
        group_links = await page.query_selector_all(
            'a[href*="/groups/"][role="presentation"]'
        )

        seen_ids = set()
        for link in group_links:
            href = await link.get_attribute("href")
            name = await link.inner_text()
            if not href or "/groups/" not in href:
                continue
            parts = href.rstrip("/").split("/")
            try:
                idx = parts.index("groups")
                group_id = parts[idx + 1]
            except (ValueError, IndexError):
                continue
            if group_id in seen_ids or not group_id.isdigit():
                continue
            seen_ids.add(group_id)
            groups.append({"id": group_id, "name": name.strip()})

        if not groups:
            groups = await _scrape_groups_via_search(page)

        return groups
    finally:
        await _safe_close_context(context)


async def _scrape_groups_via_search(page: Page) -> list[dict]:
    await _goto(page, "https://www.facebook.com/groups")
    await random_delay(2, 3)

    groups = []
    cards = await page.query_selector_all('[class*="x1i10hfl"]')
    seen_ids = set()

    for card in cards:
        try:
            link = await card.query_selector('a[href*="/groups/"]')
            if not link:
                continue
            href = await link.get_attribute("href")
            name = await card.inner_text()
            if not href:
                continue
            parts = href.rstrip("/").split("/")
            try:
                idx = parts.index("groups")
                group_id = parts[idx + 1]
            except (ValueError, IndexError):
                continue
            if group_id in seen_ids or not group_id.isdigit():
                continue
            seen_ids.add(group_id)
            groups.append({"id": group_id, "name": name.strip().split("\n")[0]})
        except Exception:
            continue

    return groups


async def post_to_group(
    encrypted_cookies: str,
    decrypt_fn,
    group_id: str,
    text: str,
    image_urls: list[str] | None = None,
) -> dict:
    context, page = await _get_authenticated_context(encrypted_cookies, decrypt_fn)
    try:
        page.set_default_timeout(30000)
        await _goto(page, f"https://www.facebook.com/groups/{group_id}")
        await random_delay(2, 4)

        composer = await _wait_for_first(
            page,
            [
                '[role="button"]:has-text("Escribir algo...")',
                '[role="button"]:has-text("Write something")',
                '[aria-label*="publicar"], [aria-label*="write"]',
            ],
        )
        if composer is None:
            raise Exception("Could not find post composer")

        await composer.click()
        await random_delay(1, 2)

        textbox = await _wait_for_first(
            page,
            ['[role="textbox"][contenteditable="true"]', '[data-lexical-editor="true"]'],
        )
        if textbox is None:
            raise Exception("Could not find text input")

        await textbox.click()
        await random_delay(0.3, 0.5)
        await textbox.fill(text)
        await random_delay(1, 2)

        if image_urls:
            file_input = page.locator('input[type="file"][accept*="image"]')
            if await file_input.count() > 0:
                import httpx
                import tempfile
                import os

                temp_paths = []
                async with httpx.AsyncClient() as client:
                    for url in image_urls:
                        resp = await client.get(url, timeout=30)
                        if resp.status_code == 200:
                            suffix = "." + url.split(".")[-1].split("?")[0]
                            tmp = tempfile.NamedTemporaryFile(
                                delete=False, suffix=suffix
                            )
                            tmp.write(resp.content)
                            tmp.close()
                            temp_paths.append(tmp.name)

                if temp_paths:
                    await file_input.first.set_input_files(temp_paths)
                    await random_delay(2, 4)
                    for p in temp_paths:
                        os.unlink(p)

        post_btn = await _wait_for_first(
            page,
            [
                'div[aria-label="Publicar"], div[aria-label="Post"]',
                'button:has-text("Publicar"), button:has-text("Post")',
            ],
        )
        if post_btn is None:
            raise Exception("Could not find post button")

        await post_btn.click()
        await random_delay(3, 5)

        return {"status": "success", "group_id": group_id}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
    finally:
        await _safe_close_context(context)


async def post_to_profile(
    encrypted_cookies: str,
    decrypt_fn,
    text: str,
    image_urls: list[str] | None = None,
) -> dict:
    context, page = await _get_authenticated_context(encrypted_cookies, decrypt_fn)
    try:
        page.set_default_timeout(30000)
        await _goto(page, "https://www.facebook.com/")
        await random_delay(2, 4)

        composer = await _wait_for_first(
            page,
            [
                '[aria-label*="en que estas pensando"], [aria-label*="on your mind"]',
                '[role="button"]:has-text("¿Qué hay de nuevo")',
                '[role="button"]:has-text("What")',
            ],
        )
        if composer is None:
            raise Exception("Could not find profile post composer")

        await composer.click()
        await random_delay(1, 2)

        textbox = await _wait_for_first(
            page,
            ['[role="textbox"][contenteditable="true"]', '[data-lexical-editor="true"]'],
        )
        if textbox is None:
            raise Exception("Could not find text input")

        await textbox.click()
        await random_delay(0.3, 0.5)
        await textbox.fill(text)
        await random_delay(1, 2)

        if image_urls:
            file_input = page.locator('input[type="file"][accept*="image"]')
            if await file_input.count() > 0:
                import httpx
                import tempfile
                import os

                temp_paths = []
                async with httpx.AsyncClient() as client:
                    for url in image_urls:
                        resp = await client.get(url, timeout=30)
                        if resp.status_code == 200:
                            suffix = "." + url.split(".")[-1].split("?")[0]
                            tmp = tempfile.NamedTemporaryFile(
                                delete=False, suffix=suffix
                            )
                            tmp.write(resp.content)
                            tmp.close()
                            temp_paths.append(tmp.name)

                if temp_paths:
                    await file_input.first.set_input_files(temp_paths)
                    await random_delay(2, 4)
                    for p in temp_paths:
                        os.unlink(p)

        post_btn = await _wait_for_first(
            page,
            [
                'div[aria-label="Publicar"], div[aria-label="Post"]',
                'button:has-text("Publicar"), button:has-text("Post")',
            ],
        )
        if post_btn is None:
            raise Exception("Could not find post button")

        await post_btn.click()
        await random_delay(3, 5)

        return {"status": "success"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
    finally:
        await _safe_close_context(context)
