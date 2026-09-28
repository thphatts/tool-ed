import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, STORAGE_STATE, URL

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        print("[*] Opening Home Dashboard with stored session...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)

        continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=20000)
        print(f"[*] Found button: '{await continue_btn.inner_text()}', clicking into Unit 2...")
        await continue_btn.click()

        print("[*] Waiting for Learning Area to load...")
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=25000)
        await page.wait_for_timeout(3000)
        print(f"[*] In Learning Area: {page.url}")

        # Open the Steps Dropdown
        dropdowns = await page.query_selector_all(".learning__dropDownListTitleW")
        if len(dropdowns) >= 2:
            print("[*] Opening Steps dropdown (Explore, Practice, Test)...")
            await dropdowns[1].click()
            await page.wait_for_timeout(1000)

            # Click Practice
            practice_btn = await page.query_selector(".learning__dropDownList_item:has-text('Practice')")
            if practice_btn:
                print("[*] Navigating to Practice step...")
                await practice_btn.click()
                await page.wait_for_timeout(4000)

        await page.screenshot(path=f"{OUTPUT_DIR}/practice_initial.png")
        print(f"[*] Practice step loaded, screenshot saved: practice_initial.png")

        # Let's inspect the practice container
        content_text = await page.evaluate('''() => {
            const body = document.querySelector('.learning__unit') || document.body;
            return body.innerText;
        }''')
        print("=== PRACTICE CONTENT PREVIEW ===")
        for line in [l.strip() for l in content_text.splitlines() if l.strip()][:40]:
            print(f"  {line}")

        # Save HTML
        with open(f"{OUTPUT_DIR}/practice_page.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
