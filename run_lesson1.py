import asyncio
import os
import sys
from playwright.async_api import async_playwright
from solver_engine import EngDisSolver, CHROMIUM_ARGS, STORAGE_STATE
from settings import URL

OUTPUT_DIR = "run_artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def run_lesson_1(headless=True):
    async with async_playwright() as p:
        print(f"[*] Starting runner (headless={headless})...")
        browser = await p.chromium.launch(headless=headless, args=CHROMIUM_ARGS)
        context = await browser.new_context(storage_state=STORAGE_STATE, viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=20000)
        await continue_btn.click()
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=25000)
        await page.wait_for_timeout(2000)

        solver = EngDisSolver(page)

        # Loop through tasks
        for task_num in range(1, 15):
            await page.wait_for_timeout(2000)
            await solver.dismiss_popups_and_reminders()

            # Read current status
            status = await page.evaluate('''() => {
                const dropdowns = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
                const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
                return { dropdowns, pager };
            }''')
            print(f"\n[Task Step {task_num}] Status: {status['dropdowns']} | Pager: {status['pager']}")

            # Screenshot current state
            await page.screenshot(path=f"{OUTPUT_DIR}/lesson1_step_{task_num}.png")

            # Solve
            res = await solver.solve_current_task()
            print(f"[*] Solver action result: {res}")

            await page.wait_for_timeout(1000)
            # Advance
            advanced = await solver.advance_next()
            if not advanced:
                print("[*] Reached end of current step or lesson!")
                break

            await page.wait_for_timeout(2000)

        print("[*] Completed Lesson 1 run!")
        await page.screenshot(path=f"{OUTPUT_DIR}/lesson1_finished.png")
        await browser.close()

if __name__ == "__main__":
    is_headless = "--headed" not in sys.argv
    asyncio.run(run_lesson_1(headless=is_headless))
