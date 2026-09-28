import asyncio
import re
from playwright.async_api import async_playwright

from session_manager import ensure_logged_in
from run_any_unit import UniversalEngDisAgent


ANSWERS = [
    ["'d answered"],
    ["had never been"],
    ["had", "already", "passed"],
    ["had", "seen"],
    ["had", "graduated"],
]


async def fill_dnd(page, words):
    target_sel = '.dndZone:visible:not([id^="bank_"]):not(:has(.draggable)), .droptarget:visible:not([id^="bank_"]):not(:has(.draggable))'
    chips = page.locator('.dnditem.draggable, .draggable.wordBankTile, .draggable')
    for idx in range(len(words) - 1, -1, -1):
        word = words[idx]
        target = page.locator(target_sel).nth(idx)
        chip = chips.filter(has_text=re.compile(rf"^\s*{re.escape(word)}\s*$", re.I)).first
        print("FILL", idx, word, await target.count(), await chip.count())
        await chip.drag_to(target)
        await page.wait_for_timeout(350)


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        agent = UniversalEngDisAgent(page, context)
        assert await agent.select_course_on_dashboard("Intermediate 2")
        assert await agent.select_unit_on_dashboard("3", "4")
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await agent.select_lesson_in_learning_area("4")
        await agent.select_step_in_learning_area("Test")
        await page.wait_for_timeout(1200)
        start = page.locator('.btnStartTest, #testIntro a, .startTest a').first
        if await start.count() and await start.is_visible():
            await start.evaluate("el => el.click()")
            await page.wait_for_timeout(1800)

        for i, words in enumerate(ANSWERS, 1):
            print("TASK", i, await page.locator('.learning__tasksPager').all_inner_texts())
            await fill_dnd(page, words)
            await agent.advance_next()
            await page.wait_for_timeout(1200)

        score = await agent.get_current_test_score()
        print("SCORE", score)
        await page.screenshot(path="run_artifacts/unit3_lesson4_fixed.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
