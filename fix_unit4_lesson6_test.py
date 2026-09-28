import asyncio
import re
from playwright.async_api import async_playwright

from session_manager import ensure_logged_in
from run_any_unit import UniversalEngDisAgent


ANSWERS = [
    [", which", "where"],
    [", which I regret", "whenever"],
    ["which", "wherever"],
    ["where", "wherever"],
    ["where", ", which"],
    [", who", "whenever"],
    ["where", "Wherever"],
    [", which", "where"],
    ["whose", "wherever"],
    ["where", "whatever"],
]


async def exact(locator, value):
    return locator.filter(has_text=re.compile(rf"^\s*{re.escape(value)}\s*$", re.I)).first


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        agent = UniversalEngDisAgent(page, context)
        await agent.select_unit_on_dashboard("4")
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await agent.select_lesson_in_learning_area("6")
        await agent.select_step_in_learning_area("Test")
        await page.wait_for_timeout(1800)
        start = page.locator(".btnStartTest, #testIntro a, .startTest a, .layout__roundBtn").first
        if await start.count() and await start.is_visible():
            await start.click(force=True)
            await page.wait_for_timeout(2200)

        for number, answers in enumerate(ANSWERS, 1):
            ddls = page.locator(".DDLOptions__selected:visible")
            if await ddls.count():
                for idx, answer in enumerate(answers):
                    await ddls.nth(idx).click(force=True)
                    await page.wait_for_timeout(250)
                    options = page.locator(".DDLOptions__listItem:visible, .DDLOptions__list li:visible")
                    option = await exact(options, answer)
                    await option.click(force=True)
            else:
                chips = page.locator(".draggable.wordBankTile, .wordsBankWrapper .draggable, .dnditem.draggable, .dndBank .dnditem, .draggable")
                targets = page.locator(".droptarget:visible:not(:has(.droptarget:visible))")
                if await targets.count() < len(answers):
                    targets = page.locator(".dndZone:visible:not(:has(.dndZone:visible))")
                print("TASK", number, "LEAF_TARGETS", await targets.count(), answers)
                for idx, answer in enumerate(answers):
                    chip = await exact(chips, answer)
                    await chip.drag_to(targets.nth(idx), force=True)
                    await page.wait_for_timeout(350)
            print("ADVANCE", await agent.advance_next())
            await page.wait_for_timeout(700)

        await page.wait_for_timeout(3500)
        await agent.dismiss_all_popups()
        print("FINAL_SCORE", await agent.get_current_test_score())
        await page.screenshot(path="run_artifacts/fix_unit4_lesson6_result.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
