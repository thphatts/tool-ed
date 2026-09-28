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
                await page.wait_for_timeout(2000)

        # Go to Task 1
        next_btn = await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink", timeout=10000)
        await next_btn.click()
        await page.wait_for_timeout(4000)

        print("[*] Now at Task 1. Finding correct answer element...")
        correct_label = await page.query_selector(".multiRadio.correct label, .selection--v + .multiRadio label")
        if correct_label:
            txt = (await correct_label.inner_text()).strip()
            print(f"[*] Found correct option: '{txt}'! Clicking it...")
            await correct_label.click()
        else:
            print("[!] Could not find .multiRadio.correct directly, clicking 3rd option...")
            opt = page.locator("label:has-text('an antiques store.')")
            await opt.click()

        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{OUTPUT_DIR}/task1_selected.png")

        # Click Check Answer
        check_btn = await page.query_selector("#CheckAnswer")
        if check_btn:
            print("[*] Clicking Check Answer (#CheckAnswer)...")
            await check_btn.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{OUTPUT_DIR}/task1_checked.png")
            print("[*] Saved task1_checked.png")

        # Advance to Task 2
        print("[*] Clicking Next to advance to Task 2...")
        next_btn = await page.query_selector("#learning__nextItem, .learning__nextItemLink")
        await next_btn.click()
        await page.wait_for_timeout(4000)

        await page.screenshot(path=f"{OUTPUT_DIR}/practice_task_2.png")
        print("[*] Arrived at Task 2! Saved practice_task_2.png")

        # Inspect Task 2 HTML and question
        text2 = await page.evaluate("() => document.querySelector('.learning__unit') ? document.querySelector('.learning__unit').innerText : document.body.innerText")
        print("=== TASK 2 PREVIEW ===")
        for line in [l.strip() for l in text2.splitlines() if l.strip()][:30]:
            print(f"  > {line}")

        with open(f"{OUTPUT_DIR}/practice_task_2.html", "w", encoding="utf-8") as f:
            f.write(await page.content())

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
