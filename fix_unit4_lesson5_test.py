import asyncio
import re
from playwright.async_api import async_playwright

from session_manager import ensure_logged_in
from run_any_unit import UniversalEngDisAgent


ANSWERS = ["where", "whose", "where", "where", "where"]


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        agent = UniversalEngDisAgent(page, context)
        await agent.select_unit_on_dashboard("4")
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await agent.select_lesson_in_learning_area("5")
        await agent.select_step_in_learning_area("Test")
        await page.wait_for_timeout(1800)

        start = page.locator(".btnStartTest, #testIntro a, .startTest a, .layout__roundBtn").first
        if await start.count() and await start.is_visible():
            await start.click(force=True)
            await page.wait_for_timeout(2200)

        for number, answer in enumerate(ANSWERS, 1):
            chips = page.locator(".draggable.wordBankTile, .wordsBankWrapper .draggable, .dnditem.draggable, .dndBank .dnditem, .draggable")
            chip = chips.filter(has_text=re.compile(rf"^\s*{re.escape(answer)}\s*$", re.I)).first
            targets = page.locator(".droptarget:visible")
            if await targets.count() == 0:
                targets = page.locator(".dndZone:visible, .TTpanswerDiv:visible")
            target = targets.first
            print("TASK", number, "ANSWER", answer, "TARGETS", await targets.count())

            for attempt in range(3):
                await chip.drag_to(target, force=True)
                await page.wait_for_timeout(500)
                placed = (await target.inner_text()).strip()
                print("PLACED", attempt + 1, repr(placed))
                if answer.casefold() in placed.casefold():
                    break

            result = await agent.advance_next()
            print("ADVANCE", result)
            if number < len(ANSWERS):
                await page.wait_for_timeout(1000)

        await page.wait_for_timeout(3500)
        await agent.dismiss_all_popups()
        print("FINAL_SCORE", await agent.get_current_test_score())
        await page.screenshot(path="run_artifacts/fix_unit4_lesson5_result.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
