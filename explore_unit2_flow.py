import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, PASSWORD, URL, USERNAME, require_login_config

async def login(page):
    require_login_config()
    await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
    user_input = await page.wait_for_selector("input[name='userName']", timeout=20000)
    pass_input = await page.wait_for_selector("input[name='password']", timeout=20000)
    submit_btn = await page.wait_for_selector("input#submit1", timeout=20000)

    await user_input.click()
    await user_input.fill("")
    await user_input.type(USERNAME, delay=30)

    await pass_input.click()
    await pass_input.fill("")
    await pass_input.type(PASSWORD, delay=30)
    await page.wait_for_timeout(500)
    await submit_btn.click()

    for _ in range(15):
        await page.wait_for_timeout(1000)
        if "#/home" in page.url:
            break
        modal_btns = await page.query_selector_all(".modal-dialog button, button:has-text('Login on This Device')")
        for btn in modal_btns:
            if await btn.is_visible():
                await btn.click()
                break

    await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=20000)
    continue_btn = await page.query_selector(".carouselStartBtnW a, a:has-text('Continue')")
    await continue_btn.click()
    await page.wait_for_timeout(6000)
    print(f"[*] Entered learning area: {page.url}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await login(page)

        # Let's inspect current step and task counter
        for step_idx in range(1, 6):
            print(f"\n--- STEP/ACTION {step_idx} ---")
            await page.wait_for_timeout(2000)
            
            # Print current lesson and step name
            lesson_title = await page.evaluate('''() => {
                const header = document.querySelector('.learning__lessonsStepsNav');
                return header ? header.innerText.replace(/\\n+/g, ' | ') : 'No header';
            }''')
            print(f"Header status: {lesson_title}")

            # Check if there is an audio or video element
            media_info = await page.evaluate('''() => {
                const videos = document.querySelectorAll('video');
                const audios = document.querySelectorAll('audio');
                return {
                    videoCount: videos.length,
                    audioCount: audios.length
                };
            }''')
            print(f"Media info: {media_info}")

            # Look for questions or inputs
            form_info = await page.evaluate('''() => {
                const radios = Array.from(document.querySelectorAll('input[type=\"radio\"]')).map(r => r.id || r.value);
                const texts = Array.from(document.querySelectorAll('input[type=\"text\"]')).map(t => t.id || t.placeholder);
                const buttons = Array.from(document.querySelectorAll('button, .learning__actionBtn, a[role=\"button\"]')).map(b => b.innerText.trim()).filter(Boolean);
                return { radios, texts, buttons };
            }''')
            print(f"Form elements: {form_info}")

            # Screenshot
            await page.screenshot(path=f"{OUTPUT_DIR}/step_{step_idx}.png")

            # Click next
            next_btn = await page.query_selector("#learning__nextItem, .learning__nextItem, .learning__nextItemLink")
            if next_btn and await next_btn.is_visible():
                print("Clicking Next (#learning__nextItem)...")
                await next_btn.click()
            else:
                print("Next button not visible or reached end.")
                break

            await page.wait_for_timeout(3000)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
