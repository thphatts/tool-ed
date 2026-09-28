import asyncio
import sys
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        unit_number = int(sys.argv[1]) if len(sys.argv) > 1 else 6
        card = page.locator(f"#home__unitIW_{unit_number - 1}")
        wrap = card.locator("xpath=ancestor::div[contains(@class,'home__unitW')][1]")
        if "--no-click" not in sys.argv:
            await card.click(force=True)
            await page.wait_for_timeout(1200)
        else:
            await card.hover()
            await wrap.locator(".home__units_lessonsTabHandle").click(force=True)
            await page.wait_for_timeout(1200)
        print("URL", page.url)
        print("TEXT", await wrap.inner_text())
        print("LINKS", await wrap.locator("a").all_inner_texts())
        print("TITLES", await wrap.locator("[title]").evaluate_all("els => els.map(e => [e.className, e.title, !!e.offsetParent])"))
        print("HTML", (await wrap.inner_html())[:12000])
        await page.screenshot(path="run_artifacts/inspect_unit6_dashboard.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
