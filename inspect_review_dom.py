import asyncio
from playwright.async_api import async_playwright

from session_manager import ensure_logged_in
from run_any_unit import UniversalEngDisAgent
from fix_inspect_unit3_lesson4 import ANSWERS, fill_dnd


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
        print("BEFORE", (await page.locator("body").inner_text())[-1500:])
        start = page.locator('.btnStartTest, #testIntro a, .startTest a').first
        if await start.count() and await start.is_visible():
            await start.evaluate("el => el.click()")
            await page.wait_for_timeout(1500)
            for words in ANSWERS:
                await fill_dnd(page, words)
                await agent.advance_next()
                await page.wait_for_timeout(900)
        review = page.locator("a:has-text('Review'), button:has-text('Review')").first
        if await review.count() and await review.is_visible():
            await review.click(force=True)
            await page.wait_for_timeout(1600)
        for _ in range(3):
            await agent.advance_next()
            await page.wait_for_timeout(900)
        tab = page.locator('.testResultTools a[index="1"], .testResultTools li:nth-child(2) a').or_(page.get_by_text("Correct Answer", exact=True)).first
        await tab.click(force=True)
        await page.wait_for_timeout(1200)
        print("PAGER", await page.locator(".learning__tasksPager").all_inner_texts())
        rows = await page.evaluate('''() => {
          const root=document.querySelector('#rightDiv,.pmContainer,.learning__practiceArea,.stepTasksAndPmContainer') || document.body;
          return Array.from(root.querySelectorAll('*')).filter(e => {
            const t=(e.innerText||'').trim();
            return t && t.length < 80 && e.children.length === 0 && e.offsetParent !== null;
          }).map(e => {
            const s=getComputedStyle(e), r=e.getBoundingClientRect();
            return {tag:e.tagName, cls:e.className, id:e.id, text:(e.innerText||'').trim(), bg:s.backgroundColor,
              color:s.color, x:r.x, y:r.y, w:r.width, h:r.height,
              parentTag:e.parentElement?.tagName, parentCls:e.parentElement?.className,
              parentId:e.parentElement?.id};
          });
        }''')
        for row in rows:
            print("LEAF", row)
        await page.screenshot(path="run_artifacts/review_dom_q4.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
