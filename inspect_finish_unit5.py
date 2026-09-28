import asyncio
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        await page.locator("#home__unitIW_4").click(force=True)
        await page.wait_for_url("**/learningArea.html*", timeout=30000)
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await page.wait_for_timeout(1500)
        print("CURRENT", await page.locator(".learning__dropDownListTitleW").all_inner_texts())
        print("BODY_TAIL", (await page.locator("body").inner_text())[-2500:])
        await page.locator(".learning__dropDownListTitleW").first.click()
        await page.wait_for_timeout(500)
        print("LESSONS", await page.locator(".learning__dropDownList_item").all_inner_texts())
        await page.locator(".learning__dropDownListTitleW").first.click()

        nexts = page.locator("#learning__nextItem, .learning__nextItemLink, .learning__submitTest")
        print("NEXT", await nexts.count(), await nexts.all_inner_texts())
        if await nexts.count():
            await nexts.first.click(force=True)
            await page.wait_for_timeout(1800)
        print("AFTER_NEXT_URL", page.url)
        print("AFTER_NEXT", (await page.locator("body").inner_text())[-2500:])
        for frame in page.frames:
            try:
                print("FRAME", repr(frame.name), frame.url, (await frame.locator("body").inner_text())[:1500])
            except Exception as exc:
                print("FRAME_ERR", repr(frame.name), exc)
        await page.screenshot(path="run_artifacts/inspect_finish_unit5.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
