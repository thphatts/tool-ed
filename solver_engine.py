import asyncio
import os
from playwright.async_api import async_playwright
from settings import CHROMIUM_ARGS, STORAGE_STATE

class EngDisSolver:
    def __init__(self, page):
        self.page = page

    async def dismiss_popups_and_reminders(self):
        """Handle any iframe popups (Reminder, confirmation, etc.)"""
        for f in self.page.frames:
            try:
                # Reminder popup Continue button
                btn_ok = await f.query_selector("a#btnOk, #btnOk, input#btnOk")
                if btn_ok and await btn_ok.is_visible():
                    print(f"[*] Found Reminder modal in frame {f.name}, clicking Continue (a#btnOk)...")
                    await btn_ok.click()
                    await self.page.wait_for_timeout(1000)
            except Exception:
                pass

        # Main page modals
        try:
            modal_btn = await self.page.query_selector(".modal-dialog button, button:has-text('Login on This Device')")
            if modal_btn and await modal_btn.is_visible():
                await modal_btn.click()
                await self.page.wait_for_timeout(1000)
        except Exception:
            pass

    async def handle_explore_step(self):
        """Simulate video/audio listening for Explore step"""
        try:
            await self.page.evaluate('''() => {
                const v = document.querySelector('video, audio');
                if (v) {
                    v.muted = true;
                    v.play();
                    v.currentTime = Math.max(0, (v.duration || 60) - 0.5);
                    v.dispatchEvent(new Event('ended'));
                }
            }''')
        except Exception:
            pass

    async def solve_current_task(self):
        """Inspect and solve current task on screen"""
        await self.dismiss_popups_and_reminders()

        # Check if this is Explore (no questions, just media or text)
        is_explore = await self.page.evaluate('''() => {
            const stepDropdown = document.querySelectorAll('.learning__dropDownListTitleW')[1];
            return stepDropdown && stepDropdown.innerText.includes('Explore');
        }''')
        if is_explore:
            print("[*] Current step is Explore. Triggering media playback...")
            await self.handle_explore_step()
            await self.page.wait_for_timeout(1000)
            return "explore_done"

        # Check for multiple choice questions (MCQ)
        mcq_solved = await self.solve_mcq()
        if mcq_solved:
            return "mcq_solved"

        # Check for fill-in-the-blank questions
        blanks_solved = await self.solve_blanks()
        if blanks_solved:
            return "blanks_solved"

        # Check for matching / drag-and-drop
        matching_solved = await self.solve_matching()
        if matching_solved:
            return "matching_solved"

        # If 'See Answer' is available, we can click it to reveal and learn answers
        see_answer_btn = await self.page.query_selector("#SeeAnswer")
        if see_answer_btn and await see_answer_btn.is_visible():
            print("[*] Clicking See Answer to reveal correct state...")
            await see_answer_btn.click()
            await self.page.wait_for_timeout(1000)
            return "see_answer_used"

        print("[!] No specific solver matched current screen.")
        return "unhandled"

    async def solve_mcq(self):
        """Solve Multiple Choice Question"""
        # Look for the correct option marked in DOM
        correct_labels = await self.page.query_selector_all(".multiRadio.correct label, .selection--v + .multiRadio label, .multiRadio.selection--v label")
        if correct_labels:
            for label in correct_labels:
                if await label.is_visible():
                    txt = (await label.inner_text()).strip()
                    print(f"[*] Identified correct MCQ option from DOM: '{txt}', clicking...")
                    await label.click()
                    await self.page.wait_for_timeout(500)
                    await self.click_check_answer()
                    return True

        # Never submit a guessed option. This legacy solver has no lesson
        # context/reasoner, so selecting the first radio would silently record
        # a wrong answer whenever the correct marker is absent (notably in Test).
        all_radios = await self.page.query_selector_all(".multiRadio label, input[type='radio']")
        if all_radios:
            visible_count = sum([await r.is_visible() for r in all_radios])
            print(f"[!] Found {visible_count} radio options but no verified correct marker; skipping MCQ.")
        return False

    async def solve_blanks(self):
        """Solve Fill-in-the-blanks"""
        inputs = await self.page.query_selector_all("input.fillInBlank, input[type='text'].blank, .gapFill input")
        if not inputs:
            return False
        print(f"[*] Found {len(inputs)} blank input fields.")
        # Check if answers are embedded in data attributes
        for inp in inputs:
            correct_val = await inp.get_attribute("data-answer") or await inp.get_attribute("ng-reflect-model")
            if correct_val:
                await inp.fill(correct_val)
        await self.click_check_answer()
        return True

    async def solve_matching(self):
        """Solve drag-and-drop or matching"""
        drag_items = await self.page.query_selector_all(".dragItem, .draggable, .matchingSource")
        if not drag_items:
            return False
        print(f"[*] Found {len(drag_items)} matching items.")
        return True

    async def click_check_answer(self):
        """Click Check Answer if available"""
        check_btn = await self.page.query_selector("#CheckAnswer")
        if check_btn and await check_btn.is_visible():
            print("[*] Clicking #CheckAnswer...")
            await check_btn.click()
            await self.page.wait_for_timeout(1000)

    async def advance_next(self):
        """Click Next button and handle any transition modals"""
        next_btn = await self.page.query_selector("#learning__nextItem, .learning__nextItemLink")
        if next_btn and await next_btn.is_visible():
            print("[*] Clicking Next Item...")
            await next_btn.click()
            await self.page.wait_for_timeout(2000)
            await self.dismiss_popups_and_reminders()
            return True
        return False
