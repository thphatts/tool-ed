import asyncio
from playwright.async_api import async_playwright

from session_manager import ensure_logged_in
from run_any_unit import UniversalEngDisAgent


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        agent = UniversalEngDisAgent(page, context)
        assert await agent.select_course_on_dashboard("Intermediate 2")
        assert await agent.select_unit_on_dashboard("3", "4")
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await agent.select_lesson_in_learning_area("4")
        await agent.select_step_in_learning_area("Practice")
        await page.wait_for_timeout(1500)
        if "Intro" in " ".join(await page.locator(".learning__tasksPager").all_inner_texts()):
            await agent.advance_next()
            await page.wait_for_timeout(1200)
        print("STATUS", await page.locator(".learning__dropDownListTitleW").all_inner_texts(), await page.locator(".learning__tasksPager").all_inner_texts())
        rows = await page.evaluate('''() => Array.from(document.querySelectorAll(
            '.droptarget, .dndZone, .TTpanswerDiv, [ed-trackable-drop*="User_Answer"], .prCLZ__regContainer .dndZone, [class*="regContainer"] .dndZone'
        )).map((e, i) => {
            const r=e.getBoundingClientRect(), s=getComputedStyle(e);
            return {i, tag:e.tagName, cls:e.className, id:e.id, track:e.getAttribute('ed-trackable-drop'),
                text:(e.innerText||'').trim(), w:r.width, h:r.height, x:r.x, y:r.y,
                display:s.display, visibility:s.visibility, opacity:s.opacity,
                child:!!e.querySelector('.droptarget,.dndZone,.TTpanswerDiv,[ed-trackable-drop*="User_Answer"]'),
                html:e.outerHTML.slice(0,1200)};
        })''')
        for row in rows:
            print("TARGET", row)
        await page.screenshot(path="run_artifacts/inspect_dnd.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
