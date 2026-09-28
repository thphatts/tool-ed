import os
import json
import re

SYSTEM_PROMPT = """Bạn là trợ lý AI gia sư tiếng Anh chuyên nghiệp cho nền tảng English Discoveries (ETS).
Nhiệm vụ của bạn là đọc kỹ toàn bộ ngữ cảnh bài học (đoạn văn đọc hiểu, lời thoại transcript audio, câu hỏi) và suy luận đáp án chính xác nhất.
Quy tắc:
1. Đọc kỹ câu hỏi và nội dung transcript/đoạn văn được cung cấp.
2. Đối chiếu trực tiếp với transcript để tìm câu trả lời chính xác nhất.
3. CHỈ trả về JSON duy nhất: {"best_option_index": 0, "best_option_text": "...", "confidence": 0.95, "explanation": "..."}
"""

import os
import json
import re
import requests
from dotenv import load_dotenv

# Tự động nạp file .env từ thư mục hiện tại hoặc thư mục cha
cur_dir = os.path.dirname(os.path.abspath(__file__))
for env_path in [os.path.join(cur_dir, ".env"), os.path.join(cur_dir, "..", ".env")]:
    if os.path.exists(env_path):
        # Respect explicit environment overrides (e.g. OLLAMA_MODEL= to skip
        # the slow local fallback during course automation).
        load_dotenv(env_path, override=False)

