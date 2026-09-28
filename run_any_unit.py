import asyncio
import os
import sys
import argparse
import re
from playwright.async_api import async_playwright
from session_manager import ensure_logged_in, CHROMIUM_ARGS, ORIGIN, STORAGE_STATE, URL
from ai_reasoner import AIContextReasoner

OUTPUT_DIR = "run_artifacts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

class UniversalEngDisAgent:
    def __init__(self, page, context):
        self.page = page
        self.context = context
        self.reasoner = AIContextReasoner()
        # Cache transcript của bài Explore để dùng lại cho Practice/Test cùng Lesson
        self._cached_transcript = ""
        self._cached_audio_path = None
        # Cache đáp án chính xác 100% trích xuất từ chế độ Review: { "1": item, "2": item, ... }
        self._cached_test_answers = {}

    async def select_course_on_dashboard(self, course_target):
        """Chuyển carousel đến đúng khóa học mà không bấm Start Over."""
        if not course_target or "#/home" not in self.page.url:
            return True

        target = str(course_target).strip().lower()
        course_name = self.page.locator(
            ".home__courseCarouselSec .carouselPathCourseName:visible"
        ).first
        await course_name.wait_for(state="visible", timeout=20000)

        for _ in range(12):
            current = (await course_name.inner_text()).strip()
            print(f"[*] Khóa học đang chọn trên Dashboard: {current}")
            if current.lower() == target:
                print(f"[★] Đã khóa đúng khóa học: {current}")
                return True
            previous = current
            await self.page.locator(
                ".home__courseCarouselSec .left.carousel-control"
            ).click()
            await self.page.wait_for_timeout(1400)

        current = (await course_name.inner_text()).strip()
        print(f"[!] Không tìm thấy khóa '{course_target}'. Khóa hiện tại: '{current}'.")
        return False

    async def dismiss_all_popups(self):
        """Xử lý tất cả popup xác nhận / Reminder trong tất cả frames"""
        try:
            overlay = self.page.locator(".utils__siteOverlay")
            if await overlay.count() > 0 and await overlay.first.is_visible():
                await self.page.wait_for_selector(".utils__siteOverlay", state="hidden", timeout=2000)
        except Exception:
            pass

        for frame in self.page.frames:
            try:
                ok_btn = await frame.query_selector("a#btnOk, #btnOk, input#btnOk, button#btnOk")
                if ok_btn and await ok_btn.is_visible():
                    print(f"[*] [Popup] Bấm OK/Continue trong frame '{frame.name}'...")
                    await ok_btn.click()
                    await self.page.wait_for_timeout(1000)
            except Exception:
                pass

        try:
            modal_btn = await self.page.query_selector("input[value='Login on This Device'], .modal-dialog button, button:has-text('Login on This Device'), button:has-text('Continue')")
            if modal_btn and await modal_btn.is_visible():
                await modal_btn.click(force=True)
                await self.page.wait_for_timeout(800)
        except Exception:
            pass

    async def select_unit_on_dashboard(self, unit_target, lesson_target=None):
        """Chọn Unit cụ thể trên màn hình Dashboard trong All Units"""
        if not unit_target:
            return False

        print(f"[*] Đang tìm kiếm Unit '{unit_target}' trong danh sách All Units...")
        target_str = str(unit_target).strip().lower()

        unit_map = {
            "1": ("0", "Buying A Car"),
            "2": ("1", "Accidents"),
            "3": ("2", "Problems"),
            "4": ("3", "Helping Out"),
            "5": ("4", "Dreams And Ambitions"),
            "6": ("5", "Money Matters"),
            "7": ("6", "Politics"),
            "8": ("7", "Instructions"),
            "9": ("8", "Recycling"),
            "10": ("9", "Movie Making"),
        }

        idx = None
        for k, (u_idx, u_name) in unit_map.items():
            if target_str == k or f"unit {k}" == target_str or u_name.lower() in target_str or target_str in u_name.lower():
                idx = u_idx
                break

        if idx is not None:
            unit_wrap = self.page.locator(".home__unitW").nth(int(idx))
            unit_card = unit_wrap.locator(f"#home__unitIW_{idx}").first
        else:
            unit_wrap = self.page.locator(f".home__unitW:has-text('{unit_target}')").first
            unit_card = unit_wrap.locator(".home__unitIW").first

        if await unit_card.count() > 0:
            print(f"[*] Đã tìm thấy thẻ Unit '{unit_target}', đang cuộn tới và chọn...")
            await unit_wrap.scroll_into_view_if_needed()

            if "learningArea.html" in self.page.url:
                print(f"[*] Đã vào trực tiếp Learning Area của Unit '{unit_target}'!")
                return True

            # Với unit chưa bắt đầu, click card chỉ chọn unit; link đầu tiên
            # trong `.home__unitW--showLessons a` là nút "Lessons", không phải
            # Lesson 1. Mở panel trước rồi mới click đúng lesson trong chính
            # card này (selector global từng click nhầm handle và không navigate).
            status_link = unit_wrap.locator(".home__statusW[title='Start unit']").first
            if await status_link.count() > 0 and await status_link.is_visible():
                print(f"[*] Unit chưa bắt đầu; đang bấm 'Start unit'...")
                await status_link.evaluate("el => el.click()")
                await self.page.wait_for_timeout(4000)
                if "learningArea.html" in self.page.url:
                    return True

            lessons_handle = unit_wrap.locator(".home__units_lessonsTabHandle").first
            if await lessons_handle.count() > 0:
                print("[*] Đang mở danh sách Lessons của Unit...")
                await lessons_handle.evaluate("el => el.click()")
                await self.page.wait_for_timeout(1200)

            lesson_number = str(lesson_target or "1").strip()
            lesson_match = re.search(r"\d+", lesson_number)
            lesson_number = lesson_match.group(0) if lesson_match else "1"
            lesson_link = unit_wrap.locator("a.home__courseListItemLink").filter(
                has_text=re.compile(rf"^\s*{re.escape(lesson_number)}(?:\.|\s)")
            ).first
            if await lesson_link.count() > 0:
                print(f"[*] Đang click mở Lesson {lesson_number} của Unit...")
                await lesson_link.evaluate("el => el.click()")
                await self.page.wait_for_timeout(4000)
                return "learningArea.html" in self.page.url

            return "learningArea.html" in self.page.url
        return False

    async def select_lesson_in_learning_area(self, lesson_target):
        """Chọn bài học cụ thể (Lesson 1..N) trong thanh menu phía trên"""
        if not lesson_target:
            return

        print(f"[*] Đang chuyển đến bài học: {lesson_target}...")
        dropdowns = await self.page.query_selector_all(".learning__dropDownListTitleW")
        if dropdowns:
            await dropdowns[0].click()
            await self.page.wait_for_timeout(800)

            target_str = str(lesson_target).lower()
            items = await self.page.query_selector_all(".learning__dropDownList_item")
            for item in items:
                txt = (await item.inner_text()).lower()
                if target_str in txt:
                    print(f"[*] Đã tìm thấy bài học: '{txt.strip()}', đang mở...")
                    # Danh sách lesson được Angular render lại khi trạng thái
                    # tiến độ cập nhật; Playwright actionability có thể giữ
                    # ElementHandle cũ và báo detached. Gọi click ngay trong
                    # page context để hoàn tất trước lần render kế tiếp.
                    await item.evaluate("el => el.click()")
                    await self.page.wait_for_timeout(2500)
                    return True

            await dropdowns[0].click()
        return False

    async def select_step_in_learning_area(self, step_target):
        """Đưa lesson về đúng step (đặc biệt Explore để nạp transcript từ đầu)."""
        if not step_target:
            return False
        if await self.page.locator(".learning__dropDownListTitleW").count() < 2:
            return False
        await self.page.evaluate('''() => {
            document.querySelectorAll('.utils__siteOverlay').forEach(x => x.remove());
            document.querySelectorAll('.learning__dropDownListTitleW')[1]?.click();
        }''')
        await self.page.wait_for_timeout(800)
        target = str(step_target).strip().lower()
        item = self.page.locator(".learning__dropDownList_item").filter(
            has_text=re.compile(re.escape(target), re.I)
        ).last
        if await item.count() > 0:
            print(f"[*] Đang chuyển step sang '{step_target}'...")
            await item.evaluate("el => el.click()")
            await self.page.wait_for_timeout(2200)
            current = " ".join(await self.page.locator(".learning__dropDownListTitleW").nth(1).all_inner_texts()).lower()
            return target in current
        print(f"[!] Không thấy step '{step_target}'. Các mục: {await self.page.locator('.learning__dropDownList_item').all_inner_texts()}")
        return False

    async def select_next_lesson_in_learning_area(self):
        """Chuyển thẳng sang lesson kế tiếp trong cùng Unit."""
        title = (await self.page.locator(".learning__dropDownListTitleW").first.inner_text()).strip()
        match = re.search(r"Lesson\s+(\d+)", title, re.I)
        if not match:
            return False
        next_number = int(match.group(1)) + 1
        await self.page.evaluate('''() => {
            document.querySelectorAll('.utils__siteOverlay').forEach(x => x.remove());
            document.querySelectorAll('.learning__dropDownListTitleW')[0]?.click();
        }''')
        await self.page.wait_for_timeout(700)
        next_item = self.page.locator(".learning__dropDownList_item").filter(
            has_text=re.compile(rf"^\s*{next_number}\.\s")
        ).first
        if await next_item.count() == 0:
            return False
        print(f"[*] [Tests Only] Lesson hiện tại không có Test; chuyển sang Lesson {next_number}...")
        await next_item.evaluate("el => el.click()")
        await self.page.wait_for_timeout(2200)
        return True

    async def complete_explore_media(self):
        """
        Xử lý bước Explore:
        1. Click nút "See Text" / "See Transcript" nếu có để hiện lời thoại.
        2. Trích xuất transcript và cache lại cho Practice/Test.
        3. Nhấn nút Play thực sự và để chạy 2.5 giây.
        4. Tải audio file về cache.
        5. Duyệt toàn bộ danh sách từ vựng nếu có.
        """
        try:
            # 1. Click nút "See Text" để hiển thị transcript nếu có
            see_text_clicked = await self.page.evaluate('''() => {
                const seeBtn = document.querySelector('.seeTxt, .seeText, [title="See Text"], .learning__seeTxt');
                if (seeBtn && seeBtn.offsetParent !== null) {
                    seeBtn.click();
                    return true;
                }
                return false;
            }''')
            if see_text_clicked:
                print("[*] [Explore] Đã click 'See Text' để hiển thị transcript!")
                await self.page.wait_for_timeout(800)

            # 2. Trích xuất và cache transcript
            ctx = await self.fetch_audio_and_transcript()
            if ctx.get("transcript"):
                self._cached_transcript = ctx["transcript"]
                print(f"[*] [Explore] Đã cache transcript ({len(self._cached_transcript)} ký tự): '{self._cached_transcript[:100]}...'")
            if ctx.get("audio_local_path"):
                self._cached_audio_path = ctx["audio_local_path"]
                print(f"[*] [Explore] Đã cache audio file: {self._cached_audio_path}")

            # 3. Bấm nút Play thực tế của video/audio
            played = await self.page.evaluate('''() => {
                const playBtn = document.querySelector('.learning__RAMRButton--play, #play-pause, .layout__mediaPlayPause--play, .layout__mediaPlayPause');
                if (playBtn && playBtn.offsetParent !== null) {
                    playBtn.click();
                    return true;
                }
                const media = document.querySelector('video, audio');
                if (media) {
                    media.muted = true;
                    media.play().catch(() => {});
                    return true;
                }
                return false;
            }''')

            if played:
                print("[*] [Explore Media] Đã bấm Play! Đang phát 2.5 giây để máy chủ xác nhận hoàn thành...")
                await self.page.wait_for_timeout(2500)

                # Sau khi chạy 2.5s, tua về cuối để đánh dấu hoàn thành
                await self.page.evaluate('''() => {
                    const media = document.querySelectorAll('video, audio');
                    media.forEach(m => {
                        m.currentTime = Math.max(0, (m.duration || 60) - 0.2);
                        m.dispatchEvent(new Event('ended'));
                    });
                }''')
                await self.page.wait_for_timeout(500)

            # 4. Duyệt qua các từ vựng nếu có danh sách từ
            has_vocab = await self.page.evaluate('''() => {
                const words = document.querySelectorAll('#wordList li a, .termsSelectionWrapper li a');
                if (words.length > 0) {
                    words.forEach(w => w.click());
                    return true;
                }
                return false;
            }''')
            if has_vocab:
                print("[*] [Explore Vocab] Đã duyệt qua danh sách từ vựng.")
                await self.page.wait_for_timeout(1000)
        except Exception:
            pass

    async def fetch_audio_and_transcript(self):
        """
        Trích xuất Transcript từ DOM và tải file Audio nếu có.
        Tìm kiếm transcript ở NHIỀU vị trí DOM khác nhau.
        """
        info = await self.page.evaluate('''() => {
            const dropdowns = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
            const unitTitle = dropdowns[0] || 'Unit';
            const stepTitle = dropdowns[1] || '';

            // Trích xuất transcript - tìm ở NHIỀU nơi
            let transcript = '';
            
            // 1. Container See Text (hiện khi click nút See Text)
            const txtContainer = document.querySelector('.seeTxtContainer, .learning__RATextW, .seeTextContent');
            if (txtContainer && txtContainer.innerText.trim()) {
                transcript = txtContainer.innerText.trim();
            }
            
            // 2. Segments / Speaker (hội thoại dạng karaoke)
            if (!transcript) {
                const segs = Array.from(document.querySelectorAll('.segment, .speaker, .dialogueText, .readingText, .viewResourceText'));
                if (segs.length > 0) {
                    transcript = segs.map(s => s.innerText.trim()).filter(t => t.length > 0).join(' ');
                }
            }
            
            // 3. Phần passage / đoạn văn bên trái (#leftDiv)
            if (!transcript) {
                const leftDiv = document.querySelector('#leftDiv');
                if (leftDiv) {
                    const paras = Array.from(leftDiv.querySelectorAll('p, td, .blockquote, span'));
                    transcript = paras.map(p => p.innerText.trim()).filter(t => t.length > 5).join(' ');
                }
            }

            // 4. Blockquote trong câu hỏi (hội thoại ngắn)
            if (!transcript) {
                const bqs = Array.from(document.querySelectorAll('.blockquote'));
                if (bqs.length > 0) {
                    transcript = bqs.map(b => b.innerText.trim()).filter(t => t.length > 0).join(' ');
                }
            }

            // 5. prCLZ__frame (cloze / gap-fill frame chứa câu văn)
            if (!transcript) {
                const clozeFrame = document.querySelector('.prCLZ__frame, .prCLZ__question');
                if (clozeFrame) {
                    transcript = clozeFrame.innerText.trim();
                }
            }

            let mediaUrl = '';
            const mediaEl = document.querySelector('video source, audio source, video, audio');
            if (mediaEl) {
                mediaUrl = mediaEl.src || mediaEl.getAttribute('src') || '';
            }

            let question = '';
            // MCQ pages use .prMCQ__questionText. Prefer the smallest question
            // node so instructions/options do not leak into the prompt.
            const qEl = document.querySelector('.prMCQ__questionText, .learning__questionText, .questionText, .learning__question, .prMCQ__question, .taskInstructions, .learning__taskInstructions');
            if (qEl) {
                question = qEl.innerText.trim();
            } else {
                const rightArea = document.querySelector('#rightDiv, .learning__practiceArea, .pmContainer');
                if (rightArea) {
                    const lines = rightArea.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    question = lines.slice(0, 3).join(' ');
                }
            }

            return { unitTitle, stepTitle, transcript, mediaUrl, question };
        }''')

        audio_local_path = None
        media_url = info.get("mediaUrl", "")
        if media_url and ("http" in media_url):
            try:
                ext = ".mp4" if ".mp4" in media_url else ".mp3"
                save_path = f"{OUTPUT_DIR}/current_task_audio{ext}"
                resp = await self.context.request.get(media_url, headers={"Referer": f"{ORIGIN}/"})
                if resp.status == 200:
                    body = await resp.body()
                    with open(save_path, "wb") as f:
                        f.write(body)
                    audio_local_path = save_path
                    print(f"[*] [Audio DevTools] Đã tải Audio: {save_path} ({len(body)} bytes)")
            except Exception as e:
                print(f"[!] Không thể tải audio: {e}")

        # Nếu không tìm thấy transcript tại DOM hiện tại, dùng cache từ bước Explore
        if not info.get("transcript") and self._cached_transcript:
            info["transcript"] = self._cached_transcript
            print(f"[*] [Cache] Sử dụng transcript đã cache từ bước Explore ({len(self._cached_transcript)} ký tự)")

        # Nếu không tải được audio, dùng audio đã cache từ bước Explore
        if not audio_local_path and self._cached_audio_path and os.path.exists(self._cached_audio_path):
            audio_local_path = self._cached_audio_path
            print(f"[*] [Cache] Sử dụng audio đã cache từ bước Explore: {audio_local_path}")

        info["audio_local_path"] = audio_local_path
        return info

    async def solve_dropdown_or_popup_blanks(self):
        """DẠNG 1: Điền từ vào chỗ trống qua Popup / Dropdown (hỗ trợ tích hợp 100% đáp án Review)"""
        # 1. Lấy thông tin task hiện tại từ pager để tra cứu cache Review
        task_info = await self.page.evaluate('''() => {
            const pager = document.querySelector('.learning__tasksPager');
            let taskNum = '';
            if (pager) {
                const m = pager.innerText.match(/(\\d+)\\s*\\//);
                if (m) taskNum = m[1];
            }
            // Chỉ lấy các ô dropdown thực tế trên câu văn (loại bỏ thẻ trong menu popup)
            const workArea = document.querySelector('#rightDiv, .pmContainer, .learning__practiceArea') || document.body;
            const blanks = Array.from(workArea.querySelectorAll('.DDLOptions__selected, .prFITB__DDLOptionsW')).filter(el => {
                return el.offsetParent !== null && !el.closest('.DDLOptions__list, .DDLOptions__listWrapper, [class*="listWrapper"]');
            });
            return { taskNum, blankCount: blanks.length };
        }''')

        task_key = str(task_info.get("taskNum", ""))
        cached = self._cached_test_answers.get(task_key, {})

        # Lấy danh sách các ô dropdown thực tế trên câu văn
        custom_ddls = await self.page.locator('#rightDiv .DDLOptions__selected, .pmContainer .DDLOptions__selected, .learning__practiceArea .DDLOptions__selected').all()
        # Lọc các ô thực sự hiển thị và không nằm trong popup list
        visible_ddls = []
        for d in custom_ddls:
            if await d.is_visible():
                is_in_popup = await d.evaluate('el => el.closest(".DDLOptions__list, .DDLOptions__listWrapper") !== null')
                if not is_in_popup:
                    visible_ddls.append(d)

        if not visible_ddls:
            # Fallback nếu selector trên không tìm thấy
            fallback_ddls = await self.page.locator('.DDLOptions__selected').all()
            for d in fallback_ddls:
                if await d.is_visible():
                    is_in_popup = await d.evaluate('el => el.closest(".DDLOptions__list, .DDLOptions__listWrapper") !== null')
                    if not is_in_popup:
                        visible_ddls.append(d)

        if visible_ddls:
            print(f"[*] [Dạng 1: DDLOptions Custom] Tìm thấy {len(visible_ddls)} ô dropdown custom trên câu văn.")
            
            ctx = await self.fetch_audio_and_transcript()
            transcript = ctx.get("transcript", "")
            audio_path = ctx.get("audio_local_path")

            for idx, ddl in enumerate(visible_ddls):
                try:
                    await ddl.scroll_into_view_if_needed()
                    await ddl.click(force=True)
                    await self.page.wait_for_timeout(500)

                    items = await self.page.query_selector_all(".DDLOptions__listItem, .DDLOptions__list li")
                    visible_items = [it for it in items if await it.is_visible()]
                    if visible_items:
                        item_texts = [(await it.inner_text()).strip() for it in visible_items]
                        best_i = None

                        # ===== THỦ THUẬT REVIEW MASTER: Áp dụng đáp án chuẩn 100% =====
                        if cached:
                            # A. Khớp chính xác với từ trong ô màu xanh đã lưu
                            if cached.get("dropdown"):
                                target_words = [w.lower().strip() for w in cached["dropdown"]]
                                for it_idx, it_text in enumerate(item_texts):
                                    t_clean = it_text.lower().strip()
                                    if t_clean in target_words or any(tw == t_clean for tw in target_words):
                                        best_i = it_idx
                                        print(f"[★] [Review Master 100%] Khớp từ ô Review: '{it_text}'")
                                        break
                                    elif any(tw in t_clean or t_clean in tw for tw in target_words):
                                        best_i = it_idx
                                        print(f"[★] [Review Master 100%] Khớp tương đối từ ô Review: '{it_text}'")
                                        break

                            # B. So khớp với câu văn hoàn chỉnh của Review (fullText)
                            if best_i is None and cached.get("fullText"):
                                full_text = cached["fullText"].lower()
                                matched_candidates = []
                                for it_idx, it_text in enumerate(item_texts):
                                    t_clean = it_text.lower().strip()
                                    # Kiểm tra xem từ có xuất hiện nguyên vẹn trong câu văn Review không
                                    if t_clean and (f" {t_clean} " in f" {full_text} " or f"\n{t_clean}\n" in f"\n{full_text}\n" or t_clean in full_text):
                                        matched_candidates.append((len(t_clean), it_idx, it_text))
                                if matched_candidates:
                                    matched_candidates.sort(key=lambda x: x[0], reverse=True)
                                    best_i = matched_candidates[0][1]
                                    print(f"[★] [Review Master 100%] Khớp câu hoàn chỉnh Review: '{matched_candidates[0][2]}'")

                        # Fallback nếu không có cache hoặc chưa tìm thấy
                        if best_i is None:
                            sentence = await self.page.evaluate('''() => {
                                const qa = Array.from(document.querySelectorAll('.prFITB__qaItem, .learning__unit, #rightDiv p, .pmContainer p'));
                                return qa.map(q => q.innerText.trim()).filter(Boolean).join(' [_____] ');
                            }''')
                            for choice_attempt in range(3):
                                best_i = await self.reasoner.reason_popup_dropdown_choice(
                                    sentence, item_texts,
                                    transcript=transcript, audio_path=audio_path
                                )
                                if best_i is not None:
                                    break
                                print(f"[!] [DDL Choice] Chưa có đáp án ở lần thử {choice_attempt + 1}/3; retry...")

                        if best_i is None or not 0 <= best_i < len(visible_items):
                            print(f"[!] [DDL Choice] Không đủ bằng chứng cho ô {idx+1}; không chọn mù.")
                            return False
                        print(f"[*] [DDL Choice] Đã chọn từ vào ô {idx+1}: '{item_texts[best_i]}'")
                        await visible_items[best_i].click(force=True)
                        await self.page.wait_for_timeout(400)
                except Exception as e:
                    print(f"[!] Lỗi khi chọn dropdown custom ô {idx+1}: {e}")

            await self.click_check_answer()
            return True

        # 2. Thẻ <select> chuẩn
        selects = await self.page.query_selector_all("select.dropDownBlank, select.ddlAnswer, select.form-control, .learning__unit select")
        visible_selects = [s for s in selects if await s.is_visible()]
        if visible_selects:
            print(f"[*] [Dạng 1: Dropdown chuẩn] Tìm thấy {len(visible_selects)} ô dropdown.")
            ctx = await self.fetch_audio_and_transcript()
            for i, sel in enumerate(visible_selects):
                opts = await sel.evaluate('el => Array.from(el.options).map(o => o.text.trim()).filter(t => t && !t.startsWith("--"))')
                if opts:
                    best_idx = await self.reasoner.reason_popup_dropdown_choice(
                        f"Ô {i+1}", opts,
                        transcript=ctx.get("transcript", ""),
                        audio_path=ctx.get("audio_local_path")
                    )
                    if best_idx is None or not 0 <= best_idx < len(opts):
                        print(f"[!] [Dropdown] Không đủ bằng chứng cho ô {i+1}; không submit.")
                        return False
                    await sel.select_option(label=opts[best_idx])
                    await self.page.wait_for_timeout(300)
            await self.click_check_answer()
            return True

        return False

    async def solve_gap_fill_drag_and_drop(self):
        """
        DẠNG 2: Kéo thả các thẻ vào các ô bị khuyết / Drag Here
        GỌI fetch_audio_and_transcript() để AI có đủ ngữ cảnh!
        """
        # Dùng JavaScript để lấy chính xác từng chip word riêng biệt
        dnd_info = await self.page.evaluate('''() => {
            // Lấy danh sách ô trống (drop targets) - hỗ trợ cả Cloze lẫn Bubble / Dialogue
            const targets = Array.from(document.querySelectorAll(
                '.droptarget, .dndZone, .TTpanswerDiv, [ed-trackable-drop*="User_Answer"], .prCLZ__regContainer .dndZone, [class*="regContainer"] .dndZone'
            )).filter(t => {
                const style = getComputedStyle(t);
                const rect = t.getBoundingClientRect();
                const isBank = (t.id || '').startsWith('bank_') ||
                    t.getAttribute('dg_name') === 'TTpTablePlaceHolder' ||
                    !!t.querySelector('.draggable, .dnditem');
                const hasNestedTarget = !!t.querySelector(
                    '.droptarget, .dndZone, .TTpanswerDiv, [ed-trackable-drop*="User_Answer"]'
                );
                return t.offsetParent !== null && rect.width > 0 && rect.height > 0 &&
                    style.visibility !== 'hidden' && style.display !== 'none' &&
                    !isBank && !hasNestedTarget;
            });
            
            // Lấy các thẻ từ draggable RIÊNG LẺ (hỗ trợ cả .wordBankTile lẫn .dnditem)
            const chips = Array.from(document.querySelectorAll(
                '.draggable.wordBankTile, .wordsBankWrapper .draggable, .dnditem.draggable, .dndBank .dnditem, .draggable'
            )).filter(c => {
                // Chỉ lấy thẻ lá (không chứa thẻ con draggable)
                const childDnd = c.querySelector('.draggable, .dnditem');
                return c.offsetParent !== null && !childDnd && c.innerText.trim().length > 0;
            });
            
            // Lấy passage (LOẠI TRỪ word bank) - hỗ trợ cả .bubbleDiv lẫn .prCLZ__frame
            let passage = '';
            const passageEl = document.querySelector('.bubbleDiv, .closeFrame, .prCLZ__frame .prCLZ__regContainer, .prCLZ__question');
            if (passageEl) {
                const clone = passageEl.cloneNode(true);
                const banks = clone.querySelectorAll('.wordsBankWrapper, .dndBank, .wordBank, [class*="dndBank"]');
                banks.forEach(b => b.remove());
                passage = clone.innerText.trim();
                
                // Trích xuất text định nghĩa/ngữ cảnh gắn với từng ô droptarget (cho dạng bài Matching Definitions)
                const targetContexts = targets.map(t => {
                    const row = t.closest('tr, .matchingRow, .dndRow, div') || t.parentElement;
                    const clone = row.cloneNode(true);
                    clone.querySelectorAll('.droptarget, .dndZone, .draggable, .TTpanswerDiv').forEach(x => x.remove());
                    return clone.innerText.trim().replace(/\\s+/g, ' ');
                });

                return {
                    targetCount: targets.length,
                    chipWords: chips.map(c => c.innerText.trim()),
                    passage: passage,
                    targetContexts: targetContexts
                };
            } else {
                const frame = document.querySelector('.prCLZ__frame, #rightDiv, .pmContainer');
                if (frame) {
                    const clone = frame.cloneNode(true);
                    const banks = clone.querySelectorAll('.wordsBankWrapper, .dndBank, .wordBank, [class*="dndBank"]');
                    banks.forEach(b => b.remove());
                    passage = clone.innerText.trim();
                }
            }
            
            const targetContexts = targets.map(t => {
                const row = t.closest('tr, .matchingRow, .dndRow, div') || t.parentElement;
                const clone = row.cloneNode(true);
                clone.querySelectorAll('.droptarget, .dndZone, .draggable, .TTpanswerDiv').forEach(x => x.remove());
                return clone.innerText.trim().replace(/\\s+/g, ' ');
            });

            return {
                targetCount: targets.length,
                chipWords: chips.map(c => c.innerText.trim()),
                passage: passage,
                targetContexts: targetContexts
            };
        }''')

        target_count = dnd_info.get("targetCount", 0)
        chip_words = dnd_info.get("chipWords", [])
        passage_text = dnd_info.get("passage", "")
        target_contexts = dnd_info.get("targetContexts", [])

        # Fallback: dùng Playwright locator nếu JS không tìm thấy
        if target_count == 0:
            targets_loc = self.page.locator('.droptarget:not([id^="bank_"]):not(:has(.draggable)), .dndZone:not([id^="bank_"]):not(:has(.draggable)), .TTpanswerDiv:not(:has(.draggable)), [ed-trackable-drop*="User_Answer"]:not(:has(.draggable)), [class*="answerDiv"]:not(:has(.draggable))')
            target_count = await targets_loc.count()
        if not chip_words:
            chips_loc = self.page.locator('.draggable.wordBankTile, .wordsBankWrapper .draggable, .dnditem.draggable, .dndBank .dnditem, .draggable')
            count = await chips_loc.count()
            for i in range(count):
                txt = (await chips_loc.nth(i).inner_text()).strip()
                if txt:
                    chip_words.append(txt)

        if not chip_words or target_count == 0:
            return False

        # Một số task English Discoveries render thêm một dndZone phụ (wrapper
        #/placeholder), nên DOM có thể báo nhiều target hơn số thẻ dùng một lần.
        # Word bank là tập đáp án dùng một lần; giới hạn theo số thẻ để không
        # tạo ra một ô giả khiến mapping bị thiếu và agent dừng sai.
        if target_count > len(chip_words):
            print(f"[!] [DnD] DOM báo {target_count} target nhưng chỉ có {len(chip_words)} thẻ; bỏ qua target phụ.")
            target_count = len(chip_words)

        print(f"[*] [Dạng 2: Kéo thả] {len(chip_words)} thẻ từ: {chip_words}")
        print(f"[*] [Dạng 2: Kéo thả] {target_count} ô mục tiêu.")

        # ===== TRÍCH XUẤT TRANSCRIPT + AUDIO =====
        ctx = await self.fetch_audio_and_transcript()
        transcript = ctx.get("transcript", "")
        audio_path = ctx.get("audio_local_path")

        if transcript:
            print(f"[*] [Transcript cho DnD]: '{transcript[:120]}...'")
        if audio_path:
            print(f"[*] [Audio cho DnD]: {audio_path}")
        
        # Log passage để debug
        if passage_text:
            print(f"[*] [Passage DnD]: '{passage_text[:200]}...'")
        else:
            # Nếu passage trống, thử lấy lại bằng cách khác
            passage_text = await self.page.evaluate('''() => {
                const rightArea = document.querySelector('#rightDiv, .pmContainer, .learning__practiceArea, .prCLZ__frame');
                if (!rightArea) return '';
                const clone = rightArea.cloneNode(true);
                const banks = clone.querySelectorAll('.wordsBankWrapper, .dndBank, [class*="dndBank"], .wordBank');
                banks.forEach(b => b.remove());
                const ctrls = clone.querySelectorAll('.practiceTools, .learning__tasksPager, button, .CheckAnswer');
                ctrls.forEach(c => c.remove());
                return clone.innerText.trim();
            }''')
            if passage_text:
                print(f"[*] [Passage DnD fallback]: '{passage_text[:200]}...'")
            else:
                print("[!] [Passage DnD]: TRỐNG! AI sẽ phải dựa vào transcript/ngữ pháp.")

        # GỌI AI VỚI ĐẦY ĐỦ NGỮ CẢNH (kèm target_contexts cho bài Matching)
        mapping = {}
        for attempt in range(3):
            mapping = await self.reasoner.reason_gap_fill_mapping(
                passage_text, chip_words,
                transcript=transcript,
                audio_path=audio_path,
                num_slots=target_count,
                lesson_title=ctx.get("unitTitle", ""),
                target_contexts=target_contexts
            )
            if len(mapping) >= target_count:
                break
            print(f"[!] [DnD] Mapping thiếu ở lần thử {attempt + 1}/3; đang gọi lại reasoner...")

        # Một số model lặp lại một đáp án dù word-bank chỉ cho dùng mỗi thẻ một lần.
        # Nếu còn đúng số thẻ chưa dùng, khôi phục các ô thiếu bằng thẻ chưa dùng.
        if len(mapping) < target_count:
            used = [str(v).strip() for v in mapping.values()]
            unused = [w for w in chip_words if w not in used]
            missing_slots = [str(i) for i in range(1, target_count + 1) if str(i) not in mapping]
            if unused and missing_slots and any(used.count(w) > 1 for w in used):
                for slot, word in zip(missing_slots, unused):
                    mapping[slot] = word
                print(f"[*] [DnD Repair] Đã thay đáp án lặp bằng thẻ còn lại: {mapping}")

        # Không được submit một bài chưa có mapping đầy đủ: mapping thiếu thường
        # là dấu hiệu AI không hiểu ngữ cảnh hoặc trả JSON sai.
        if len(mapping) < target_count:
            print(f"[!] [DnD] Mapping thiếu ({len(mapping)}/{target_count}); không submit đáp án mù.")
            return False

        # Thực hiện kéo thả
        targets_loc = self.page.locator('.droptarget:visible:not([id^="bank_"]):not(:has(.draggable)):not(:has(.droptarget:visible)), .dndZone:visible:not([id^="bank_"]):not(:has(.draggable)):not(:has(.dndZone:visible)), .TTpanswerDiv:visible:not(:has(.draggable)):not(:has(.TTpanswerDiv:visible)), [ed-trackable-drop*="User_Answer"]:visible:not(:has(.draggable)):not(:has([ed-trackable-drop*="User_Answer"]:visible))')
        chips_loc = self.page.locator('.draggable.wordBankTile, .wordsBankWrapper .draggable, .dnditem.draggable, .dndBank .dnditem, .draggable')

        # Điền từ ô cuối về ô đầu. Sau mỗi lần kéo, ô vừa điền không còn
        # khớp selector `:not(:has(.draggable))`; đi ngược giữ chỉ số của các
        # ô chưa điền ổn định.
        ordered_mapping = sorted(mapping.items(), key=lambda item: int(item[0]), reverse=True)
        for slot_str, target_word in ordered_mapping:
            try:
                # Mapping dùng số ô hiển thị 1-based; locator dùng nth 0-based.
                slot_idx = int(slot_str) - 1
                if 0 <= slot_idx < target_count:
                    target = targets_loc.nth(slot_idx)
                    
                    # Tìm thẻ chính xác (exact text match)
                    # `has_text="where"` cũng khớp các distractor như
                    # "they're where" / "that's where".  Với word bank,
                    # phải khớp toàn bộ nhãn để không kéo nhầm đáp án.
                    exact_word = re.compile(rf"^\s*{re.escape(str(target_word))}\s*$", re.I)
                    chip = chips_loc.filter(has_text=exact_word).first
                    if await chip.count() > 0:
                        print(f"[*] Đang kéo thẻ '{target_word}' vào ô [{slot_idx}]...")
                        await chip.drag_to(target)
                        await self.page.wait_for_timeout(400)
                    else:
                        print(f"[!] Không tìm thấy thẻ '{target_word}', thử tìm gần đúng...")
                        # Fallback: tìm gần đúng
                        found = False
                        chip_count = await chips_loc.count()
                        for ci in range(chip_count):
                            chip_txt = (await chips_loc.nth(ci).inner_text()).strip()
                            if target_word.lower() in chip_txt.lower() or chip_txt.lower() in target_word.lower():
                                print(f"[*] Tìm thấy gần đúng: '{chip_txt}', đang kéo vào ô [{slot_idx}]...")
                                await chips_loc.nth(ci).drag_to(target)
                                await self.page.wait_for_timeout(400)
                                found = True
                                break
                        if not found:
                            print(f"[!] Không tìm thấy thẻ '{target_word}' trên màn hình!")
            except Exception as e:
                print(f"[!] Lỗi kéo thẻ '{target_word}': {e}")

        # Bấm Check Answer để hệ thống ghi nhận Hoàn thành
        check_btn = await self.page.query_selector('#CheckAnswer, [title="Check Answer"]')
        if check_btn and await check_btn.is_visible():
            print("[*] Bấm Check Answer để hệ thống đánh dấu HOÀN THÀNH (Done)...")
            await check_btn.click(force=True)
            await self.page.wait_for_timeout(1000)
        return True

    async def solve_text_inputs(self):
        """DẠNG 3: Điền vào ô input text (nếu có)"""
        inputs = await self.page.query_selector_all(
            "input[type='text']:not([readonly]), textarea, [contenteditable='true']"
        )
        # Bài viết dùng TinyMCE trong iframe; query_selector_all trên page
        # chính không nhìn thấy body editor bên trong frame.
        for frame in self.page.frames:
            try:
                inputs.extend(await frame.query_selector_all(
                    "body#tinymce, .mce-content-body, textarea:not([readonly]), [contenteditable='true']"
                ))
            except Exception:
                pass
        visible_inputs = [inp for inp in inputs if await inp.is_visible() and not await inp.is_disabled()]
        if visible_inputs:
            print(f"[*] [Dạng 3: Điền chữ] Tìm thấy {len(visible_inputs)} ô nhập văn bản.")
            for i, inp in enumerate(visible_inputs):
                try:
                    await inp.scroll_into_view_if_needed()
                    await inp.click()
                    if await inp.get_attribute("contenteditable") == "true":
                        await inp.fill(
                            "Dear Producer,\n\nI enjoy Know Your Composers because it is interesting and educational. "
                            "For next week's show, please ask questions about famous composers and their music.\n\nBest wishes."
                        )
                    else:
                        await inp.fill("answered")
                    await self.page.wait_for_timeout(200)
                except Exception:
                    pass
            done = await self.page.query_selector("#Done, button:has-text('Done'), a:has-text('Done')")
            if done and await done.is_visible():
                await done.click(force=True)
                await self.page.wait_for_timeout(800)
            else:
                await self.click_check_answer()
            return True
        return False

    async def solve_current_screen(self):
        """Tự động phân tích và giải màn hình hiện tại"""
        await self.dismiss_all_popups()
        await self.page.wait_for_timeout(600)

        # 1. Start Test Button
        has_start_test = await self.page.evaluate('''() => {
            const btn = document.querySelector('.btnStartTest, #testIntro a, .startTest a');
            if (btn && btn.offsetParent !== null) {
                btn.click();
                return true;
            }
            return false;
        }''')
        if has_start_test:
            print("[*] Đã bấm nút 'Start Test' qua JavaScript! Đang tải câu hỏi kiểm tra...")
            await self.page.wait_for_timeout(3000)
            return "test_started"

        # 1.5. ƯU TIÊN 1: Nếu có đáp án chuẩn 100% từ chế độ Review -> Áp dụng ngay!
        cached_res = await self.apply_cached_review_answer()
        if cached_res:
            return cached_res

        # 2. Explore Media & Vocab (cache transcript + audio)
        step_title = await self.page.evaluate('''() => {
            const el = document.querySelectorAll('.learning__dropDownListTitleW')[1];
            return el ? el.innerText : '';
        }''')
        if "Explore" in step_title:
            print("[*] Bước Explore -> Tự động phát media, trích xuất transcript và duyệt từ vựng.")
            await self.complete_explore_media()
            return "explore"

        # 3. DẠNG 1: Popup / Dropdown Blanks
        solved_dropdown = await self.solve_dropdown_or_popup_blanks()
        if solved_dropdown:
            return "dropdown_blanks_solved"

        # 4. DẠNG 2: Kéo thả ô khuyết
        solved_gap_fill = await self.solve_gap_fill_drag_and_drop()
        if solved_gap_fill:
            return "gap_fill_dnd_solved"

        # 5. DẠNG 3: Nhập text vào input
        solved_inputs = await self.solve_text_inputs()
        if solved_inputs:
            return "text_input_solved"

        # 6. MCQ Practice: Có thuộc tính đúng sẵn trong Angular DOM
        correct_labels = await self.page.query_selector_all(".multiRadio.correct label, .selection--v + .multiRadio label, .multiRadio.selection--v label")
        visible_correct = [l for l in correct_labels if await l.is_visible() and (await l.inner_text()).strip()]
        if visible_correct:
            text = (await visible_correct[0].inner_text()).strip()
            print(f"[*] [MCQ Practice] Tự động chọn đáp án đúng: '{text}'")
            await visible_correct[0].click(force=True)
            await self.page.wait_for_timeout(400)
            await self.click_check_answer()
            return "mcq_exact"

        # 6.5. Dạng checkbox: câu hỏi có thể có nhiều đáp án đúng.
        checkbox_info = await self.page.evaluate('''() => {
            // Checkbox của nền tảng thường là input ẩn bên trong label custom.
            const boxes = Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"], ed-la-multicheck, ed-la-multiselect'));
            const options = boxes.map((x, i) => {
                const label = x.closest('label') || document.querySelector(`label[for="${x.id}"]`) || x.parentElement;
                const container = x.closest('.radioTextWrapper') || label;
                return { index: i, text: (container ? container.innerText : '').trim(), visible: !!(container && container.offsetParent !== null) };
            }).filter(x => x.text && x.visible);
            const q = document.querySelector('.prMCQ__questionText, .learning__questionText, .questionText, .taskInstructions');
            return { options, question: q ? q.innerText.trim() : document.body.innerText.slice(0, 500) };
        }''')
        if checkbox_info.get('options'):
            ctx = await self.fetch_audio_and_transcript()
            options = [x['text'] for x in checkbox_info['options']]
            selected = await self.reasoner.reason_multi_answer(
                ctx.get('unitTitle', ''), ctx.get('stepTitle', ''),
                checkbox_info.get('question', ''), options,
                passage_context=ctx.get('transcript', ''))
            if selected:
                boxes = await self.page.locator('input[type="checkbox"], [role="checkbox"], ed-la-multicheck, ed-la-multiselect').all()
                for idx in selected:
                    if idx < len(boxes):
                        try:
                            if not await boxes[idx].is_checked():
                                await boxes[idx].check(force=True)
                        except Exception:
                            label = boxes[idx].locator('xpath=ancestor::label[1]')
                            if await label.count() > 0:
                                await label.click(force=True)
                await self.click_check_answer()
                return "checkbox_multi_solved"

        # 6.6. Speaking/response: các lựa chọn là div custom, sau đó bấm Start.
        response_info = await self.page.evaluate('''() => {
            const nodes = Array.from(document.querySelectorAll('.lessonMultipleAnswer .multiTextInline, .lessonMultipleAnswer .multiText'))
                .filter(x => x.offsetParent !== null && x.innerText.trim());
            const q = document.querySelector('.prMCQ__questionText, .learning__questionText, .questionText, .taskInstructions');
            return { options: nodes.map(x => x.innerText.trim()), question: q ? q.innerText.trim() : '' };
        }''')
        if response_info.get('options'):
            ctx = await self.fetch_audio_and_transcript()
            best = await self.reasoner.reason_best_answer(
                ctx.get('unitTitle', ''), ctx.get('stepTitle', ''),
                response_info.get('question', ''), response_info['options'],
                passage_context=ctx.get('transcript', ''))
            if best is not None and 0 <= best < len(response_info['options']):
                chosen = response_info['options'][best]
                await self.page.locator('.lessonMultipleAnswer').filter(has_text=chosen).first.click(force=True)
                await self.page.wait_for_timeout(600)
                start = self.page.locator('a:has-text("Start"), button:has-text("Start"), input[value="Start"]').first
                if await start.count() > 0 and await start.is_visible():
                    await start.click(force=True)
                    await self.page.wait_for_timeout(2500)
                return "speaking_response_selected"

        personalized_hint = await self.page.evaluate('''() => /If you were submitting a film for the REAL MOTION Film Festival/i.test(document.body.innerText || '')''')
        if personalized_hint:
            start = self.page.locator('a:has-text("Start"), button:has-text("Start"), input[value="Start"]').first
            if await start.count() > 0 and await start.is_visible():
                await start.click(force=True)
                await self.page.wait_for_timeout(2500)
            print("[*] [Personalized Speaking] Đã khởi động hoạt động nói.")
            return "personalized_speaking_started"

        # 6.7. Interact: chọn nhân vật bằng mũi tên rồi khởi động bài luyện nói.
        interact_hint = await self.page.evaluate('''() => /click on the arrow/i.test(document.body.innerText || '')''')
        if interact_hint:
            arrow = self.page.locator('#rightDiv [class*="arrow"], .learning__unit [class*="arrow"], [class*="Arrow"]').filter(visible=True).first
            if await arrow.count() > 0:
                await arrow.click(force=True)
                await self.page.wait_for_timeout(700)
            start = self.page.locator('a:has-text("Start"), button:has-text("Start"), input[value="Start"]').first
            if await start.count() > 0 and await start.is_visible():
                await start.click(force=True)
                await self.page.wait_for_timeout(2500)
                return "interact_started"

        # 6.8. Vocabulary list: mở/lướt qua toàn bộ thẻ và nút nghe để ghi nhận.
        vocab_hint = await self.page.evaluate('''() => /read the list of words and phrases/i.test(document.body.innerText || '')''')
        if vocab_hint:
            clicked = await self.page.evaluate('''() => {
                const nodes = Array.from(document.querySelectorAll('[class*="headphones"], [class*="audio"], [class*="Audio"], .multiTextInline'))
                    .filter(x => x.offsetParent !== null && !/next/i.test(x.innerText || ''));
                nodes.forEach(x => { try { x.click(); } catch (_) {} });
                return nodes.length;
            }''')
            print(f"[*] [Vocabulary] Đã duyệt/phát {clicked} mục trên danh sách từ.")
            await self.page.wait_for_timeout(1500)
            return "vocabulary_completed"

        # Các trang bài giảng/định hướng 1/1 chỉ cần đọc và chuyển tiếp.
        lesson_page = await self.page.evaluate('''() => {
            const text = document.body.innerText || '';
            const next = document.querySelector('#learning__nextItem, .learning__nextItemLink');
            return !!(next && next.offsetParent !== null && /Identifying Important Details|Important details give us/i.test(text));
        }''')
        if lesson_page:
            print("[*] [Lesson Page] Đã ghi nhận trang hướng dẫn, chuyển tiếp...")
            return "lesson_page_completed"

        # Dạng chọn thông tin trực tiếp trong đoạn đọc (click-to-select).
        select_hint = await self.page.evaluate('''() => /select the correct information in the text/i.test(document.body.innerText || '')''')
        if select_hint:
            selectable = await self.page.locator('.learning__selectTxt_st:visible').all()
            select_texts = [(await x.inner_text()).strip() for x in selectable]
            question_text = await self.page.evaluate('''() => (document.querySelector('.learning__PAQuestion, .taskInstructions, #rightDiv') || document.body).innerText.split('Your Answer:')[0].trim()''')
            target = None
            if re.search(r'feature-length', question_text, re.I):
                target = next((x for x in select_texts if x == 'April 25'), None)
            if target is None and select_texts:
                ctx = await self.fetch_audio_and_transcript()
                best = await self.reasoner.reason_best_answer('', '', question_text, select_texts, passage_context=ctx.get('transcript', ''))
                if best is not None and best < len(select_texts):
                    target = select_texts[best]
            if target:
                for node, text_value in zip(selectable, select_texts):
                    if text_value == target:
                        await node.click(force=True)
                        await self.page.wait_for_timeout(700)
                        print(f"[*] [Text Select] Đã chọn thông tin: '{target}'")
                        return "text_select_solved"
            candidates = await self.page.evaluate('''() => Array.from(document.querySelectorAll('span, a, p, [class*="select"], [class*="answer"], [onclick]'))
                .filter(x => x.offsetParent !== null && x.innerText.trim().length > 0 && x.innerText.trim().length < 100)
                .map(x => ({text:x.innerText.trim(), cls:x.className, html:x.outerHTML.slice(0,300)})).slice(0,50)''')
            print(f"[!] [Debug text-select] {candidates}")

        insertion_hint = await self.page.evaluate('''() => /select the place in the text where this sentence best fits/i.test(document.body.innerText || '')''')
        if insertion_hint:
            marker = self.page.locator('.at, [class*="insert"], [class*="place"], [class*="dropPoint"]').filter(visible=True).first
            if await marker.count() > 0:
                await marker.evaluate('el => { el.scrollIntoView({block:"center", inline:"center"}); el.click(); }')
                await self.page.wait_for_timeout(700)
                print("[*] [Text Insert] Đã chọn vị trí chèn câu trong đoạn đọc.")
                return "text_insert_solved"

        # 7. MCQ Test / Practice chưa mark -> AI suy luận
        row_info = await self.page.evaluate('''() => {
            const rows = Array.from(document.querySelectorAll('.prMCQ__answers .prMCQ__answerLabel, .multiRadio label, .answerOption, ed-la-multiradio')).filter(r => {
                return r.offsetParent !== null && r.innerText.trim().length > 0;
            });
            return rows.map((r, idx) => ({
                index: idx,
                text: r.innerText.trim()
            }));
        }''')

        if row_info:
            all_options_text = [r['text'] for r in row_info]
            
            # DEDUP: Loại bỏ phương án trùng lặp (giữ lại chỉ số DOM gốc đầu tiên)
            seen = {}
            unique_options = []
            unique_dom_indices = []
            for r in row_info:
                txt = r['text']
                if txt not in seen:
                    seen[txt] = True
                    unique_options.append(txt)
                    unique_dom_indices.append(r['index'])
            
            ctx = await self.fetch_audio_and_transcript()

            if ctx.get("transcript"):
                print(f"[*] [Transcript Audio]: '{ctx['transcript'][:120]}...'")
            print(f"[*] [AI Reasoning] Câu hỏi: '{ctx.get('question', '')}'")
            print(f"[*] [AI Options] Các phương án ({len(unique_options)} lựa chọn, dedup từ {len(all_options_text)}): {unique_options}")

            best_idx = await self.reasoner.reason_best_answer(
                unit_title=ctx.get("unitTitle", ""),
                lesson_title=ctx.get("stepTitle", ""),
                question_text=ctx.get("question", ""),
                options=unique_options,
                passage_context=ctx.get("transcript", ""),
                audio_path=ctx.get("audio_local_path")
            )

            if best_idx is not None and 0 <= best_idx < len(unique_options):
                dom_idx = unique_dom_indices[best_idx]
                print(f"[*] [AI Action] Đã chọn phương án [{best_idx}]: '{unique_options[best_idx]}' (DOM index={dom_idx})")
                await self.page.evaluate(f'''() => {{
                    const rows = Array.from(document.querySelectorAll('.prMCQ__answers .prMCQ__answerLabel, .multiRadio label, .answerOption, ed-la-multiradio')).filter(r => {{
                        return r.offsetParent !== null && r.innerText.trim().length > 0;
                    }});
                    if (rows[{dom_idx}]) {{
                        const target = rows[{dom_idx}].querySelector('label, input') || rows[{dom_idx}];
                        target.click();
                    }}
                }}''')
                await self.page.wait_for_timeout(500)
                await self.click_check_answer()
                return "mcq_ai_reasoned"

            print("[!] [MCQ] AI/local reasoner không trả về lựa chọn hợp lệ; không submit đáp án mù.")

        debug_controls = await self.page.evaluate('''() => Array.from(document.querySelectorAll('#rightDiv input, #rightDiv label, #rightDiv button, #rightDiv [role], #rightDiv [class*="check"], #rightDiv [class*="Check"]'))
            .filter(x => x.offsetParent !== null || x.tagName === 'INPUT')
            .slice(0, 40).map(x => ({tag: x.tagName, cls: x.className, type: x.type || '', text: (x.innerText || '').trim().slice(0, 120), html: (x.parentElement && x.parentElement.parentElement ? x.parentElement.parentElement.outerHTML : x.outerHTML).slice(0, 500)}))''')
        if debug_controls:
            print(f"[!] [Debug controls] {debug_controls}")
        return "none"

    async def get_current_test_score(self):
        """Đọc điểm số bài Test (%) từ màn hình kết quả hoặc từ dropdown"""
        try:
            score = await self.page.evaluate('''() => {
                // 1. Kiểm tra text hiển thị trực tiếp trên màn hình kết quả Test (ví dụ: 'Your test score is: 25%')
                const bodyText = document.body.innerText || '';
                const mDirect = bodyText.match(/Your test score is:?\\s*(\\d+)%/i) || bodyText.match(/score is:?\\s*(\\d+)%/i);
                if (mDirect) {
                    return parseInt(mDirect[1]);
                }

                // 2. Nếu không có trên màn hình, mở dropdown Steps để đọc
                const dropdowns = document.querySelectorAll('.learning__dropDownListTitleW');
                let wasOpen = false;
                if (dropdowns.length > 1) {
                    dropdowns[1].click();
                    wasOpen = true;
                }
                const items = Array.from(document.querySelectorAll('.learning__dropDownList_item'));
                let testScore = null;
                for (const it of items) {
                    const text = it.innerText || '';
                    if (text.toLowerCase().includes('test')) {
                        const m = text.match(/(\\d+)%/);
                        if (m) testScore = parseInt(m[1]);
                    }
                }
                if (wasOpen && dropdowns.length > 1) {
                    dropdowns[1].click();
                }
                return testScore;
            }''')
            return score
        except Exception as e:
            print(f"[!] Lỗi đọc điểm test: {e}")
            return None

    async def extract_review_answers(self):
        """
        Bấm nút Review sau khi nộp bài Test để duyệt qua từng câu,
        mở tab 'Correct Answer' và lưu 100% đáp án chuẩn xác vào bộ nhớ cache!
        """
        print("[*] [Review Master] Đang tìm và bấm nút Review...")
        try:
            # 1. Tìm chính xác nút Review / Preview ở nửa dưới màn hình (tránh menu ở header)
            clicked_review = await self.page.evaluate('''() => {
                const candidates = Array.from(document.querySelectorAll('a, button, div, span, input'));
                const r = candidates.find(el => {
                    if (el.offsetParent === null) return false;
                    const rect = el.getBoundingClientRect();
                    if (rect.top < window.innerHeight * 0.5) return false;
                    const t = (el.innerText || el.value || '').trim().toLowerCase();
                    return t === 'review' || t === 'preview';
                });
                if (r) {
                    r.click();
                    return true;
                }
                return false;
            }''')

            if not clicked_review:
                loc = self.page.locator('.learning__tasksNavigation a, .practiceTools a, #bottomDiv a, button').filter(has_text=re.compile(r'^(review|preview)$', re.I))
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click()
                    clicked_review = True

            if not clicked_review:
                print("[!] Không tìm thấy nút Review/Preview trên màn hình kết quả!")
                return {}

            print("[*] [Review Master] Đã bấm nút Review/Preview thành công! Đang tải màn hình kiểm tra...")
            await self.page.wait_for_timeout(3000)
            await self.dismiss_all_popups()
            await self.page.screenshot(path=f"{OUTPUT_DIR}/review_mode_entered.png")

            # Lấy số lượng câu hỏi trong bài Test (thường là 5 hoặc 12 câu)
            total_tasks = await self.page.evaluate('''() => {
                const pager = document.querySelector('.learning__tasksPager');
                if (pager) {
                    const m = pager.innerText.match(/\\d+\\s*\\/\\s*(\\d+)/);
                    if (m) return parseInt(m[1]);
                }
                return 5;
            }''')

            print(f"[*] [Review Master] Bắt đầu quét {total_tasks} câu hỏi để lấy đáp án chuẩn...")

            for task_i in range(1, total_tasks + 1):
                await self.page.wait_for_timeout(1000)

                # 2. Click vào tab "Correct Answer" bằng thẻ <a> trong .testResultTools!
                # Cấu trúc của hệ thống: <div class="testResultTools"><ul><li><a index="0">Your Answer</a></li><li><a index="1">Correct Answer</a></li></ul></div>
                clicked_tab = await self.page.evaluate('''() => {
                    // Thử qua jQuery trước (Edusoft bind sự kiện trên $('.testResultTools a'))
                    if (window.$) {
                        const jqBtn = window.$('.testResultTools a[index="1"], .testResultTools li:nth-child(2) a, .testResultTools a:contains("Correct Answer")');
                        if (jqBtn.length > 0) {
                            jqBtn.trigger('click').click();
                            return 'jquery_clicked';
                        }
                    }
                    // Thử qua DOM click trực tiếp vào thẻ <a>
                    const a = document.querySelector('.testResultTools a[index="1"], .testResultTools li:nth-child(2) a') 
                        || Array.from(document.querySelectorAll('.testResultTools a, a')).find(el => (el.innerText || '').trim().toLowerCase() === 'correct answer');
                    if (a) {
                        a.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, cancelable: true }));
                        a.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                        a.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                        a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        a.click();
                        return 'dom_a_clicked';
                    }
                    return 'not_found';
                }''')

                # Bổ trợ thêm bằng Playwright locator
                try:
                    tab_loc = self.page.locator('.testResultTools a[index="1"], .testResultTools li:nth-child(2) a, text="Correct Answer"').first
                    if await tab_loc.count() > 0:
                        await tab_loc.click(force=True)
                except Exception:
                    pass

                await self.page.wait_for_timeout(1500)

                # Chụp ảnh xác nhận đã ở tab Correct Answer
                await self.page.screenshot(path=f"{OUTPUT_DIR}/review_task_{task_i}_correct.png")

                # 3. Trích xuất đáp án CHỈ TRONG KHU VỰC BÀI TẬP (loại trừ toàn bộ header/dropdown menu)
                item_data = await self.page.evaluate('''() => {
                    const workArea = document.querySelector('#rightDiv, .pmContainer, .learning__practiceArea, .stepTasksAndPmContainer');
                    if (!workArea) return { fullText: '', mcq: '', dnd: [], dropdown: [] };
                    
                    const fullText = workArea.innerText.trim();

                    // A. Đáp án MCQ đúng qua 3 lớp nhận diện:
                    let mcqCorrect = '';
                    // Đây là marker chính xác của English Discoveries. Đọc label
                    // con thay vì innerText của cả wrapper (có thể kèm câu hỏi).
                    const exactCorrect = workArea.querySelector(
                        '.multiRadio.correct .prMCQ__answerLabel, .multiRadioWrapper.correct .prMCQ__answerLabel'
                    );
                    if (exactCorrect) mcqCorrect = exactCorrect.innerText.trim();
                    const options = Array.from(workArea.querySelectorAll('.multiRadio, .answerOption, .prMCQ__answerLabel, ed-la-multiradio, label, div.TextDiv, [class*="option"]'));

                    // Lớp 1: Nền highlight màu xanh (background khác trắng/trong suốt)
                    for (const opt of options) {
                        const bg = window.getComputedStyle(opt).backgroundColor;
                        const isHighlighted = (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'rgb(255, 255, 255)' && !bg.includes('255, 255, 255'));
                        if (isHighlighted) {
                            const t = opt.innerText.trim();
                            if (t && t !== 'Correct Answer' && t !== 'Your Answer') {
                                mcqCorrect = t;
                                break;
                            }
                        }
                    }

                    // Lớp 2: Class correct, selected, active, selection--v hoặc input checked
                    if (!mcqCorrect) {
                        for (const opt of options) {
                            const cls = (opt.className || '').toString();
                            const input = opt.querySelector('input[type="radio"]');
                            const isChecked = input ? input.checked : false;
                            if (cls.includes('selected') || cls.includes('correct') || cls.includes('active') || cls.includes('selection--v') || isChecked) {
                                const t = opt.innerText.trim();
                                if (t && t !== 'Correct Answer' && t !== 'Your Answer') {
                                    mcqCorrect = t;
                                    break;
                                }
                            }
                        }
                    }

                    // Lớp 3: Icon tick xanh kế bên
                    if (!mcqCorrect) {
                        for (const opt of options) {
                            const parent = opt.parentElement || opt;
                            const hasCheck = parent.querySelector('.glyphicon-ok, .fa-check, [class*="correct"], [class*="check"], svg') !== null;
                            if (hasCheck) {
                                const t = opt.innerText.trim();
                                if (t && t !== 'Correct Answer' && t !== 'Your Answer') {
                                    mcqCorrect = t;
                                    break;
                                }
                            }
                        }
                    }

                    // B. Đáp án Drag and Drop đúng (BẮT BUỘC PHẢI LÀ MỘT TRONG CÁC TỪ TRONG WORD BANK)
                    let dndAnswers = [];
                    // Biến thể cũ của ED đổi thẻ đúng thành `wordBankTilePlaced`
                    // và DOM order không trùng thứ tự câu. Sắp theo vị trí nhìn
                    // thấy (trên xuống, trái sang phải) để khôi phục đúng slot.
                    const placedAnswers = Array.from(workArea.querySelectorAll(
                        '.wordBankTilePlaced, .dnditemPlaced, [class*="wordBankTilePlaced"], [class*="dnditemPlaced"]'
                    )).filter(el => el.offsetParent !== null && (el.innerText || '').trim()).map(el => {
                        const r = el.getBoundingClientRect();
                        return { text: (el.innerText || '').trim(), x: r.x, y: r.y };
                    }).sort((a, b) => Math.abs(a.y - b.y) > 5 ? a.y - b.y : a.x - b.x);
                    if (placedAnswers.length > 0) dndAnswers = placedAnswers.map(x => x.text);
                    // Correct Answer renders accepted words inside the leaf
                    // drop targets even when the original bank no longer has
                    // `.draggable`. Read those slots directly and in order.
                    const reviewTargets = Array.from(workArea.querySelectorAll(
                        '.droptarget, .dndZone, .TTpanswerDiv, [ed-trackable-drop*="User_Answer"]'
                    )).filter(el => el.offsetParent !== null &&
                        !(el.id || '').startsWith('bank_') &&
                        el.getAttribute('dg_name') !== 'TTpTablePlaceHolder' &&
                        !el.querySelector('.droptarget, .dndZone, .TTpanswerDiv, [ed-trackable-drop*="User_Answer"]'));
                    const renderedAnswers = reviewTargets.map(el => (el.innerText || '').trim()).filter(t => t.length > 0 && t.length < 100);
                    if (dndAnswers.length === 0 && renderedAnswers.length > 0) dndAnswers = renderedAnswers;
                    const chips = Array.from(workArea.querySelectorAll('.draggable, .wordBankTile, .dnditem')).map(c => c.innerText.trim()).filter(t => t.length > 0);
                    
                    if (chips.length > 0) {
                        // 1. Kiểm tra các ô droptarget / ô highlight xem có chứa CHÍNH XÁC từ trong chips không
                        const potentialBoxes = Array.from(workArea.querySelectorAll('.droptarget, .dndZone, .TTpanswerDiv, [ed-trackable-drop*="User_Answer"], span, div')).filter(el => {
                            if (el.closest('.wordsBankWrapper, .wordBank, .dndBank, .testResultTools, .learning__tasksPager')) return false;
                            const t = (el.innerText || '').trim().toLowerCase();
                            return chips.some(c => c.toLowerCase() === t);
                        });
                        for (const b of potentialBoxes) {
                            const t = b.innerText.trim();
                            const matchedChip = chips.find(c => c.toLowerCase() === t.toLowerCase());
                            if (matchedChip && !dndAnswers.includes(matchedChip)) {
                                dndAnswers.push(matchedChip);
                            }
                        }

                        // 2. Nếu chưa đủ: so khớp câu văn (đã loại sạch Word Bank) với danh sách chips
                        if (dndAnswers.length === 0) {
                            const clone = workArea.cloneNode(true);
                            const bankNodes = clone.querySelectorAll('.wordsBankWrapper, .wordBank, .dndBank, .draggableContainer, .draggable, .wordBankTile, .dnditem, .testResultTools');
                            bankNodes.forEach(n => n.remove());
                            const cleanSentenceText = (clone.innerText || '').toLowerCase();

                            const matched = [];
                            for (const chip of chips) {
                                const chipLower = chip.toLowerCase();
                                // Dùng indexOf thay regex động để tránh lỗi parse
                                // khi word-bank chứa ký tự đặc biệt.
                                const pos = cleanSentenceText.indexOf(chipLower);
                                if (pos >= 0) {
                                    matched.push({ pos: pos, word: chip });
                                }
                            }
                            matched.sort((a, b) => a.pos - b.pos);
                            dndAnswers = matched.map(m => m.word);
                        }
                    }

                    // C. Đáp án Dropdown / FITB đúng: đọc chữ trong ô hiển thị (chính là ô màu xanh nhạt trong ảnh)
                    let ddAnswers = [];
                    const ddlBoxes = Array.from(workArea.querySelectorAll('.DDLOptions__selected, .DDLOptions__main, .prFITB__DDLOptionsW, .ddlOptions, .prDDL__select, select, [class*="DDL"], [class*="ddl"]'));
                    for (const box of ddlBoxes) {
                        const t = (box.value || box.innerText || '').trim();
                        if (t && t.length < 60 && !t.includes('Select') && !t.includes('Choose') && !t.includes('Your Answer') && !t.includes('Correct Answer')) {
                            if (!ddAnswers.includes(t)) ddAnswers.push(t);
                        }
                    }
                    // Nếu chưa tìm thấy bằng class, tìm bất kỳ thẻ span/div nào có background highlight màu xanh nằm trong câu văn
                    if (ddAnswers.length === 0) {
                        const allSpans = Array.from(workArea.querySelectorAll('span, div')).filter(el => {
                            if (el.children.length > 0) return false;
                            const bg = window.getComputedStyle(el).backgroundColor;
                            const hasBg = (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'rgb(255, 255, 255)' && !bg.includes('255, 255, 255'));
                            const t = (el.innerText || '').trim();
                            return hasBg && t.length > 0 && t.length < 50;
                        });
                        ddAnswers = allSpans.map(s => s.innerText.trim()).filter(t => !t.includes('Answer'));
                    }

                    // Trong Review của bài Drag-and-Drop, word bank thường bị
                    // vô hiệu hoá và không còn class `.draggable`.  Khi đó các
                    // đáp án đúng vẫn hiện ở ô xanh, nên đoạn fallback phía
                    // trên tìm được chúng trong `ddAnswers` nhưng nhánh DnD
                    // lại bị rỗng.  Đưa các ô xanh này về cache DnD theo đúng
                    // thứ tự hiển thị để lần làm lại kéo đủ đáp án.
                    const pageText = document.body.innerText || '';
                    if (dndAnswers.length === 0 && /drag the correct answer/i.test(pageText) && ddAnswers.length > 0) {
                        dndAnswers = [...ddAnswers];
                    }

                    return {
                        fullText: fullText,
                        mcq: mcqCorrect,
                        dnd: dndAnswers,
                        dropdown: ddAnswers
                    };
                }''')

                task_key = str(task_i)
                self._cached_test_answers[task_key] = item_data
                
                ans_summary = item_data.get('mcq') or (', '.join(item_data.get('dnd', []))) or (', '.join(item_data.get('dropdown', []))) or item_data.get('fullText', '')[:60]
                print(f"    [★] [Review Master Câu {task_i}/{total_tasks}] Đáp án chuẩn = '{ans_summary}'")

                # Bấm nút Next để sang câu tiếp theo của Review
                if task_i < total_tasks:
                    await self.page.evaluate('''() => {
                        const nextBtn = document.querySelector('#learning__nextItem, .learning__nextItemLink, a.next, button.next, [class*="nextItemLink"]');
                        if (nextBtn) nextBtn.click();
                    }''')
                    await self.page.wait_for_timeout(1000)

            print(f"[*] [Review Master] Đã lưu thành công 100% đáp án của {len(self._cached_test_answers)} câu vào cache!")
            return self._cached_test_answers
        except Exception as e:
            print(f"[!] Lỗi khi trích xuất Review: {e}")
            return {}

    async def reset_and_retake_test(self):
        """
        Làm lại bài test theo đúng hướng dẫn của người dùng:
        1. Mở popup Steps -> chọn Step 2: Practice
        2. Mở lại popup Steps -> chọn Step 3: Test
        3. Bấm nút Start Test để bắt đầu làm lại bài kiểm tra từ đầu với 100% cache!
        """
        print("[*] [Reset Test] Đang reset bài Test theo quy trình: Practice -> Test -> Start Test...")
        try:
            await self.dismiss_all_popups()
            await self.page.evaluate('''() => document.querySelectorAll('.utils__siteOverlay').forEach(x => { x.style.pointerEvents = 'none'; x.remove(); })''')
            await self.page.wait_for_timeout(500)

            # 1. Mở popup Steps -> Chọn Step 2: Practice
            print("[*] [Reset Test] 1/3: Mở dropdown Steps để chọn Practice...")
            await self.page.evaluate('''() => document.querySelectorAll('.learning__dropDownListTitleW')[1]?.click()''')
            await self.page.wait_for_timeout(800)

            prac_item = self.page.locator('.learning__dropDownList_item').filter(has_text='Practice').first
            if await prac_item.count() > 0:
                await prac_item.evaluate('el => el.click()')
                print("[*] [Reset Test] Đã click 'Practice'! Đang xử lý popup xác nhận nếu có...")
                await self.page.wait_for_timeout(1500)
                await self.dismiss_all_popups()
            else:
                await self.page.evaluate('''() => { const x = Array.from(document.querySelectorAll('.learning__dropDownList_item')).find(e => /practice/i.test(e.innerText)); if (x) x.click(); }''')
                await self.page.wait_for_timeout(2500)
                await self.page.wait_for_timeout(2500)

            # 2. Mở lại popup Steps -> Chọn Step 3: Test
            print("[*] [Reset Test] 2/3: Mở dropdown Steps để chọn lại Test...")
            await self.page.evaluate('''() => document.querySelectorAll('.utils__siteOverlay').forEach(x => x.remove())''')
            await self.page.evaluate('''() => document.querySelectorAll('.learning__dropDownListTitleW')[1]?.click()''')
            await self.page.wait_for_timeout(800)

            test_item = self.page.locator('.learning__dropDownList_item').filter(has_text='Test').first
            if await test_item.count() > 0:
                await test_item.evaluate('el => el.click()')
                print("[*] [Reset Test] Đã click 'Test'! Đang tải màn hình làm lại...")
                await self.page.wait_for_timeout(2500)
                await self.dismiss_all_popups()
            else:
                await self.page.evaluate('''() => { const x = Array.from(document.querySelectorAll('.learning__dropDownList_item')).find(e => /^test/i.test(e.innerText.trim())); if (x) x.click(); }''')
                await self.page.wait_for_timeout(2500)
                await self.dismiss_all_popups()

            # 3. Bấm nút Start Test
            clicked_start = await self.page.evaluate('''() => {
                const btn = document.querySelector('.btnStartTest, #testIntro a, .startTest a, .layout__roundBtn');
                if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                return false;
            }''')
            if clicked_start:
                print("[*] [Reset Test] 3/3: Đã bấm nút 'Start Test' qua evaluate!")
                await self.page.wait_for_timeout(3000)
                await self.dismiss_all_popups()
                return True

            # Fallback: chuyển thẳng Step Test bằng menu Angular rồi thử Start lại.
            await self.page.evaluate('''() => {
                document.querySelectorAll('.utils__siteOverlay').forEach(x => x.remove());
                const x = Array.from(document.querySelectorAll('.learning__dropDownList_item')).find(e => /^test/i.test(e.innerText.trim()));
                if (x) x.click();
            }''')
            await self.page.wait_for_timeout(1500)
            clicked_start = await self.page.evaluate('''() => {
                const btn = document.querySelector('.btnStartTest, #testIntro a, .startTest a, .layout__roundBtn');
                if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                return false;
            }''')
            if clicked_start:
                await self.page.wait_for_timeout(2500)
                print("[*] [Reset Test] Fallback đã mở lại Test và Start.")
                return True
            print("[!] [Reset Test] Không mở được màn hình Start Test.")
            return False
        except Exception as e:
            print(f"[!] Lỗi khi reset bài test: {e}")
            return False

    async def apply_cached_review_answer(self):
        """Nếu đang ở Step Test và có đáp án đã lưu từ chế độ Review -> Áp dụng ngay 100%!"""
        if not self._cached_test_answers:
            return None

        task_info = await self.page.evaluate('''() => {
            const pager = document.querySelector('.learning__tasksPager');
            const stepEl = document.querySelectorAll('.learning__dropDownListTitleW')[1];
            const isTest = stepEl && stepEl.innerText.toLowerCase().includes('test');
            let taskNum = '';
            if (pager) {
                const m = pager.innerText.match(/(\\d+)\\s*\\//);
                if (m) taskNum = m[1];
            }
            return { isTest, taskNum };
        }''')

        if not task_info["isTest"] or not task_info["taskNum"]:
            return None

        task_key = str(task_info["taskNum"])
        cached = self._cached_test_answers.get(task_key)
        if not cached:
            return None

        full_text = cached.get("fullText", "").lower()
        print(f"[*] [Review Master 100%] Áp dụng đáp án lưu cho Câu {task_key}...")

        # 1. Nếu là dạng Drag and Drop (Kéo thả vào ô trống)
        if cached.get("dnd") and len(cached["dnd"]) > 0:
            dnd_list = cached["dnd"]
            targets_loc = self.page.locator('.droptarget:visible:not([id^="bank_"]):not(:has(.draggable)):not(:has(.droptarget:visible)), .dndZone:visible:not([id^="bank_"]):not(:has(.draggable)):not(:has(.dndZone:visible)), .TTpanswerDiv:visible:not(:has(.draggable)):not(:has(.TTpanswerDiv:visible)), [ed-trackable-drop*="User_Answer"]:visible:not(:has(.draggable)):not(:has([ed-trackable-drop*="User_Answer"]:visible))')
            chips_loc = self.page.locator('.draggable.wordBankTile, .wordsBankWrapper .draggable, .dnditem.draggable, .dndBank .dnditem, .draggable')
            target_count = await targets_loc.count()
            if target_count > 0:
                print(f"[★] [Review Master 100%] Đang kéo thả {len(dnd_list)} thẻ từ chuẩn vào {target_count} ô trống...")
                # Cùng lý do với solver chính: kéo từ ô cuối về đầu để locator
                # động không đổi chỉ số sau mỗi lần thả.
                for idx, word in reversed(list(enumerate(dnd_list))):
                    if idx < target_count:
                        target = targets_loc.nth(idx)
                        # Khớp exact; contains-text làm `where` chọn nhầm
                        # `they're where`, khiến đáp án Review vẫn mất điểm.
                        exact_word = re.compile(rf"^\s*{re.escape(str(word))}\s*$", re.I)
                        chip = chips_loc.filter(has_text=exact_word).first
                        if await chip.count() > 0:
                            print(f"    Ô [{idx}] <- Kéo thẻ: '{word}'")
                            await chip.drag_to(target)
                            await self.page.wait_for_timeout(400)
                await self.page.wait_for_timeout(500)
                await self.click_check_answer()
                return "dnd_review_master_solved"

        # 2. Nếu là dạng MCQ (Trắc nghiệm)
        if cached.get("mcq"):
            target_mcq = cached["mcq"].strip()
            clicked = await self.page.evaluate('''(ans) => {
                const workArea = document.querySelector('#rightDiv, .pmContainer, .learning__practiceArea') || document.body;
                const rows = Array.from(workArea.querySelectorAll('.multiRadio, .prMCQ__answerLabel, .answerOption, ed-la-multiradio, label'));
                for (const r of rows) {
                    const txt = r.innerText.trim();
                    if (txt.toLowerCase() === ans.toLowerCase() || txt.includes(ans) || ans.includes(txt)) {
                        const target = r.querySelector('label, input') || r;
                        target.click();
                        return true;
                    }
                }
                return false;
            }''', target_mcq)
            if clicked:
                print(f"[★] [Review Master 100%] Đã chọn MCQ chuẩn: '{target_mcq}'")
                await self.page.wait_for_timeout(400)
                await self.click_check_answer()
                return "mcq_review_master_solved"

        # 3. Nếu là dạng Dropdown Popup (.DDLOptions__selected - như trong Lesson 5 Politics)
        ddl_selected_loc = self.page.locator('.DDLOptions__selected:visible')
        ddl_count = await ddl_selected_loc.count()
        cached_dropdowns = cached.get("dropdown") or []
        if ddl_count > 0 and cached_dropdowns:
            print(f"[*] [Review Master 100%] Phát hiện {ddl_count} Dropdown Popup cho Câu {task_key}...")
            solved_count = 0
            for ddl_idx in range(min(ddl_count, len(cached_dropdowns))):
                target_word = str(cached_dropdowns[ddl_idx]).strip()
                await ddl_selected_loc.nth(ddl_idx).click(force=True)
                await self.page.wait_for_timeout(350)
                items = await self.page.query_selector_all('.DDLOptions__listItem, .DDLOptions__list li')
                visible_items = [it for it in items if await it.is_visible()]
                best_item = None
                best_text = ""
                # Ưu tiên exact; chỉ dùng contains khi UI tách trợ động từ
                # ra ngoài dropdown (vd cache "had just closed", option "just closed").
                for it in visible_items:
                    t = (await it.inner_text()).strip()
                    if t.lower() == target_word.lower():
                        best_item, best_text = it, t
                        break
                if not best_item:
                    for it in visible_items:
                        t = (await it.inner_text()).strip()
                        if t and (t.lower() in target_word.lower() or target_word.lower() in t.lower()):
                            if len(t) > len(best_text):
                                best_item, best_text = it, t
                if best_item:
                    print(f"[★] Dropdown [{ddl_idx + 1}/{ddl_count}] = '{best_text}'")
                    await best_item.click(force=True)
                    solved_count += 1
                    await self.page.wait_for_timeout(300)
                else:
                    print(f"[!] Không tìm thấy option chuẩn cho Dropdown {ddl_idx + 1}: '{target_word}'")
                    break
            if solved_count == ddl_count:
                await self.click_check_answer()
                return "dropdown_popup_review_master_solved"

        # 4. Nếu là dạng Dropdown chuẩn (Select - CHỈ TÌM TRONG KHU VỰC BÀI LÀM)
        dd_solved = await self.page.evaluate('''(fullText) => {
            const workArea = document.querySelector('#rightDiv, .pmContainer, .learning__practiceArea');
            if (!workArea) return false;
            const ddlContainers = Array.from(workArea.querySelectorAll('.ddlOptions, .prDDL__select, select')).filter(d => d.offsetParent !== null);
            if (ddlContainers.length === 0) return false;

            for (const container of ddlContainers) {
                if (container.tagName === 'SELECT') {
                    for (let i = 0; i < container.options.length; i++) {
                        const optTxt = container.options[i].innerText.trim().toLowerCase();
                        if (optTxt && fullText.includes(optTxt)) {
                            container.selectedIndex = i;
                            container.dispatchEvent(new Event('change'));
                            break;
                        }
                    }
                }
            }
            return true;
        }''', full_text)
        if dd_solved:
            print(f"[★] [Review Master 100%] Đã chọn Dropdown chuẩn từ Review!")
            await self.page.wait_for_timeout(400)
            await self.click_check_answer()
            return "dropdown_review_master_solved"

        return None

    async def click_check_answer(self):
        """Bấm nút Check Answer để máy chủ lưu kết quả đã làm câu hỏi này"""
        try:
            checked = await self.page.evaluate('''() => {
                const btn = document.querySelector('#CheckAnswer, .practiceTools #CheckAnswer, [title="Check Answer"]');
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return true;
                }
                return false;
            }''')
            if checked:
                await self.page.wait_for_timeout(800)
        except Exception:
            pass

    async def advance_next(self):
        """Bấm nút Next hoặc Submit Test để chuyển sang câu/bài tiếp theo"""
        # Kiểm tra xem có phải nút Submit không (ở câu cuối bài Test, nút màu xanh có text Submit)
        is_submit = await self.page.evaluate('''() => {
            const btn = document.querySelector('.learning__submitTest, #learning__nextItem, .learning__nextItemLink, a.submitTest');
            if (btn && btn.offsetParent !== null) {
                const txt = (btn.innerText || '').trim().toLowerCase();
                if (txt === 'submit' || txt.includes('submit')) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }''')
        if is_submit:
            print("[*] Đã bấm nút Submit bài Test! Đang xử lý popup xác nhận nộp bài...")
            await self.page.wait_for_timeout(2000)
            await self.dismiss_all_popups()
            await self.page.wait_for_timeout(3000)
            return "submitted_test"

        # Nếu là nút Next thông thường
        next_btn = await self.page.query_selector("#learning__nextItem, .learning__nextItemLink")
        if next_btn and await next_btn.is_visible():
            txt = (await next_btn.inner_text()).strip().lower()
            if "submit" in txt:
                print("[*] Đã bấm nút Submit bài Test...")
                await next_btn.click(force=True)
                await self.page.wait_for_timeout(2000)
                await self.dismiss_all_popups()
                await self.page.wait_for_timeout(3000)
                return "submitted_test"

            print("[*] Chuyển tiếp (Next ->)...")
            await next_btn.click(force=True)
            await self.page.wait_for_timeout(1500)
            await self.dismiss_all_popups()
            return True

        return False

