import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, PASSWORD, URL, USERNAME, require_login_config

async def safe_login(page):
    require_login_config()
    print("[*] Navigating to login...")
    await page.goto(URL, wait_until="domcontentloaded", timeout=45000)

    # Check if already logged in or login form
    user_input = await page.wait_for_selector("input[name='userName']", timeout=15000)
    pass_input = await page.wait_for_selector("input[name='password']", timeout=15000)
    submit_btn = await page.wait_for_selector("input#submit1", timeout=15000)

    await user_input.click()
    await user_input.fill("")
    await user_input.type(USERNAME, delay=30)

    await pass_input.click()
    await pass_input.fill("")
    await pass_input.type(PASSWORD, delay=30)
    await page.wait_for_timeout(500)
    await submit_btn.click()

    print("[*] Handling session takeover if needed...")
    for _ in range(15):
        await page.wait_for_timeout(1000)
        if "#/home" in page.url:
            await page.wait_for_timeout(2000)
            break
        # Click duplicate login button if present
        btn = page.locator(".modal-dialog button, button:has-text('Login on This Device'), a:has-text('Login on This Device')")
        if await btn.count() > 0:
            first_btn = btn.first
            if await first_btn.is_visible():
                print("[*] Clicking Login on This Device...")
                await first_btn.click()
                await page.wait_for_timeout(2000)

    print(f"[*] Dashboard URL: {page.url}")
    continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=20000)
    await continue_btn.click()
    print("[*] Clicked Continue, waiting for Learning Area...")
    await page.wait_for_selector(".learning__lessonsStepsNav", timeout=25000)
    await page.wait_for_timeout(3000)
    print(f"[*] Arrived in Learning Area: {page.url}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await safe_login(page)
        await page.screenshot(path=f"{OUTPUT_DIR}/nav_01_initial.png")

        # Let's inspect the dropdowns at top
        dropdown_titles = await page.locator(".learning__dropDownListTitleW").all()
        print(f"[*] Found {len(dropdown_titles)} top navigation dropdowns:")
        for idx, dd in enumerate(dropdown_titles):
            txt = (await dd.inner_text()).strip().replace("\n", " ")
            print(f"    - Dropdown {idx}: '{txt}'")

        # Click the 2nd dropdown (Steps: Explore, Practice, Test)
        if len(dropdown_titles) >= 2:
            print("[*] Clicking Step dropdown to see all steps...")
            await dropdown_titles[1].click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f"{OUTPUT_DIR}/nav_02_step_menu.png")

            # Look for "Practice"
            practice_item = page.locator(".learning__dropDownList_item:has-text('Practice')")
            if await practice_item.count() > 0:
                print("[*] Clicking 'Practice' in dropdown...")
                await practice_item.first.click()
                await page.wait_for_timeout(4000)
                await page.screenshot(path=f"{OUTPUT_DIR}/nav_03_practice_loaded.png")

                # Inspect what is inside Practice
                text = await page.evaluate("() => document.body.innerText")
                print("=== PRACTICE SCREEN TEXT PREVIEW ===")
                for line in [l.strip() for l in text.split('\n') if l.strip()][:30]:
                    print(f"    > {line}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
