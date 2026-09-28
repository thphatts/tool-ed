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

        # In Explore task 1, let's fast-forward and play video
        next_btn = await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink", timeout=10000)
        await next_btn.click()
        await page.wait_for_timeout(2000)

        print("[*] Triggering video play and completion...")
        video_played = await page.evaluate('''() => {
            const v = document.querySelector('video');
            if (v) {
                v.muted = true;
                v.play();
                v.currentTime = Math.max(0, (v.duration || 75) - 0.5);
                v.dispatchEvent(new Event('ended'));
                return true;
            }
            return false;
        }''')
        print(f"[*] Video triggered: {video_played}")
        await page.wait_for_timeout(2000)

        # Click Next item
        next_btn = await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink")
        print("[*] Clicking Next item after video completion...")
        await next_btn.click()
        await page.wait_for_timeout(2000)

        # If Reminder modal appears, click "Continue"
        reminder_continue = page.locator(".modal-dialog a:has-text('Continue'), a:has-text('Continue'), button:has-text('Continue')")
        if await reminder_continue.count() > 0:
            first_c = reminder_continue.first
            if await first_c.is_visible():
                print("[*] Found Reminder modal, clicking Continue to proceed...")
                await first_c.click()
                await page.wait_for_timeout(3000)

        state = await page.evaluate('''() => {
            const allDropdowns = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
            const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
            return { allDropdowns, pager };
        }''')
        print(f"[*] Current State: {state}")
        await page.screenshot(path=f"{OUTPUT_DIR}/after_video_next.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
