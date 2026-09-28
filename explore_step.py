import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, STORAGE_STATE, URL

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=20000)
        await continue_btn.click()
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=25000)
        await page.wait_for_timeout(2000)

        # Click next in Explore
        next_btn = await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink", timeout=10000)
        print("[*] Clicking Next in Step 1: Explore...")
        await next_btn.click()
        await page.wait_for_timeout(3000)

        pager_text = await page.evaluate("() => document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : ''")
        print(f"[*] Pager in Explore: {pager_text}")
        await page.screenshot(path=f"{OUTPUT_DIR}/explore_task.png")

        # Check if video play button exists
        play_btn = await page.query_selector(".play-btn, .vjs-big-play-button, button[title='Play'], .playerPlayPauseBtn")
        if play_btn:
            print("[*] Found video play button, clicking play...")
            await play_btn.click()
            await page.wait_for_timeout(3000)

        # Click Next again to see if Explore ends and goes to Practice
        next_btn = await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink", timeout=10000)
        print("[*] Clicking Next again in Explore...")
        await next_btn.click()
        await page.wait_for_timeout(4000)

        new_state = await page.evaluate('''() => {
            const allDropdowns = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
            const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
            return { allDropdowns, pager };
        }''')
        print(f"[*] State after second next: {new_state}")
        await page.screenshot(path=f"{OUTPUT_DIR}/after_explore_next.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
