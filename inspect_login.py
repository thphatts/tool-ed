import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, PASSWORD, URL, USERNAME, require_login_config

os.makedirs(OUTPUT_DIR, exist_ok=True)

async def main():
    require_login_config()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=CHROMIUM_ARGS
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        print(f"[*] Navigating to {URL}...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)

        user_input = await page.wait_for_selector("input[name='userName']", timeout=15000)
        pass_input = await page.wait_for_selector("input[name='password']", timeout=15000)
        submit_btn = await page.wait_for_selector("input#submit1", timeout=15000)

        print("[*] Typing credentials...")
        await user_input.fill(USERNAME)
        await pass_input.fill(PASSWORD)

        print("[*] Clicking Login...")
        await submit_btn.click()

        # Check for "Login on This Device" modal
        print("[*] Checking for duplicate login confirmation...")
        try:
            confirm_btn = await page.wait_for_selector(
                "button:has-text('Login on This Device'), a:has-text('Login on This Device'), input[value*='Login on This Device'], .modal-dialog button, .ui-dialog button",
                timeout=8000
            )
            if confirm_btn:
                btn_text = await confirm_btn.inner_text()
                print(f"[*] Found modal button: '{btn_text}', clicking to take over session...")
                await confirm_btn.click()
        except Exception:
            print("[*] No 'Login on This Device' modal appeared (or timed out).")

        print("[*] Waiting for dashboard to load...")
        await page.wait_for_timeout(8000)
        await page.screenshot(path=f"{OUTPUT_DIR}/05_logged_in_dashboard.png")
        print(f"[*] Current URL: {page.url}")

        # Look for courses and Unit 2
        text_content = await page.evaluate("() => document.body.innerText")
        print("[*] Page Text Snippet:")
        for line in text_content.split("\n"):
            line = line.strip()
            if line and any(k in line.lower() for k in ["unit", "accident", "course", "lesson", "start", "continue", "progress"]):
                print(f"    > {line}")

        # Save html
        with open(f"{OUTPUT_DIR}/dashboard_logged_in.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
