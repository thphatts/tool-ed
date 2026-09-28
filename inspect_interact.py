import asyncio
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in
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
        await page.wait_for_timeout(1800)
        print("CURRENT", await page.locator(".learning__dropDownListTitleW").all_inner_texts())
        print("BODY", (await page.locator("body").inner_text())[-5000:])
        print("BUTTONS", await page.locator("a:visible, button:visible, input:visible").evaluate_all(
            "els => els.map(e => ({tag:e.tagName, text:(e.innerText||e.value||'').trim(), id:e.id, cls:e.className, title:e.title}))"
        ))
        await page.locator(".learning__nextItemLink").click(force=True)
        await page.wait_for_timeout(1800)
        print("TASK_BODY", (await page.locator("body").inner_text())[-5000:])
        print("TASK_BUTTONS", await page.locator("a:visible, button:visible, input:visible").evaluate_all(
            "els => els.map(e => ({tag:e.tagName, text:(e.innerText||e.value||'').trim(), id:e.id, cls:e.className, title:e.title}))"
        ))
        start = page.locator("a.button.continue:visible").first
        if await start.count():
            await start.click(force=True)
            await page.wait_for_timeout(5000)
            print("AFTER_START", (await page.locator("body").inner_text())[-5000:])
            print("AFTER_START_BUTTONS", await page.locator("a:visible, button:visible, input:visible").evaluate_all(
                "els => els.map(e => ({tag:e.tagName, text:(e.innerText||e.value||'').trim(), id:e.id, cls:e.className, title:e.title}))"
            ))
            arrow = page.locator(".chooseCaracterArrow:visible").first
            if await arrow.count():
                await arrow.click(force=True)
                await page.wait_for_timeout(12000)
                print("AFTER_ARROW", (await page.locator("body").inner_text())[-5000:])
                print("AFTER_ARROW_BUTTONS", await page.locator("a:visible, button:visible, input:visible").evaluate_all(
                    "els => els.map(e => ({tag:e.tagName, text:(e.innerText||e.value||'').trim(), id:e.id, cls:e.className, title:e.title}))"
                ))
        for frame in page.frames:
            try:
                print("FRAME", repr(frame.name), frame.url, (await frame.locator("body").inner_text())[:4000])
            except Exception:
                pass
        await page.screenshot(path="run_artifacts/inspect_interact.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
