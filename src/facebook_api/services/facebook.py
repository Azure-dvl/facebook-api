import asyncio
import json
import random

from playwright.async_api import BrowserContext, Page

from facebook_api.utils.browser import BrowserManager, browser_manager, random_user_agent


async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _safe_close_context(context: BrowserContext) -> None:
    try:
        await context.close()
    except Exception:
        pass


async def _goto_login(page: Page) -> None:
    attempt = 0
    while True:
        attempt += 1
        try:
            await page.goto(
                "https://www.facebook.com/login",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await random_delay(1, 2)
            return
        except Exception as e:
            if attempt >= 2:
                raise TimeoutError(
                    f"No se pudo cargar la pagina de login de Facebook: {e}"
                )
            await random_delay(2, 3)


async def login_facebook(email: str, password: str) -> dict:
    context = await browser_manager.create_context()
    try:
        page = await context.new_page()
        page.set_default_timeout(30000)

        await _goto_login(page)

        email_input = page.locator('input[name="email"]')
        try:
            await email_input.first.wait_for(state="visible", timeout=15000)
        except Exception:
            raise Exception("No se renderizo el formulario de login de Facebook")
        await email_input.first.fill(email)
        await random_delay(0.5, 1)

        pass_input = page.locator('input[name="pass"]')
        try:
            await pass_input.first.wait_for(state="visible", timeout=10000)
        except Exception:
            raise Exception("No se renderizo el campo de password")
        await pass_input.first.fill(password)
        await random_delay(0.5, 1)

        submit_btn = page.locator('input[type="submit"]')
        if await submit_btn.count() == 0:
            submit_btn = page.locator('[role="button"]:has-text("Iniciar sesión")')
        if await submit_btn.count() == 0:
            submit_btn = page.locator('[role="button"]:has-text("Log In")')

        submitted = False
        if await submit_btn.count() > 0 and await submit_btn.first.is_enabled():
            try:
                await submit_btn.first.click(timeout=5000)
                submitted = True
            except Exception:
                submitted = False

        if not submitted:
            await pass_input.first.press("Enter")

        try:
            await page.wait_for_load_state("domcontentloaded", timeout=20000)
        except asyncio.TimeoutError:
            pass

        await random_delay(3, 5)

        current_url = page.url
        if "checkpoint" in current_url:
            raise Exception("Facebook pide verificacion adicional (checkpoint)")

        cookies = await context.cookies()
        user_agent = await page.evaluate("navigator.userAgent")

        fb_user_id = None
        has_session = False
        for cookie in cookies:
            if cookie["name"] == "c_user":
                fb_user_id = cookie["value"]
                has_session = True

        if not has_session:
            raise Exception(
                "El login no se confirmo: credenciales invalidas o Facebook lo bloqueo"
            )

        return {
            "cookies": cookies,
            "user_agent": user_agent,
            "fb_user_id": fb_user_id,
        }
    finally:
        await _safe_close_context(context)


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


async def list_groups(encrypted_cookies: str, decrypt_fn) -> list[dict]:
    context, page = await _get_authenticated_context(encrypted_cookies, decrypt_fn)
    try:
        await page.goto(
            "https://www.facebook.com/groups/feed", wait_until="networkidle"
        )
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
    await page.goto("https://www.facebook.com/groups", wait_until="networkidle")
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
        await page.goto(
            f"https://www.facebook.com/groups/{group_id}", wait_until="networkidle"
        )
        await random_delay(2, 4)

        composer = page.locator('[role="button"]:has-text("Escribir algo...")')
        if await composer.count() == 0:
            composer = page.locator('[role="button"]:has-text("Write something")')
        if await composer.count() == 0:
            composer = page.locator('[aria-label*="publicar"], [aria-label*="write"]')

        if await composer.count() == 0:
            raise Exception("Could not find post composer")

        await composer.first.click()
        await random_delay(1, 2)

        textbox = page.locator('[role="textbox"][contenteditable="true"]')
        if await textbox.count() == 0:
            textbox = page.locator('[data-lexical-editor="true"]')

        if await textbox.count() == 0:
            raise Exception("Could not find text input")

        await textbox.first.click()
        await random_delay(0.3, 0.5)
        await textbox.first.fill(text)
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

        post_btn = page.locator(
            'div[aria-label="Publicar"], div[aria-label="Post"]'
        )
        if await post_btn.count() == 0:
            post_btn = page.locator('button:has-text("Publicar"), button:has-text("Post")')

        if await post_btn.count() == 0:
            raise Exception("Could not find post button")

        await post_btn.first.click()
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
        await page.goto("https://www.facebook.com/", wait_until="networkidle")
        await random_delay(2, 4)

        composer = page.locator(
            '[aria-label*="en que estas pensando"], [aria-label*="on your mind"]'
        )
        if await composer.count() == 0:
            composer = page.locator('[role="button"]:has-text("¿Qué hay de nuevo")')
        if await composer.count() == 0:
            composer = page.locator('[role="button"]:has-text("What")')

        if await composer.count() == 0:
            raise Exception("Could not find profile post composer")

        await composer.first.click()
        await random_delay(1, 2)

        textbox = page.locator('[role="textbox"][contenteditable="true"]')
        if await textbox.count() == 0:
            textbox = page.locator('[data-lexical-editor="true"]')

        if await textbox.count() == 0:
            raise Exception("Could not find text input")

        await textbox.first.click()
        await random_delay(0.3, 0.5)
        await textbox.first.fill(text)
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

        post_btn = page.locator(
            'div[aria-label="Publicar"], div[aria-label="Post"]'
        )
        if await post_btn.count() == 0:
            post_btn = page.locator('button:has-text("Publicar"), button:has-text("Post")')

        if await post_btn.count() == 0:
            raise Exception("Could not find post button")

        await post_btn.first.click()
        await random_delay(3, 5)

        return {"status": "success"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
    finally:
        await _safe_close_context(context)
