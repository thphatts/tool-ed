import asyncio
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in, URL
from run_any_unit import UniversalEngDisAgent


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        await page.locator("#home__unitIW_4").click(force=True)
        await page.wait_for_url("**/learningArea.html*", timeout=30000)
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        agent = UniversalEngDisAgent(page, context)
        await agent.select_lesson_in_learning_area("3")
        await agent.select_step_in_learning_area("Interact")
        # Step menu may restore either Intro or task 1 depending on the last
        # attempt. Advance only from Intro; otherwise stay on the task.
        if await page.locator(".chooseCaracterArrow:visible").count() == 0:
            await page.locator(".learning__nextItemLink").click(force=True)
        for _ in range(12):
            if "click on the arrow" in (await page.locator("body").inner_text()).lower():
                break
            await page.wait_for_timeout(1000)
        await page.locator(".chooseCaracterArrow:visible").nth(1).click(force=True)
        for _ in range(12):
            if "click 'start'" in (await page.locator("body").inner_text()).lower():
                break
            await page.wait_for_timeout(500)
        await page.locator("a.button.continue:visible").first.click(force=True)
        for tick in range(12):
            await page.wait_for_timeout(5000)
            body = (await page.locator("body").inner_text())[-1800:]
            print("TICK", tick + 1, body)
            if any(s in body.lower() for s in ["try again", "completed", "well done", "start again"]):
                break
        await page.screenshot(path="run_artifacts/complete_unit5_interact.png")
        next_btn = page.locator(".learning__nextItemLink").first
        if await next_btn.count() and await next_btn.is_visible():
            await next_btn.click(force=True)
            await page.wait_for_timeout(2500)
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        card6 = page.locator("#home__unitIW_5")
        print("UNIT6_CLASS", await card6.locator("xpath=..").get_attribute("class"))
        print("UNIT6_TEXT", await card6.locator("xpath=..").inner_text())
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
