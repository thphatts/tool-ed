import asyncio
from playwright.async_api import async_playwright

from session_manager import ensure_logged_in
from run_any_unit import UniversalEngDisAgent


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        agent = UniversalEngDisAgent(page, context)
        await agent.select_unit_on_dashboard("4")
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await agent.select_lesson_in_learning_area("5")
        await agent.select_step_in_learning_area("Test")
        await page.wait_for_timeout(2500)

        body = (await page.locator("body").inner_text())
        print("RESULT_PAGE", "Your test score is" in body, body[-1000:])
        review = page.get_by_text("Review", exact=True).last
        if await review.count() and await review.is_visible():
            await review.click(force=True)
            await page.wait_for_timeout(2500)

        for task in range(1, 6):
            tabs = page.locator(".testResultTools a")
            print("TASK", task, "TABS", await tabs.count(), await tabs.all_inner_texts())
            if await tabs.count() >= 2:
                await tabs.nth(1).click(force=True)
                await page.wait_for_timeout(700)
            state = await page.evaluate("""() => ({
                tabs: Array.from(document.querySelectorAll('.testResultTools a')).map(a => ({text: a.innerText, cls: a.className, parent: a.parentElement?.className})),
                work: (document.querySelector('#rightDiv, .pmContainer, .learning__practiceArea, .stepTasksAndPmContainer')?.innerText || '')
            })""")
            print("STATE", task, state)
            await page.screenshot(path=f"run_artifacts/inspect_correct_{task}.png")
            if task < 5:
                await page.locator("#learning__nextItem, .learning__nextItemLink").first.click(force=True)
                await page.wait_for_timeout(700)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
