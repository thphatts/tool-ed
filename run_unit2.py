import asyncio
import os
import sys
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in, CHROMIUM_ARGS, STORAGE_STATE, URL

OUTPUT_DIR = "run_artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

class Unit2AutonomousAgent:
    def __init__(self, page):
        self.page = page

    async def dismiss_all_popups(self):
        """Dismiss any confirmation / reminder popups across all frames"""
        for frame in self.page.frames:
            try:
                ok_btn = await frame.query_selector("a#btnOk, #btnOk, input#btnOk, button#btnOk")
                if ok_btn and await ok_btn.is_visible():
                    print(f"[*] [Popup] Clicking OK/Continue in frame '{frame.name}'...")
                    await ok_btn.click()
                    await self.page.wait_for_timeout(800)
            except Exception:
                pass

        try:
            modal_btn = await self.page.query_selector(".modal-dialog button, button:has-text('Login on This Device'), button:has-text('Continue')")
            if modal_btn and await modal_btn.is_visible():
                await modal_btn.click()
                await self.page.wait_for_timeout(800)
        except Exception:
            pass

    async def complete_explore_step(self):
        """Simulate media playback to satisfy Explore requirements"""
        try:
            await self.page.evaluate('''() => {
                const media = document.querySelectorAll('video, audio');
                media.forEach(m => {
                    m.muted = true;
                    m.play().catch(() => {});
                    m.currentTime = Math.max(0, (m.duration || 60) - 0.5);
                    m.dispatchEvent(new Event('ended'));
                });
            }''')
        except Exception:
            pass

    async def solve_current_task(self):
        """Solve whatever question is currently active"""
        await self.dismiss_all_popups()

        # Check step type
        step_title = await self.page.evaluate('''() => {
            const el = document.querySelectorAll('.learning__dropDownListTitleW')[1];
            return el ? el.innerText : '';
        }''')

        if "Explore" in step_title:
            print("[*] Active step: Explore -> playing media.")
            await self.complete_explore_step()
            return "explore"

        # 1. Check Multiple Choice with correct marker
        correct_labels = await self.page.query_selector_all(".multiRadio.correct label, .selection--v + .multiRadio label, .multiRadio.selection--v label")
        if correct_labels:
            for label in correct_labels:
                if await label.is_visible():
                    text = (await label.inner_text()).strip()
                    print(f"[*] [MCQ] Selecting correct answer: '{text}'")
                    await label.click()
                    await self.page.wait_for_timeout(500)
                    await self.check_answer()
                    return "mcq_exact"

        # 2. Check general Multiple Choice options (if correct not pre-marked)
        radio_labels = await self.page.query_selector_all(".multiRadio label, input[type='radio']")
        if radio_labels:
            for r in radio_labels:
                if await r.is_visible():
                    print("[*] [MCQ] Selecting option...")
                    await r.click()
                    await self.page.wait_for_timeout(500)
                    await self.check_answer()
                    return "mcq_general"

        # 3. Check Drag-and-Drop matching (True/False or Categorization)
        zone_true = self.page.locator("[dg_name='0'], .dndZone:first-child").first
        zone_false = self.page.locator("[dg_name='1'], .dndZone:nth-child(2)").first
        draggable_items = await self.page.query_selector_all(".dnditem.draggable, .draggable")
        if draggable_items and await zone_true.count() > 0:
            print(f"[*] [DND] Found {len(draggable_items)} draggable items. Sorting into drop zones...")
            for idx, item in enumerate(draggable_items):
                try:
                    if await item.is_visible():
                        target_zone = zone_true if (idx % 2 == 0) else zone_false
                        await item.drag_to(target_zone)
                        await self.page.wait_for_timeout(300)
                except Exception:
                    pass
            await self.check_answer()
            return "dnd_solved"

        # 4. Check 'See Answer' button if available to auto-reveal
        see_answer_btn = await self.page.query_selector("#SeeAnswer")
        if see_answer_btn and await see_answer_btn.is_visible():
            print("[*] Clicking See Answer to reveal...")
            await see_answer_btn.click()
            await self.page.wait_for_timeout(500)
            return "see_answer"

        # 5. Check Test Start button
        start_test_btn = await self.page.query_selector(".learning__btnStartTest, button:has-text('Start Test'), a:has-text('Start Test'), .startTest")
        if start_test_btn and await start_test_btn.is_visible():
            print("[*] Clicking 'Start Test'...")
            await start_test_btn.click()
            await self.page.wait_for_timeout(2000)
            return "test_started"

        return "none"

    async def check_answer(self):
        """Click the Check Answer checkmark icon"""
        btn = await self.page.query_selector("#CheckAnswer, .practiceTools #CheckAnswer")
        if btn and await btn.is_visible():
            await btn.click()
            await self.page.wait_for_timeout(800)

    async def click_next(self):
        """Advance to next task or step"""
        # First check Submit Test if in test mode
        submit_test = await self.page.query_selector(".learning__submitTest, a:has-text('Submit Test'), button:has-text('Submit')")
        if submit_test and await submit_test.is_visible():
            print("[*] Submitting test...")
            await submit_test.click()
            await self.page.wait_for_timeout(2000)
            await self.dismiss_all_popups()

        # Regular Next item
        next_btn = await self.page.query_selector("#learning__nextItem, .learning__nextItemLink")
        if next_btn and await next_btn.is_visible():
            print("[*] Advancing: Next ->")
            await next_btn.click()
            await self.page.wait_for_timeout(1500)
            await self.dismiss_all_popups()
            return True
        return False

async def run_agent(headless=False):
    print("=" * 60)
    print("    ENGLISH DISCOVERIES - UNIT 2: ACCIDENTS AGENT")
    print(f"    Mode: {'Headless' if headless else 'Headed (Live Browser)'}")
    print("=" * 60)

    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=headless)
        agent = Unit2AutonomousAgent(page)

        print("[*] Ensuring we are in the Learning Area for Unit 2...")
        if "#/home" in page.url:
            continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=20000)
            await continue_btn.click()
            await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
            await page.wait_for_timeout(2000)

        step_count = 0
        max_steps = 60 # Safe upper bound for all 5 lessons in Unit 2

        while step_count < max_steps:
            step_count += 1
            await page.wait_for_timeout(1500)
            await agent.dismiss_all_popups()

            # Read navigation state
            status = await page.evaluate('''() => {
                const dd = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
                const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
                return { lesson: dd[0] || '', step: dd[1] || '', pager };
            }''')

            print(f"\n[Step {step_count}] {status['lesson']} | {status['step']} | Task {status['pager']}")

            # Save progress screenshot
            await page.screenshot(path=f"{OUTPUT_DIR}/agent_step_{step_count}.png")

            # Solve
            action = await agent.solve_current_task()
            print(f"    Action performed: {action}")

            # Advance
            advanced = await agent.click_next()
            if not advanced:
                print("[*] Next button reached terminal state. Checking if Unit 2 is completed...")
                await page.wait_for_timeout(3000)
                break

        print("\n" + "=" * 60)
        print("[*] Agent run finished! Returning to Dashboard to verify score...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{OUTPUT_DIR}/final_unit2_completion.png")
        print(f"[*] Final screenshot saved to {OUTPUT_DIR}/final_unit2_completion.png")
        await browser.close()

if __name__ == "__main__":
    headless_mode = "--headed" not in sys.argv
    asyncio.run(run_agent(headless=headless_mode))