class AIContextReasoner:
    """
    Hệ thống suy luận AI đa tầng thông minh:
    1. Multi-Key Gemini Rotation: Tự động đổi API Key khi một key bị hết Quota (429 / RESOURCE_EXHAUSTED).
    2. Multi-Provider Fallback: Tự động gọi sang Groq (Llama 3.3 70B), OpenRouter hoặc OpenAI nếu Gemini hết quota.
    3. Local Grammar & Semantic Engine: Dự phòng offline 100% không lo mất mạng.
    """
    def __init__(self, api_key=None):
        # 1. Thu thập toàn bộ danh sách Gemini API Keys
        self.gemini_keys = []
        if api_key:
            self.gemini_keys.append(api_key.strip())
        
        main_gemini = os.environ.get("GEMINI_API_KEY", "").strip()
        if main_gemini and main_gemini not in self.gemini_keys:
            self.gemini_keys.append(main_gemini)
            
        backup_gemini = os.environ.get("GEMINI_BACKUP_KEYS", "")
        if backup_gemini:
            for k in re.split(r'[,;\n]+', backup_gemini):
                k = k.strip()
                if k and k not in self.gemini_keys:
                    self.gemini_keys.append(k)

        # Quét thêm các key dạng GEMINI_API_KEY_1, GEMINI_API_KEY_2...
        for env_k, env_v in os.environ.items():
            if env_k.startswith("GEMINI_API_KEY_") and env_v.strip() and env_v.strip() not in self.gemini_keys:
                self.gemini_keys.append(env_v.strip())

        self.current_key_idx = 0
        self._quota_error_seen = False
        self.client = None
        self._init_active_gemini_client()

        # 2. Thu thập các Backup Provider khác
        self.ollama_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/v1").strip()
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "").strip()
        self.groq_key = os.environ.get("GROQ_API_KEY", "").strip()
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

        # In thông báo cấu hình
        print(f"[*] [AI Pool] Đã nạp {len(self.gemini_keys)} Gemini API Keys | Ollama: {'Bật (' + self.ollama_model + ')' if self.ollama_model else 'Tắt'} | Groq: {'Bật' if self.groq_key else 'Tắt'} | OpenRouter: {'Bật' if self.openrouter_key else 'Tắt'}")

    def _init_active_gemini_client(self):
        """Khởi tạo Gemini Client với key hiện tại"""
        self.client = None
        if self.current_key_idx < len(self.gemini_keys):
            active_key = self.gemini_keys[self.current_key_idx]
            try:
                from google import genai
                self.client = genai.Client(api_key=active_key)
                masked_key = active_key[:6] + "..." + active_key[-4:] if len(active_key) > 10 else active_key
                print(f"[*] [AI Reasoner] Đã kết nối Gemini API với Key #{self.current_key_idx + 1} ({masked_key})!")
            except Exception as e:
                print(f"[!] [AI Reasoner] Lỗi kết nối Gemini API (Key #{self.current_key_idx + 1}): {e}")

    @staticmethod
    def _parse_choice(data, options):
        """Parse an LLM answer safely; never silently turn a bad answer into option 0."""
        if not isinstance(data, dict) or not options:
            return None

        answer_text = str(data.get("best_option_text", "")).strip().casefold()
        if answer_text:
            exact = [i for i, option in enumerate(options) if str(option).strip().casefold() == answer_text]
            if len(exact) == 1:
                return exact[0]
            partial = [i for i, option in enumerate(options)
                       if answer_text in str(option).strip().casefold()
                       or str(option).strip().casefold() in answer_text]
            if len(partial) == 1:
                return partial[0]

        raw_index = data.get("best_option_index")
        if raw_index is not None:
            try:
                index = int(raw_index)
                if 0 <= index < len(options):
                    return index
                # Some models ignore the zero-based instruction and return 1..N.
                if 1 <= index <= len(options):
                    return index - 1
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def _load_json_response(raw):
        """Accept strict JSON plus fenced/explanatory provider responses."""
        if isinstance(raw, dict):
            return raw
        text = str(raw or "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return None
        return None

    def _rotate_gemini_key(self):
        """Chuyển sang Gemini Backup Key tiếp theo khi key hiện tại bị hết quota (429)"""
        if not self._quota_error_seen:
            return False
        self._quota_error_seen = False
        self.current_key_idx += 1
        if self.current_key_idx < len(self.gemini_keys):
            print(f"[!] [Key Rotation] Gemini Key trước đó hết Quota, tự động đổi sang Backup Key #{self.current_key_idx + 1}/{len(self.gemini_keys)}...")
            self._init_active_gemini_client()
            return True
        else:
            print("[!] [Key Rotation] TẤT CẢ Gemini Keys đã hết Quota! Đang chuyển sang Provider dự phòng (Groq / OpenRouter)...")
            self.client = None
            return False

    def _call_backup_provider(self, prompt, json_mode=True):
        """Gọi Provider dự phòng (Ollama, Groq, OpenRouter hoặc OpenAI) khi Gemini hết quota hoặc ưu tiên dùng Local"""
        
        # 0. Ưu tiên Ollama (Mô hình Local)
        if self.ollama_model and self.ollama_url:
            try:
                print(f"[*] [Backup Provider] Đang gọi Ollama Local ({self.ollama_model})...")
                resp = requests.post(
                    f"{self.ollama_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self.ollama_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    },
                    timeout=6 # Không để Ollama chặn toàn bộ course khi local model quá tải
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    print(f"[*] [Ollama Local] Nhận kết quả thành công!")
                    return text
                else:
                    print(f"[!] Ollama trả về mã lỗi: {resp.status_code} - {resp.text[:100]}")
            except Exception as e:
                print(f"[!] Lỗi gọi Ollama Local: {e}")

        # 1. Dự phòng Groq API (Siêu tốc, miễn phí 14,400 req/ngày, model Llama 3.3 70B rất giỏi tiếng Anh)
        if self.groq_key:
            try:
                print("[*] [Backup Provider] Đang gọi Groq API (Llama 3.3 70B Versatile)...")
                payload = {
                    # llama-3.3-70b-versatile is rejected by the current
                    # Groq endpoint for this account; keep the free-tier
                    # compatible production model as fallback.
                    "model": "openai/gpt-oss-20b",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                # Một số model Groq hiện tại trả 400 khi bật response_format
                # json_object dù prompt đã yêu cầu JSON. Để fallback hoạt động
                # ổn định, chỉ ràng buộc định dạng bằng prompt và parse ở caller.
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=10
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    print(f"[*] [Groq Backup] Nhận kết quả thành công!")
                    return text
                else:
                    print(f"[!] Groq API trả về mã lỗi: {resp.status_code} - {resp.text[:100]}")
            except Exception as e:
                print(f"[!] Lỗi gọi Groq Backup: {e}")

        # 2. Dự phòng OpenRouter API
        if self.openrouter_key:
            try:
                print("[*] [Backup Provider] Đang gọi OpenRouter API...")
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openrouter_key}", "Content-Type": "application/json"},
                    json={
                        "model": "meta-llama/llama-3.3-70b-instruct",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    },
                    timeout=12
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    print(f"[*] [OpenRouter Backup] Nhận kết quả thành công!")
                    return text
            except Exception as e:
                print(f"[!] Lỗi gọi OpenRouter Backup: {e}")

        # 3. Dự phòng OpenAI API
        if self.openai_key:
            try:
                print("[*] [Backup Provider] Đang gọi OpenAI API (gpt-4o-mini)...")
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    text = resp.json()["choices"][0]["message"]["content"].strip()
                    return text
            except Exception as e:
                print(f"[!] Lỗi gọi OpenAI Backup: {e}")

        return None

    def _upload_audio_file(self, audio_path):
        """Upload file audio lên Gemini File API (dùng chung cho nhiều hàm)"""
        if not self.client or not audio_path or not os.path.exists(audio_path):
            return None
        try:
            audio_file = self.client.files.upload(file=audio_path)
            return audio_file
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                self._quota_error_seen = True
                if self._rotate_gemini_key():
                    return self._upload_audio_file(audio_path)
            print(f"[!] Lỗi upload audio: {e}")
            return None

    async def reason_with_audio_file(self, audio_path, unit_title, question_text, options):
        """Cho phép Gemini nghe trực tiếp file âm thanh (Audio Multimodal) cho MCQ"""
        if not self.client or not os.path.exists(audio_path):
            return None

        clean_options = [str(opt).strip() for opt in options if str(opt).strip()]
        opts_prompt = "\n".join([f"{i}. {opt}" for i, opt in enumerate(clean_options)])

        prompt = f"""Bạn là gia sư tiếng Anh ETS. Hãy nghe thật kỹ đoạn ghi âm audio được đính kèm và trả lời câu hỏi sau:
Câu hỏi: {question_text}

Các lựa chọn:
{opts_prompt}

Hãy chọn phương án đúng nhất. CHỈ trả về JSON: {{"best_option_index": 0, "best_option_text": "..."}}"""

        for model_name in ["gemini-3.6-flash"]:
            try:
                print(f"[*] [AI Audio MCQ] Đang tải audio lên Gemini ({model_name}) để nghe trực tiếp...")
                audio_file = self._upload_audio_file(audio_path)
                if not audio_file:
                    break
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[audio_file, prompt],
                    config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                idx = self._parse_choice(data, clean_options)
                if idx is not None:
                    print(f"[*] [AI Audio Heard] Gemini đã nghe và chọn: '{clean_options[idx]}'")
                    return idx
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    self._quota_error_seen = True
                    print(f"[!] Quota exceeded ({model_name}), thử Backup Key hoặc Model khác...")
                    if self._rotate_gemini_key():
                        return await self.reason_with_audio_file(audio_path, unit_title, question_text, options)
                    continue
                print(f"[!] Lỗi AI Audio MCQ ({model_name}): {e}")
                break
        return None

    async def reason_best_answer(self, unit_title, lesson_title, question_text, options, passage_context="", audio_path=None):
        """Suy luận trắc nghiệm MCQ dựa vào Audio trực tiếp hoặc Transcript"""
        if not options:
            return None

        clean_options = [str(opt).strip() for opt in options if str(opt).strip()]
        if not clean_options:
            return None

        # 1. Nếu có file Audio tải về được -> Ưu tiên cho Gemini nghe trực tiếp
        if audio_path and os.path.exists(audio_path):
            audio_result = await self.reason_with_audio_file(audio_path, unit_title, question_text, clean_options)
            if audio_result is not None:
                return audio_result

        # 2. Sử dụng Transcript đọc từ DOM
        if self.client or self.groq_key or self.openrouter_key or self.openai_key:
            prompt = f"""Ngữ cảnh bài học:
- Chủ đề: {unit_title}
- Bài học: {lesson_title}

Lời thoại Audio / Bài đọc trích xuất (Transcript):
\"\"\"{passage_context if passage_context else "Dựa vào câu hỏi và các phương án."}\"\"\"

Câu hỏi:
{question_text if question_text else "Chọn phương án đúng nhất theo ngữ cảnh bài học."}

Các lựa chọn:
"""
            for i, opt in enumerate(clean_options):
                prompt += f"{i}. {opt}\n"

            prompt += "\nHãy chọn phương án đúng nhất. CHỈ trả về JSON duy nhất: {\"best_option_index\": 0, \"best_option_text\": \"...\"}"

            while self.client:
                for model_name in ["gemini-3.6-flash"]:
                    try:
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config={"response_mime_type": "application/json"}
                        )
                        data = json.loads(response.text)
                        idx = self._parse_choice(data, clean_options)
                        if idx is not None:
                            print(f"[*] [AI Reasoning ({model_name})] Chọn: '{clean_options[idx]}'")
                            return idx
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            self._quota_error_seen = True
                            continue
                        break
                if not self._rotate_gemini_key():
                    break

            # Gọi Provider dự phòng (Groq / OpenRouter / OpenAI) nếu Gemini hết quota
            backup_resp = self._call_backup_provider(prompt, json_mode=True)
            if backup_resp:
                try:
                    data = self._load_json_response(backup_resp)
                    idx = self._parse_choice(data, clean_options)
                    if idx is not None:
                        print(f"[*] [AI Backup Provider] Chọn: '{clean_options[idx]}'")
                        return idx
                except Exception:
                    pass

        # 3. Thuật toán so khớp ngữ cảnh và transcript cục bộ (Local Semantic Matcher)
        return self._local_semantic_match(question_text, clean_options, passage_context)

    async def reason_multi_answer(self, unit_title, lesson_title, question_text, options, passage_context=""):
        """Chọn nhiều đáp án cho dạng checkbox / select-all-that-apply."""
        clean_options = [str(opt).strip() for opt in options if str(opt).strip()]
        if not clean_options:
            return []
        prompt = f'''Ngữ cảnh bài học:
{passage_context}

Câu hỏi checkbox (có thể có nhiều đáp án đúng):
{question_text}

Các lựa chọn:
'''
        for i, opt in enumerate(clean_options):
            prompt += f"{i}. {opt}\n"
        prompt += '\nChọn TẤT CẢ đáp án đúng. Chỉ trả về JSON: {"selected_option_indices":[0,2],"explanation":"..."}'

        def parse(raw):
            data = self._load_json_response(raw)
            if not isinstance(data, dict):
                return None
            vals = data.get("selected_option_indices")
            if not isinstance(vals, list):
                return None
            result = []
            for val in vals:
                try:
                    idx = int(val)
                    if 0 <= idx < len(clean_options) and idx not in result:
                        result.append(idx)
                except (TypeError, ValueError):
                    pass
            return result

        while self.client:
            try:
                response = self.client.models.generate_content(
                    model="gemini-3.6-flash", contents=prompt,
                    config={"response_mime_type": "application/json"})
                parsed = parse(response.text)
                if parsed is not None:
                    print(f"[*] [AI Multi-select] Chọn các đáp án: {parsed}")
                    return parsed
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    self._quota_error_seen = True
                    continue
                break
            if not self._rotate_gemini_key():
                break
        backup = self._call_backup_provider(prompt, json_mode=True)
        parsed = parse(backup) if backup else None
        if parsed is not None:
            print(f"[*] [AI Backup Multi-select] Chọn các đáp án: {parsed}")
            return parsed
        return []

    async def reason_gap_fill_mapping(self, passage_with_slots, available_words, transcript="", audio_path=None, num_slots=1, lesson_title="", unit_title="", target_contexts=None):
        """
        Dạng 2: Kéo thả từ vào ô bị khuyết
        
        Chiến lược ưu tiên:
        1. Audio file → Gemini Multimodal nghe trực tiếp
        2. Gemini text với ngữ cảnh bài học + transcript + passage
        3. Local Grammar & Transcript Engine (nhận diện thì ngữ pháp, cấu trúc câu, transcript)
        """
        if not available_words:
            return {}

        # Xây dựng prompt rõ ràng, đánh số từng từ
        context_parts = []
        if lesson_title:
            context_parts.append(f"=== CHỦ ĐỀ BÀI HỌC / NGỮ PHÁP ===\n{lesson_title}")
        if transcript:
            context_parts.append(f"=== LỜI THOẠI AUDIO / TRANSCRIPT ===\n{transcript}")
        if passage_with_slots:
            context_parts.append(f"=== CÂU VĂN CÓ Ô TRỐNG (cần điền từ) ===\n{passage_with_slots}")
        if target_contexts:
            context_parts.append(f"=== CÁC ĐỊNH NGHĨA / NGỮ CẢNH CỦA TỪNG Ô (đánh số từ 1) ===\n" + "\n".join([f"  Ô [{i + 1}]: {c}" for i, c in enumerate(target_contexts)]))
        
        context_text = "\n\n".join(context_parts) if context_parts else "Dựa vào ngữ pháp và ngữ cảnh của các từ."

        # Đánh số rõ ràng từng từ
        words_numbered = "\n".join([f"  [{i}] \"{w}\"" for i, w in enumerate(available_words)])
        
        prompt = f"""Bạn là giáo viên tiếng Anh ETS. Nhiệm vụ: Chọn từ/cụm từ ĐÚNG để điền vào {num_slots} ô trống trong câu văn.

{context_text}

Có {len(available_words)} từ/cụm từ sau để lựa chọn (một số là từ NHIỄU, không dùng):
{words_numbered}

SỐ Ô TRỐNG CẦN ĐIỀN: {num_slots}

QUY TẮC BẮT BUỘC:
1. Đọc kỹ chủ đề ngữ pháp của bài học (nếu bài học về thì nào, ví dụ Past Perfect Progressive, thì ưu tiên thì đó).
2. Mỗi ô trống CHỈ ĐƯỢC ĐIỀN ĐÚNG 1 từ/cụm từ từ danh sách ở trên.
3. Giá trị trả về PHẢI CHÉP NGUYÊN VĂN từ danh sách (ví dụ: "had been looking").
4. Trả về đúng {num_slots} cặp key-value.

CHỈ trả về JSON, trong đó key là số ô bắt đầu từ 1: {{"1": "một_từ_duy_nhất_cho_ô_1"{', "2": "một_từ_duy_nhất_cho_ô_2"' if num_slots > 1 else ''}}}"""

        # 1. Thử gửi Audio cho Gemini nếu có
        if self.client and audio_path and os.path.exists(audio_path):
            audio_file = self._upload_audio_file(audio_path)
            if audio_file:
                for model_name in ["gemini-3.6-flash"]:
                    try:
                        print(f"[*] [AI Audio DnD] Đang cho Gemini ({model_name}) nghe audio để điền từ...")
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=[audio_file, prompt],
                            config={"response_mime_type": "application/json"}
                        )
                        mapping = json.loads(response.text)
                        if mapping and isinstance(mapping, dict):
                            print(f"[*] [AI Audio DnD ({model_name})] ĐÃ NGHE AUDIO và ghép từ:")
                            return self._validate_mapping(mapping, available_words, num_slots)
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            self._quota_error_seen = True
                            continue
                        break

        # 2. Thử Gemini Text API với prompt đầy đủ ngữ cảnh bài học
        while self.client:
            for model_name in ["gemini-3.6-flash"]:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    mapping = json.loads(response.text)
                    if mapping and isinstance(mapping, dict):
                        print(f"[*] [AI Gap-Fill ({model_name})] Đã ghép từ cho các ô khuyết:")
                        for slot, word in mapping.items():
                            print(f"    Ô [{slot}] -> '{word}'")
                        return self._validate_mapping(mapping, available_words, num_slots)
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        self._quota_error_seen = True
                        continue
                    break
            if not self._rotate_gemini_key():
                break

        # Thử Backup Provider cho Gap-Fill
        backup_resp = self._call_backup_provider(prompt, json_mode=True)
        if backup_resp:
            try:
                mapping = self._load_json_response(backup_resp)
                if mapping and isinstance(mapping, dict):
                    print(f"[*] [AI Backup Provider] Đã ghép từ cho các ô khuyết từ Groq/Backup:")
                    return self._validate_mapping(mapping, available_words, num_slots)
            except Exception:
                pass

        # 3. LOCAL GRAMMAR & TRANSCRIPT ENGINE (Cực kỳ chính xác khi không có API)
        print("[*] [Local Grammar Engine] Đang phân tích ngữ pháp & transcript cục bộ...")
        local_mapping = self._local_gap_fill_reasoner(
            passage_with_slots, available_words, transcript, num_slots,
            lesson_title, target_contexts=target_contexts
        )
        return self._validate_mapping(local_mapping, available_words, num_slots)

    def _local_gap_fill_reasoner(self, passage, available_words, transcript, num_slots, lesson_title="", target_contexts=None):
        """
        Bộ suy luận ngữ pháp & ngữ cảnh cục bộ:
        - Nhận diện thì ngữ pháp của bài học (Past Perfect Progressive, Past Simple, Passive...)
        - So khớp với transcript (đặc biệt cho bài sắp xếp thứ tự câu hoặc bài nghe)
        - So khớp định nghĩa với từ vựng (Matching Definitions)
        """
        lesson_lower = (lesson_title or "").lower()
        passage_lower = (passage or "").lower()
        transcript_lower = (transcript or "").lower()

        # TRƯỜNG HỢP A: BÀI NỐI TỪ VỚI ĐỊNH NGHĨA (Matching Words with Definitions)
        meaningful_contexts = [re.sub(r"\s+", " ", c.strip().lower()) for c in (target_contexts or []) if len(c.strip()) > 5]
        if meaningful_contexts and len(set(meaningful_contexts)) >= num_slots:
            print(f"[*] [Local Matching Engine] Phát hiện dạng bài nối từ với định nghĩa ({len(target_contexts)} định nghĩa)!")
            synonym_hints = {
                "update": ["new information", "news", "report", "latest", "recent", "fresh", "information"],
                "defeat": ["lose", "lost", "beaten", "fail", "surrender", "someone"],
                "press conference": ["meeting", "official information", "journalists", "reporters", "news", "announcement"],
                "key issue": ["main factor", "problem", "important", "essential", "primary", "issue"],
                "investigate": ["discover", "facts", "truth", "examine", "find out", "police", "search", "something"],
                "arson": ["fire", "burning", "crime", "illegal", "burn"],
                "suspect": ["believe", "think", "guilty", "police", "doubt"],
                "candidate": ["person", "election", "politics", "running", "vote"],
                "resign": ["quit", "leave", "give up", "job", "position"],
                "unemployment": ["jobless", "without work", "no job", "workers"],
                "education": ["school", "learning", "teaching", "students"],
                "clue": ["sign", "hint", "evidence", "trace", "solve"],
                "investigation": ["examination", "inquiry", "search", "police"],
                "attempted": ["tried", "try", "effort"],
                "murder": ["kill", "death", "crime"],
                "terrible": ["very bad", "awful", "dreadful"],
                "frightened": ["scared", "afraid", "fear"],
                "injure": ["hurt", "wound", "damage"],
                "recover": ["get better", "heal", "cure"],
                "bleed": ["blood", "lose blood"],
                "cliff": ["high", "steep", "rock", "edge"],
                "rocky": ["rocks", "rough", "stones"],
                "rescue": ["save", "help out", "danger"]
            }

            res = {}
            used_words = set()
            for slot_idx, def_text in enumerate(target_contexts[:num_slots]):
                def_lower = def_text.lower()
                best_word = None
                best_score = -9999.0

                for w in available_words:
                    if w in used_words:
                        continue
                    w_clean = re.sub(r'[^a-zA-Z0-9 ]', '', w.lower().strip())
                    score = 0.0

                    w_tokens = [t for t in w_clean.split() if len(t) > 2]
                    for token in w_tokens:
                        if token in def_lower:
                            score += 30.0

                    for root_key, hints in synonym_hints.items():
                        if root_key in w_clean:
                            for hint in hints:
                                if hint in def_lower:
                                    score += 45.0
                                elif any(h_tok in def_lower for h_tok in hint.split() if len(h_tok) > 3):
                                    score += 15.0

                    common_words = set(w_tokens) & set([t for t in def_lower.split() if len(t) > 2])
                    score += len(common_words) * 20.0

                    if score > best_score:
                        best_score = score
                        best_word = w

                if best_word:
                    res[str(slot_idx)] = best_word
                    used_words.add(best_word)
                    print(f"    Ô [{slot_idx}] ('{def_text[:35]}...') -> Ghép: '{best_word}' (Điểm: {best_score})")

            remaining = [w for w in available_words if w not in used_words]
            for slot_idx in range(num_slots):
                if str(slot_idx) not in res and remaining:
                    res[str(slot_idx)] = remaining.pop(0)

            return res

        # TRƯỜNG HỢP B: BÀI SẮP XẾP THỨ TỰ CÂU (Sentence Ordering)
        # Nếu các thẻ là câu hoàn chỉnh (dài > 20 ký tự) và có transcript
        if available_words and len(available_words[0]) > 20 and transcript_lower:
            positions = []
            for w in available_words:
                clean_w = re.sub(r'[^a-zA-Z0-9 ]', '', w.lower())
                words_in_sent = [x for x in clean_w.split() if len(x) > 3]
                # Tìm vị trí xuất hiện sớm nhất trong transcript
                pos = 999999
                for word in words_in_sent:
                    idx = transcript_lower.find(word)
                    if 0 <= idx < pos:
                        pos = idx
                positions.append((pos, w))
            positions.sort(key=lambda x: x[0])
            sorted_words = [p[1] for p in positions]
            print(f"[*] [Local Sentence Ordering] Đã sắp xếp {len(sorted_words)} câu theo thứ tự transcript:")
            res = {}
            for i in range(min(len(sorted_words), num_slots)):
                res[str(i)] = sorted_words[i]
                print(f"    Ô [{i}] -> '{sorted_words[i][:50]}...'")
            return res

        # TRƯỜNG HỢP B: BÀI NGỮ PHÁP (Grammar - Phân tích thì & cấu trúc)
        scores = {}
        for w in available_words:
            w_lower = w.lower().strip()
            score = 0.0

            # 1. Thì Past Perfect Progressive (had been + V-ing / 'd been + V-ing)
            is_past_perf_prog = (
                "past perfect" in lesson_lower or "progressive" in lesson_lower or
                "continuous" in lesson_lower or "had been" in passage_lower or
                "for months" in passage_lower or "for hours" in passage_lower or
                "before he realized" in passage_lower or "when she called" in passage_lower
            )
            if is_past_perf_prog:
                if re.search(r"\b(had|'d|hadn't)\s+(been|[a-z]+\s+been)\s+[a-z]+ing\b", w_lower):
                    score += 50.0
                elif re.search(r"\b(had|'d|hadn't)\s+been\b", w_lower):
                    score += 45.0
                elif re.search(r"\bhad\s+[a-z]+\s+been\b", w_lower):
                    score += 45.0
                elif "'d been" in w_lower or "had been" in w_lower or "hadn't been" in w_lower:
                    score += 40.0
                elif "was running" in w_lower or "were dating" in w_lower:
                    score += 5.0  # điểm thấp cho thì khác
                else:
                    score -= 10.0

            # 2. So khớp với Transcript nếu có
            if transcript_lower:
                if w_lower in transcript_lower:
                    score += 30.0
                else:
                    for token in w_lower.split():
                        if len(token) > 3 and token in transcript_lower:
                            score += 5.0

            # 3. Phân tích thì khác nếu không phải Past Perfect Progressive
            if "passive" in lesson_lower and re.search(r"\b(was|were|is|are|been|be)\s+[a-z]+(ed|en)\b", w_lower):
                score += 40.0
            if "present perfect" in lesson_lower and re.search(r"\b(have|has|haven't|hasn't)\s+[a-z]+", w_lower):
                score += 40.0

            scores[w] = score

        # Sắp xếp các từ theo điểm số từ cao đến thấp
        ranked_words = sorted(available_words, key=lambda w: scores.get(w, 0.0), reverse=True)
        print(f"[*] [Local Grammar Engine] Điểm xếp hạng từ: {[(w, scores.get(w, 0)) for w in ranked_words[:num_slots+2]]}")

        res = {}
        for i in range(min(len(ranked_words), num_slots)):
            res[str(i)] = ranked_words[i]
            print(f"    Ô [{i}] -> '{ranked_words[i]}'")
        return res

    def _validate_mapping(self, mapping, available_words, num_slots):
        """
        Kiểm tra và sửa kết quả từ AI:
        - Nếu giá trị trả về chứa NHIỀU từ ghép lại (concat), tìm từ hợp lệ đầu tiên
        - Nếu giá trị không khớp chính xác, tìm từ gần đúng nhất
        """
        validated = {}
        words_lower = {w.lower().strip(): w for w in available_words}
        used_words = set()

        # Một số model vẫn trả key 0-based dù prompt yêu cầu 1-based.
        # Chuẩn hóa một lần tại boundary để UI luôn nhận slot 1..N.
        mapping_keys = {str(k) for k in mapping}
        zero_based = "0" in mapping_keys and str(num_slots) not in mapping_keys

        for slot, word in mapping.items():
            slot_key = str(int(slot) + 1) if zero_based and str(slot).isdigit() else str(slot)
            word = str(word).strip()
            
            # Kiểm tra khớp chính xác
            if word.lower() in words_lower and word.lower() not in used_words:
                validated[slot_key] = words_lower[word.lower()]
                used_words.add(word.lower())
                continue

            # Nếu AI ghép nhiều từ: tìm từ hợp lệ trong chuỗi ghép
            found = False
            for aw in available_words:
                if aw.lower() in word.lower() and aw.lower() not in used_words:
                    print(f"[*] [Validate] Ô [{slot}]: '{word}' -> sửa thành '{aw}'")
                    validated[slot_key] = aw
                    used_words.add(aw.lower())
                    found = True
                    break
            
            if not found:
                # Không chọn đại một từ còn lại. Việc này làm bài bị submit sai
                # dù model đã trả về kết quả không hợp lệ.
                print(f"[!] [Validate] Ô [{slot}]: '{word}' không khớp từ word-bank; bỏ qua.")

        return validated

    async def reason_popup_dropdown_choice(self, sentence_context, options, transcript="", audio_path=None):
        """
        Dạng 1: Popup / Dropdown selection khi click vào ô trống
        Nay hỗ trợ nhận transcript và audio để suy luận chính xác hơn.
        """
        if not options:
            return None

        clean_opts = [str(o).strip() for o in options if str(o).strip()]
        if not clean_opts:
            return None

        if self.client or self.groq_key or self.openrouter_key or self.openai_key:
            # Xây dựng prompt với đầy đủ ngữ cảnh
            context_parts = []
            if transcript:
                context_parts.append(f"Lời thoại Audio / Transcript:\n\"{transcript}\"")
            
            context_str = "\n\n".join(context_parts)

            prompt = f"""Nhiệm vụ: Chọn từ đúng nhất để điền vào chỗ trống [_____] trong câu sau:

{f"=== NGỮ CẢNH ==={chr(10)}{context_str}{chr(10)}" if context_str else ""}
Câu văn:
\"{sentence_context}\"

Các phương án:
"""
            for i, opt in enumerate(clean_opts):
                prompt += f"{i}. {opt}\n"

            prompt += "\nCHỈ trả về JSON duy nhất: {\"best_option_index\": 0, \"best_option_text\": \"...\"}"

            # Thử audio trước
            if audio_path and os.path.exists(audio_path):
                audio_file = self._upload_audio_file(audio_path)
                if audio_file:
                    for model_name in ["gemini-3.6-flash"]:
                        try:
                            print(f"[*] [AI Audio Dropdown] Cho Gemini ({model_name}) nghe audio để chọn từ...")
                            response = self.client.models.generate_content(
                                model=model_name,
                                contents=[audio_file, prompt],
                                config={"response_mime_type": "application/json"}
                            )
                            data = json.loads(response.text)
                            idx = self._parse_choice(data, clean_opts)
                            if idx is not None:
                                print(f"[*] [AI Audio Dropdown] Chọn: '{clean_opts[idx]}'")
                                return idx
                        except Exception as e:
                            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                                self._quota_error_seen = True
                                continue
                            break

            # Text-only
            while self.client:
                for model_name in ["gemini-3.6-flash"]:
                    try:
                        response = self.client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config={"response_mime_type": "application/json"}
                        )
                        data = json.loads(response.text)
                        idx = self._parse_choice(data, clean_opts)
                        if idx is not None:
                            print(f"[*] [AI Dropdown ({model_name})] Chọn: '{clean_opts[idx]}'")
                            return idx
                    except Exception as e:
                        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                            self._quota_error_seen = True
                            continue
                        break
                if not self._rotate_gemini_key():
                    break

            # Thử Backup Provider cho Dropdown
            backup_resp = self._call_backup_provider(prompt, json_mode=True)
            if backup_resp:
                try:
                    data = self._load_json_response(backup_resp)
                    idx = self._parse_choice(data, clean_opts)
                    if idx is not None:
                        print(f"[*] [AI Backup Provider] Dropdown chọn từ Groq/Backup: '{clean_opts[idx]}'")
                        return idx
                except Exception:
                    pass

        # Fallback phân tích ngữ pháp cục bộ
        # Dropdown của bài nghe thường chứa đúng cụm từ trong transcript.
        # Đây là tín hiệu mạnh hơn việc đếm từ chung chung.
        if transcript:
            transcript_lower = transcript.casefold()
            exact_matches = [i for i, option in enumerate(clean_opts)
                             if option.casefold() in transcript_lower]
            if len(exact_matches) == 1:
                print(f"[*] [Local Transcript Match] Chọn: '{clean_opts[exact_matches[0]]}'")
                return exact_matches[0]

        collocations = {
            "flying": ["afraid", "scared"],
            "of": ["afraid", "scared", "tired", "fond"],
            "knee": ["bleed", "hurt", "injured"],
            "hospital": ["recover", "injury"],
            "mountain": ["cliff", "rocky"],
            "road": ["slippery", "icy"],
            "lost": ["take a wrong turn", "left behind"]
        }
        sent_lower = sentence_context.lower()
        for word, matched_opts in collocations.items():
            if word in sent_lower:
                for idx, opt in enumerate(clean_opts):
                    if opt.lower() in matched_opts:
                        print(f"[*] [Local Collocation] Khớp '{word}' -> Chọn [{idx}]: '{clean_opts[idx]}'")
                        return idx

        return None

    def _local_semantic_match(self, question, options, passage):
        """So khớp ngữ cảnh và transcript thông minh cục bộ không cần API"""
        if not passage:
            print("[!] [Local Matcher] Không có transcript/ngữ cảnh để suy luận.")
            return None

        passage_lower = passage.lower()
        question_lower = question.lower() if question else ""

        # Các câu hỏi từ vựng có đáp án là từ đồng nghĩa, không phải từ xuất
        # hiện nguyên văn trong transcript.
        synonym_groups = {
            "changed": {"replaced", "altered", "modified", "different"},
            "means changed": {"replaced", "altered", "modified", "different"},
        }
        for clue, synonyms in synonym_groups.items():
            if clue in question_lower:
                for i, option in enumerate(options):
                    if option.lower().strip(" .") in synonyms:
                        print(f"[*] [Local Vocabulary] '{clue}' -> Chọn [{i}]: '{option}'")
                        return i

        # Với True/False, so khớp mệnh đề với transcript. Đây là cách xử lý
        # được khi audio mô tả đúng bối cảnh của hình và model hết quota.
        normalized_question = re.sub(r"[^a-z0-9 ]", " ", question_lower)
        if {o.lower() for o in options} == {"true", "false"}:
            statement_words = {w for w in normalized_question.split() if len(w) > 3
                               and w not in {"look", "picture", "true", "false"}}
            overlap = sum(1 for w in statement_words if w in passage_lower)
            if overlap:
                return next(i for i, o in enumerate(options) if o.lower() == "true")

        scores = [0.0] * len(options)
        for i, opt in enumerate(options):
            opt_lower = opt.lower().strip()

            if opt_lower in passage_lower:
                scores[i] += 10.0

            words = [w for w in re.findall(r'[a-z]+', opt_lower) if len(w) > 3]
            for w in words:
                if w in passage_lower:
                    scores[i] += 3.0
                if w in question_lower:
                    scores[i] += 1.0

        # Câu hỏi phủ định hỏi phương án KHÔNG xuất hiện/không đúng.
        is_negative = bool(re.search(r"\b(not|n't|never|except)\b", question_lower))
        max_score = min(scores) if is_negative else max(scores)
        if (not is_negative and max_score <= 0) or (is_negative and max(scores) == min(scores)):
            print("[!] [Local Matcher] Không có bằng chứng đủ mạnh để chọn đáp án.")
            return None
        best_idx = scores.index(max_score) if is_negative else scores.index(max_score)
        print(f"[*] [Local Matcher] Điểm khớp transcript: {scores} -> Chọn [{best_idx}]: '{options[best_idx]}'")
        return best_idx
