import asyncio
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in


async def main():
    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=True)
        slides = page.locator(".BSslide")
        print("SLIDE_COUNT", await slides.count())
        for i in range(await slides.count()):
            slide = slides.nth(i)
            print("SLIDE", i, await slide.get_attribute("class"), (await slide.inner_text())[:1000])
        for direction in ("left", "right"):
            control = page.locator(f".home__courseCarouselSec .{direction}.carousel-control")
            print("CONTROL", direction, await control.count(), await control.is_visible() if await control.count() else False)
        left = page.locator(".home__courseCarouselSec .left.carousel-control")
        if await left.count() and await left.is_visible():
            await left.click()
            await page.wait_for_timeout(2500)
            print("AFTER_LEFT", await page.locator(".home__courseCarouselSec .carouselPathCourseName:visible").all_inner_texts())
            print("AFTER_LEFT_BODY", (await page.locator(".home__courseCarouselSec").inner_text())[:1000])
            units = page.locator(".home__unitW")
            print("UNIT_COUNT", await units.count())
            for i in range(await units.count()):
                unit = units.nth(i)
                print("UNIT", i, await unit.get_attribute("id"), await unit.get_attribute("class"), (await unit.inner_text())[:1600])
                print("UNIT_LINKS", i, await unit.locator("a").evaluate_all(
                    "els => els.map(e => ({text:(e.innerText||'').trim(), cls:e.className, title:e.title, click:e.getAttribute('ng-click') || e.getAttribute('data-ng-click')}))"
                ))
            unit3 = units.nth(2)
            await unit3.locator(".home__units_lessonsTabHandle").evaluate("el => el.click()")
            await page.wait_for_timeout(1800)
            print("UNIT3_OPEN", await unit3.get_attribute("class"), (await unit3.inner_text())[:4000])
            print("UNIT3_OPEN_LINKS", await unit3.locator("a").evaluate_all(
                "els => els.map(e => ({text:(e.innerText||'').trim(), cls:e.className, title:e.title, href:e.getAttribute('href'), click:e.getAttribute('ng-click') || e.getAttribute('data-ng-click')}))"
            ))
            await page.screenshot(path="run_artifacts/current_courses_after_left.png")
        print("CONTROLS", await page.locator("a:visible, button:visible").evaluate_all(
            "els => els.map(e => ({text:(e.innerText||'').trim(), cls:e.className, title:e.title, aria:e.getAttribute('aria-label')})).filter(x => x.text || x.title || x.aria)"
        ))
        await page.screenshot(path="run_artifacts/current_courses.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
