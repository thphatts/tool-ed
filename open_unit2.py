import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, OUTPUT_DIR, PASSWORD, URL, USERNAME, require_login_config

async def main():
    require_login_config()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        print("[*] Step 1: Navigating to login page...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)

        user_input = await page.wait_for_selector("input[name='userName']", timeout=15000)
        pass_input = await page.wait_for_selector("input[name='password']", timeout=15000)
        submit_btn = await page.wait_for_selector("input#submit1", timeout=15000)

        print("[*] Step 2: Typing credentials...")
        await user_input.click()
        await user_input.fill("")
        await user_input.type(USERNAME, delay=30)

        await pass_input.click()
        await pass_input.fill("")
        await pass_input.type(PASSWORD, delay=30)
        await page.wait_for_timeout(500)

        print("[*] Step 3: Clicking Login button...")
        await submit_btn.click()

        # Step 4: Handle modal if already logged in
        print("[*] Step 4: Waiting for dashboard or duplicate login modal...")
        for sec in range(20):
            await page.wait_for_timeout(1000)
            if "#/home" in page.url:
                # wait 2 more seconds to stabilize
                await page.wait_for_timeout(2000)
                print(f"[*] Arrived at {page.url}!")
                break
            modal_btns = await page.query_selector_all(".modal-dialog button, .ui-dialog button, a:has-text('Login on This Device'), button:has-text('Login on This Device'), .modal-footer button")
            for btn in modal_btns:
                if await btn.is_visible():
                    txt = await btn.inner_text()
                    print(f"[*] Found visible modal button: '{txt}', clicking it...")
                    await btn.click()
                    break

        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{OUTPUT_DIR}/dashboard_ready.png")

        # Step 5: On dashboard, locate Unit 2
        print("[*] Step 5: Looking for Unit 2 / Continue button...")
        continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue'), .btn-continue", timeout=20000)
        print(f"[*] Clicking Continue: {await continue_btn.inner_text()}...")
        await continue_btn.click()

        # Step 6: Wait for lesson view to load
        print("[*] Step 6: Waiting for lesson screen...")
        await page.wait_for_selector("#learning__nextItem, .learning__nextItemLink", timeout=25000)
        await page.wait_for_timeout(3000)
        print(f"[*] Reached learning area: {page.url}")

        # Step 7: Advance through steps
        for step in range(1, 8):
            print(f"\n=== LEARNING STEP {step} ===")
            await page.wait_for_timeout(2000)
            
            # Print state
            state_text = await page.evaluate('''() => {
                const header = document.querySelector('.learning__lessonsStepsNav');
                const pager = document.querySelector('.learning__tasksPager');
                const title = header ? header.innerText.replace(/\\n+/g, ' | ') : '';
                const task = pager ? pager.innerText.replace(/\\n+/g, ' ') : '';
                return `${title} --- Task: ${task}`;
            }''')
            print(f"State: {state_text}")

            # Capture interactive elements (questions, options, inputs)
            interactive_details = await page.evaluate('''() => {
                const radios = Array.from(document.querySelectorAll('input[type=\"radio\"], .learning__option, .learning__choice, label.radio')).map(el => el.innerText || el.value || el.id);
                const inputs = Array.from(document.querySelectorAll('input[type=\"text\"], textarea')).map(el => el.placeholder || el.id || el.name);
                const checkBtns = Array.from(document.querySelectorAll('.learning__checkBtn, button:has-text(\"Check\"), a:has-text(\"Check\"), .learning__actionBtn')).map(el => el.innerText || el.id);
                const questionText = document.querySelector('.learning__question, .learning__taskIW, .learning__content') ? document.querySelector('.learning__question, .learning__taskIW, .learning__content').innerText.slice(0, 300) : '';
                return { radios, inputs, checkBtns, questionPreview: questionText.replace(/\\n+/g, ' ') };
            }''')
            print(f"Interactive: {interactive_details}")

            # Take screenshot
            await page.screenshot(path=f"{OUTPUT_DIR}/lesson_step_{step}.png")

            # Click next
            next_btn = await page.query_selector("#learning__nextItem, .learning__nextItemLink")
            if next_btn and await next_btn.is_visible():
                print("Clicking Next Item...")
                await next_btn.click()
                await page.wait_for_timeout(3000)
            else:
                print("Next button not found or disabled.")
                break

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
