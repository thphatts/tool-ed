import asyncio
from playwright.async_api import async_playwright
import os
from settings import CHROMIUM_ARGS, STORAGE_STATE, URL

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        context = await browser.new_context(storage_state=STORAGE_STATE, viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        await page.goto(URL, wait_until='domcontentloaded')
        continue_btn = await page.wait_for_selector('.carouselStartBtnW a, a:has-text(\"Continue\")')
        await continue_btn.click()
        await page.wait_for_selector('.learning__lessonsStepsNav')

        # Open Steps dropdown and click Test
        dropdowns = await page.query_selector_all('.learning__dropDownListTitleW')
        await dropdowns[1].click()
        await page.wait_for_timeout(500)
        test_step = await page.query_selector('.learning__dropDownList_item:has-text(\"Test\")')
        if test_step:
            await test_step.click()
            await page.wait_for_timeout(2000)

        # Check for Start Test button
        start_test_btn = await page.query_selector('.learning__btnStartTest, button:has-text(\"Start Test\"), a:has-text(\"Start Test\"), .startTest')
        if not start_test_btn:
            start_test_btn = await page.query_selector('div:has-text(\"Start Test\"), .layout__btnAction')

        if start_test_btn:
            print(f'Found Start Test: {await start_test_btn.inner_text()}, clicking...')
            await start_test_btn.click()
            await page.wait_for_timeout(3000)

        await page.screenshot(path='run_artifacts/test_step_screen.png')
        print('Saved test_step_screen.png')

        # Inspect test questions
        test_info = await page.evaluate('''() => {
            const body = document.querySelector('.learning__unit') ? document.querySelector('.learning__unit').innerText : document.body.innerText;
            const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
            return { pager, body: body.slice(0, 500) };
        }''')
        print('Test Info:', test_info)

        await browser.close()

asyncio.run(main())
