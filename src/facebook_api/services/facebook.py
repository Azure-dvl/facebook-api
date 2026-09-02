import asyncio
import json
import random

from playwright.async_api import BrowserContext, Page

from facebook_api.utils.browser import BrowserManager, browser_manager, random_user_agent


async def random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def login_facebook(email: str, password: str) -> dict:
    context = await browser_manager.create_context()
    try:
        page = await context.new_page()
        await page.goto("https://www.facebook.com/login", wait_until="networkidle")
        await random_delay(1, 2)

        email_input = page.locator('input[name="email"]')
        await email_input.fill(email)
        await random_delay(0.5, 1)

        pass_input = page.locator('input[name="pass"]')
        await pass_input.fill(password)
        await random_delay(0.5, 1)

        submit_btn = page.locator('button[name="login"]')
        await submit_btn.click()

        await page.wait_for_load_state("networkidle", timeout=15000)
        await random_delay(2, 3)

        current_url = page.url
        if "checkpoint" in current_url or "login" in current_url:
            raise Exception("Login failed: checkpoint or still on login page")

        cookies = await context.cookies()
        user_agent = await page.evaluate("navigator.userAgent")

        fb_user_id = None
        for cookie in cookies:
            if cookie["name"] == "c_user":
                fb_user_id = cookie["value"]
                break

        return {
            "cookies": cookies,
            "user_agent": user_agent,
            "fb_user_id": fb_user_id,
        }
    finally:
        await context.close()


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
        await context.close()


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
        await context.close()


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
        await context.close()
