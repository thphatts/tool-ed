import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, PASSWORD, URL, USERNAME, require_login_config

async def login_and_get_to_home(page):
    require_login_config()
    print("[*] Loading login page...")
    await page.goto(URL, wait_until="domcontentloaded", timeout=45000)

    user_input = await page.wait_for_selector("input[name='userName']", timeout=20000)
    pass_input = await page.wait_for_selector("input[name='password']", timeout=20000)
    submit_btn = await page.wait_for_selector("input#submit1", timeout=20000)

    await user_input.fill(USERNAME)
    await pass_input.fill(PASSWORD)
    await submit_btn.click()

    # Look for either home dashboard OR duplicate login popup
    print("[*] Waiting for dashboard or duplicate login confirmation...")
    for _ in range(20):
        await page.wait_for_timeout(1000)
        
        # Check modal
        modal_btn = await page.query_selector("button:has-text('Login on This Device'), a:has-text('Login on This Device'), .modal-dialog button")
        if modal_btn and await modal_btn.is_visible():
            print("[*] Clicking 'Login on This Device'...")
            await modal_btn.click()
            await page.wait_for_timeout(2000)

        # Check if we reached home
        if "#/home" in page.url:
            continue_btn = await page.query_selector(".carouselStartBtnW a, a:has-text('Continue')")
            if continue_btn and await continue_btn.is_visible():
                print("[*] Successfully arrived at Home dashboard!")
                return True

    print(f"[*] Finished waiting, current URL: {page.url}")
    return "#/home" in page.url

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        success = await login_and_get_to_home(page)
        if not success:
            await page.screenshot(path=f"{OUTPUT_DIR}/login_failed_state.png")
            print("[!] Could not reach dashboard successfully.")
            await browser.close()
            return

        await page.screenshot(path=f"{OUTPUT_DIR}/06_dashboard_ready.png")

        continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=15000)
        print(f"[*] Clicking Continue button: {await continue_btn.inner_text()}...")
        await continue_btn.click()

        print("[*] Waiting for lesson to load...")
        await page.wait_for_timeout(10000)
        await page.screenshot(path=f"{OUTPUT_DIR}/07_inside_lesson.png")
        print(f"[*] Current URL: {page.url}")

        # Check frames
        print(f"[*] Total frames: {len(page.frames)}")
        for idx, frame in enumerate(page.frames):
            print(f"    - Frame {idx}: name='{frame.name}', url='{frame.url}'")

        # Save HTML
        with open(f"{OUTPUT_DIR}/lesson_page.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

        # Check text in lesson
        text = await page.evaluate("() => document.body.innerText")
        print("[*] Lesson Screen Text Summary:")
        for line in text.split("\n")[:30]:
            if line.strip():
                print(f"    > {line.strip()}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
