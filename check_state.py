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
        await page.wait_for_timeout(3000)

        # Current state
        state = await page.evaluate('''() => {
            const lesson = document.querySelector('.learning__dropDownListTitleW') ? document.querySelector('.learning__dropDownListTitleW').innerText : '';
            const allDropdowns = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
            const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
            const text = document.querySelector('.learning__unit') ? document.querySelector('.learning__unit').innerText : document.body.innerText;
            return { allDropdowns, pager, textPreview: text.slice(0, 500) };
        }''')

        print("=== CURRENT LEARNING STATE ===")
        print(f"Dropdowns: {state['allDropdowns']}")
        print(f"Pager: {state['pager']}")
        print(f"Content preview:\n{state['textPreview']}")

        await page.screenshot(path=f"{OUTPUT_DIR}/current_progress_state.png")
        print("[*] Saved current_progress_state.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
