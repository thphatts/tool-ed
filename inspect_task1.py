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

        # Switch to Practice
        dropdowns = await page.query_selector_all(".learning__dropDownListTitleW")
        if len(dropdowns) >= 2:
            await dropdowns[1].click()
            await page.wait_for_timeout(500)
            practice_btn = await page.query_selector(".learning__dropDownList_item:has-text('Practice')")
            if practice_btn:
                await practice_btn.click()
                await page.wait_for_timeout(3000)

        # Now click Next to go from Intro to Task 1
        print("[*] Clicking Next button to enter Task 1 of Practice...")
        next_btn = await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink", timeout=10000)
        await next_btn.click()
        await page.wait_for_timeout(5000)

        await page.screenshot(path=f"{OUTPUT_DIR}/practice_task_1.png")
        print("[*] Saved practice_task_1.png")

        # Let's inspect the question content, instructions, and interactive elements
        info = await page.evaluate('''() => {
            const body = document.querySelector('.learning__unit') || document.body;
            const fullText = body.innerText;
            const inputs = Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
                tag: el.tagName,
                type: el.type,
                name: el.name,
                id: el.id,
                placeholder: el.placeholder
            }));
            const options = Array.from(document.querySelectorAll('.radio, .checkbox, [role=\"radio\"], [role=\"option\"], .learning__option, .matchingItem, .dragItem')).map(el => el.innerText.trim());
            return { fullText, inputs, options };
        }''')

        print("=== TASK 1 QUESTION & TEXT ===")
        print(info['fullText'])
        print("\n=== INPUTS ===")
        print(info['inputs'])
        print("\n=== OPTIONS ===")
        print(info['options'])

        with open(f"{OUTPUT_DIR}/practice_task_1.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