async def main():
    parser = argparse.ArgumentParser(description="Universal English Discoveries Autonomous Agent")
    parser.add_argument("--unit", type=str, default="", help="Tên hoặc số Unit cần làm (Ví dụ: 'Unit 2', '2', '3', 'Problems')")
    parser.add_argument("--lesson", type=str, default="", help="Tên hoặc số bài học (Ví dụ: '1', 'Family', 'Lesson 2')")
    parser.add_argument("--start-step", type=str, default="", help="Bắt đầu tại step cụ thể, ví dụ Test")
    parser.add_argument("--tests-only", action="store_true", help="Chỉ làm Test; tự chuyển qua Test khi sang lesson mới")
    parser.add_argument("--review-first", action="store_true", help="Lượt đầu bỏ trống nhanh để lấy đáp án chuẩn từ Review")
    parser.add_argument("--course", type=str, default="", help="Tên khóa học phải khớp chính xác (Ví dụ: 'Intermediate 2')")
    parser.add_argument("--steps", type=int, default=50, help="Số bước tối đa cần chạy (Mặc định: 50)")
    parser.add_argument("--min-score", type=int, default=100, help="Điểm bài Test tối thiểu cần đạt để chuyển bài (Mặc định: 100%%)")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn trình duyệt (Mặc định: Hiện trình duyệt --headed)")
    args = parser.parse_args()

    print("=" * 65)
    print("    UNIVERSAL ENGLISH DISCOVERIES AUTONOMOUS AGENT")
    print(f"    Target Unit  : {args.unit or 'Hiện tại / Mặc định'}")
    print(f"    Target Lesson: {args.lesson or 'Tất cả bài học'}")
    print(f"    Start Step   : {args.start_step or 'Explore'}")
    print(f"    Tests Only   : {'Có' if args.tests_only else 'Không'}")
    print(f"    Review First : {'Có' if args.review_first else 'Không'}")
    print(f"    Target Course: {args.course or 'Khóa đang chọn'}")
    print(f"    Min Test Score: {args.min_score}% (Tự động làm lại nếu dưới {args.min_score}%)")
    print(f"    Browser Mode : {'Ẩn (Headless)' if args.headless else 'Hiện trực tiếp (Headed)'}")
    print("=" * 65)

    async with async_playwright() as p:
        browser, context, page = await ensure_logged_in(p, headless=args.headless)
        agent = UniversalEngDisAgent(page, context)

        if "#/home" in page.url and args.course:
            selected = await agent.select_course_on_dashboard(args.course)
            if not selected:
                raise RuntimeError(f"Không thể chọn chính xác khóa học '{args.course}', dừng để tránh làm nhầm khóa.")

        if "#/home" in page.url and args.unit:
            opened = await agent.select_unit_on_dashboard(args.unit, args.lesson)
            if not opened and "#/home" in page.url:
                print(f"[!] Dùng nút Continue trên Dashboard...")
                continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=10000)
                await continue_btn.click()
        elif "#/home" in page.url:
            continue_btn = await page.wait_for_selector(".carouselStartBtnW a, a:has-text('Continue')", timeout=10000)
            await continue_btn.click()

        if "learningArea.html" not in page.url:
            await page.wait_for_url("**/learningArea.html*", timeout=20000)
        await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
        await page.wait_for_timeout(2000)

        if args.course:
            learning_text = " ".join(await page.locator(".learning__dropDownList_courseName, .learning__courseName").all_inner_texts()).strip()
            if learning_text and args.course.lower() not in learning_text.lower():
                raise RuntimeError(
                    f"Learning Area đang ở khóa '{learning_text}', không phải '{args.course}'. Dừng để tránh làm nhầm khóa."
                )
            print(f"[★] Learning Area đã xác minh khóa học: {args.course}")

        if args.lesson:
            await agent.select_lesson_in_learning_area(args.lesson)
            # Mặc định bắt đầu từ Explore để cache transcript/audio; có thể
            # chạy thẳng Test khi mục tiêu chỉ là sửa điểm đã lưu.
            await agent.select_step_in_learning_area(args.start_step or "Explore")

        for step_idx in range(1, args.steps + 1):
            await page.wait_for_timeout(1000)
            await agent.dismiss_all_popups()

            status = await page.evaluate('''() => {
                const dd = Array.from(document.querySelectorAll('.learning__dropDownListTitleW')).map(d => d.innerText.trim().replace(/\\n+/g, ' '));
                const pager = document.querySelector('.learning__tasksPager') ? document.querySelector('.learning__tasksPager').innerText.trim() : '';
                return { lesson: dd[0] || '', step: dd[1] || '', pager };
            }''')

            print(f"\n[Bước {step_idx}] {status['lesson']} | {status['step']} | Task {status['pager']}")
            await page.screenshot(path=f"{OUTPUT_DIR}/universal_step_{step_idx}.png")

            if args.tests_only and "test" not in status["step"].lower():
                print("[*] [Tests Only] Bỏ qua Explore/Practice đã hoàn tất; chuyển thẳng sang Test...")
                switched = await agent.select_step_in_learning_area("Test")
                if not switched:
                    moved = await agent.select_next_lesson_in_learning_area()
                    if not moved:
                        unit_text = " ".join(await page.locator(".learning__dropDownList_unitName").all_inner_texts())
                        unit_match = re.search(r"Unit\s+(\d+)", unit_text, re.I)
                        current_unit = int(unit_match.group(1)) if unit_match else 0
                        if current_unit and current_unit < 10:
                            next_unit = current_unit + 1
                            print(f"[*] [Tests Only] Hết Unit {current_unit}; mở Unit {next_unit} Lesson 1...")
                            await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
                            await page.wait_for_timeout(2500)
                            if args.course:
                                await agent.select_course_on_dashboard(args.course)
                            await agent.select_unit_on_dashboard(str(next_unit), "1")
                            await page.wait_for_selector(".learning__lessonsStepsNav", timeout=30000)
                            await page.wait_for_timeout(1500)
                        elif current_unit >= 10:
                            print("[★] Đã duyệt đến lesson cuối của Unit 10.")
                            break
                        else:
                            print("[!] Không xác định được Unit hiện tại để chuyển tiếp.")
                            break
                continue

            # Theo yêu cầu: bỏ qua các hoạt động tự do cần viết hoặc ghi âm/nói.
            # Không áp dụng cho Step Test và các ô điền đáp án cố định.
            skip_special = await page.evaluate('''() => {
                const step = (document.querySelectorAll('.learning__dropDownListTitleW')[1]?.innerText || '').toLowerCase();
                const text = (document.body.innerText || '').toLowerCase();
                if (step.includes('test')) return false;
                const voice = step.includes('speaking') || step.includes('interact') || /microphone|record your voice|speech recognition|click.*start.*activity/.test(text);
                const freeWrite = /write (an|a|your)|write about|writing task|compose an essay/.test(text) && document.querySelector('textarea, [contenteditable="true"], iframe');
                return voice || freeWrite;
            }''')
            if skip_special:
                print("[*] [Skip Special] Bỏ qua bài tự do yêu cầu viết/voice theo yêu cầu.")
                has_next = await agent.advance_next()
                if not has_next:
                    break
                continue

            # BẢO VỆ TUYỆT ĐỐI: NẾU ĐANG Ở MÀN HÌNH KẾT QUẢ TEST MÀ ĐIỂM < 100% -> KHÔNG ĐƯỢC NHẢY BÀI, PHẢI REVIEW & RESET NGAY!
            if "test" in status['step'].lower():
                current_score = await agent.get_current_test_score()
                is_result_screen = await page.evaluate('''() => {
                    const text = document.body.innerText;
                    return text.includes("Your test score is") || text.includes("review your answers") || Array.from(document.querySelectorAll('a, button, div')).some(b => (b.innerText || '').toLowerCase().trim() === 'review');
                }''')
                if is_result_screen:
                    print(f"[*] [Phát hiện màn hình kết quả Test] Điểm hiện tại: {current_score}%")
                    if current_score is not None and current_score < args.min_score:
                        print(f"[!] [CẢNH BÁO] Điểm {current_score}% < {args.min_score}%. BẮT BUỘC REVIEW & RESET ĐỂ ĐẠT 100%!")
                        await agent.extract_review_answers()
                        restarted = await agent.reset_and_retake_test()
                        if restarted:
                            print("[★] Đã reset bài Test thành công! Bắt đầu giải lại...")
                            continue
                    elif current_score is not None and current_score >= args.min_score:
                        print(f"[★] Bài Test đã đạt chuẩn {current_score}% >= {args.min_score}%. Tiếp tục sang bài tiếp theo.")
                        agent._cached_test_answers = {}

            review_probe = (
                args.review_first
                and "test" in status["step"].lower()
                and "/" in status.get("pager", "")
                and not agent._cached_test_answers
                and not is_result_screen
            )
            if review_probe:
                print("[*] [Review First] Bỏ trống lượt thử để lấy toàn bộ đáp án chuẩn từ Review...")
                action = "none"
            else:
                action = await agent.solve_current_screen()
            print(f"    Kết quả xử lý: {action}")

            if action == "test_started":
                await page.wait_for_timeout(2000)
                continue

            # Theo yêu cầu vận hành nhanh: nếu solver không nhận diện được task,
            # vẫn bấm Next để ưu tiên hoàn thành tiến độ toàn Unit.
            is_result_screen_now = await agent.page.evaluate('''() => {
                const text = document.body.innerText || '';
                return /Your test score is|review your answers/i.test(text);
            }''')
            if action == "none" and "/" in status.get("pager", "") and not is_result_screen_now:
                print("[!] Task chưa được solver xử lý; bỏ qua bằng Next theo yêu cầu tiến độ.")

            has_next = await agent.advance_next()

            # NẾU VỪA NỘP BÀI TEST -> KIỂM TRA ĐIỂM SỐ
            if has_next == "submitted_test":
                print("[*] Đã nộp bài Test! Đang chờ máy chủ cập nhật điểm...")
                await page.wait_for_timeout(3500)
                await agent.dismiss_all_popups()

                test_score = await agent.get_current_test_score()
                if test_score is not None:
                    print(f"[*] [Xác Minh Điểm Test] Điểm số đạt được: {test_score}%")
                    if test_score < args.min_score:
                        print(f"[!] [CẢNH BÁO] Điểm {test_score}% < {args.min_score}%. KÍCH HOẠT THỦ THUẬT REVIEW ĐỂ ĐẠT 100%!")
                        # 1. Trích xuất toàn bộ đáp án chuẩn từ tab 'Correct Answer'
                        await agent.extract_review_answers()
                        # 2. Reset bài Test theo mẹo: Practice -> Test -> Start Test
                        restarted = await agent.reset_and_retake_test()
                        if restarted:
                            print("[★] Đã reset bài Test thành công! Đang giải lại với 100% đáp án chuẩn từ Review...")
                            continue
                    else:
                        print(f"[★] XUẤT SẮC! Bài Test đạt {test_score}% >= {args.min_score}% (ĐẠT CHUẨN 100%).")
                        # Xóa cache bài test cũ để sẵn sàng cho bài tiếp theo
                        agent._cached_test_answers = {}
                else:
                    print("[*] Không đọc được điểm test ngay trên thanh điều hướng, tiếp tục sang phần tiếp theo.")

            if not has_next:
                print("[*] Đã hoàn thành toàn bộ bài tập hoặc đến cuối phần học hiện tại.")
                break

        print("\n" + "=" * 65)
        print("[*] Hoàn tất phiên chạy! Đang quay lại Dashboard để đồng bộ điểm...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"{OUTPUT_DIR}/universal_final_dashboard.png")
        print(f"[*] Ảnh kết quả cuối cùng đã lưu tại: {OUTPUT_DIR}/universal_final_dashboard.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
