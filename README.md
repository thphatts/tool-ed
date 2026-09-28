# tool-ed

tool-ed là agent Python điều khiển trình duyệt để hỗ trợ thao tác trên nền tảng English Discoveries. Dự án dùng Playwright để đăng nhập, điều hướng Unit/Lesson, xử lý nhiều dạng bài tập và lưu lại ảnh chụp phục vụ kiểm tra. Khi cần suy luận ngữ nghĩa, agent có thể dùng Gemini và tự động chuyển sang Ollama, Groq, OpenRouter hoặc OpenAI.

> Chỉ sử dụng với tài khoản bạn được phép truy cập và tuân thủ quy định của đơn vị đào tạo. Không chia sẻ API key, mật khẩu, cookie hoặc các tệp phiên đăng nhập.

## Tính năng chính

- Tái sử dụng phiên đăng nhập qua `session_state.json`.
- Chọn Unit theo số hoặc tên, chọn Lesson và bắt đầu lại từ bước Explore.
- Thu thập transcript/audio làm ngữ cảnh cho câu hỏi.
- Xử lý các dạng MCQ, đúng/sai, điền từ, dropdown và một số bài ghép/kéo thả.
- Hỗ trợ nhiều AI provider, xoay vòng Gemini key khi hết quota và có bộ suy luận cục bộ dự phòng.
- Kiểm tra điểm Test, đọc đáp án ở chế độ Review và thử lại khi chưa đạt ngưỡng cấu hình.
- Lưu ảnh chụp và dữ liệu chẩn đoán trong `run_artifacts/`.

## Yêu cầu

- Python 3.10 trở lên (môi trường hiện tại dùng Python 3.14).
- Kết nối mạng tới English Discoveries và AI provider đã chọn.
- Tài khoản English Discoveries hợp lệ.
- Ollama là tùy chọn nếu muốn chạy mô hình cục bộ.

## Cài đặt

Tạo môi trường ảo và cài các thư viện cần thiết:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Trên Windows, kích hoạt môi trường bằng:

```powershell
.venv\Scripts\activate
```

## Cấu hình

Sao chép tệp cấu hình mẫu trước khi chạy:

```bash
cp .env.example .env
```

Điền URL cổng English Discoveries, tài khoản và mật khẩu:

```dotenv
ED_URL="https://your-host.example/your-institution#/home"
ED_USERNAME="your-username"
ED_PASSWORD="your-password"
```

Các AI provider là tùy chọn:

```dotenv
GEMINI_API_KEY="your-key"
GEMINI_BACKUP_KEYS="key-2,key-3"

GROQ_API_KEY=""
OPENROUTER_API_KEY=""
OPENAI_API_KEY=""

OLLAMA_API_URL="http://localhost:11434/v1"
OLLAMA_MODEL=""
```

Thứ tự dự phòng trong mã hiện tại là Ollama, Groq, OpenRouter rồi OpenAI khi Gemini không sử dụng được. Nếu không cấu hình provider, một số câu vẫn có thể được giải bằng quy tắc cục bộ nhưng độ chính xác sẽ thấp hơn.

## Sử dụng

Điểm vào chính của dự án là `run_any_unit.py`.

```bash
python run_any_unit.py --unit 2 --lesson 1 --steps 50
```

Mặc định trình duyệt được hiển thị để tiện theo dõi. Thêm `--headless` để chạy nền:

```bash
python run_any_unit.py \
  --unit "Problems" \
  --lesson "Lesson 2" \
  --steps 300 \
  --min-score 100 \
  --headless
```

Các tham số:

| Tham số       |      Mặc định | Ý nghĩa                                           |
| ------------- | ------------: | ------------------------------------------------- |
| `--unit`      | Unit hiện tại | Số hoặc tên Unit, ví dụ `2`, `Unit 2`, `Problems` |
| `--lesson`    |    Tất cả bài | Số hoặc tên Lesson cần mở                         |
| `--steps`     |          `50` | Số vòng xử lý tối đa                              |
| `--min-score` |         `100` | Điểm Test tối thiểu trước khi chuyển tiếp         |
| `--headless`  |           tắt | Chạy Chromium không hiển thị cửa sổ               |

Kiểm tra riêng việc đăng nhập và tạo/làm mới phiên:

```bash
python session_manager.py
```

## Kiểm thử

Chạy các unit test không cần mở trình duyệt:

```bash
python -m unittest -v test_reasoning.py
```

Các tệp `test_navigation.py`, `test_video_complete.py`, `inspect_*.py`, `explore_*.py` và `run_unit2*.py` là script tích hợp/chẩn đoán. Chúng truy cập hệ thống thật, có thể thay đổi tiến độ học và phụ thuộc vào cấu trúc DOM hiện tại; chỉ chạy khi bạn hiểu rõ phạm vi của từng script.

## Cấu trúc dự án

```text
.
├── run_any_unit.py       # Agent tổng quát và CLI chính
├── settings.py           # Đọc cấu hình cục bộ từ biến môi trường
├── ai_reasoner.py        # Suy luận AI, xoay key và fallback provider
├── session_manager.py    # Đăng nhập, khôi phục và lưu phiên Playwright
├── solver_engine.py      # Bộ giải cơ bản dùng cho các script cũ
├── test_reasoning.py     # Unit test cho logic phân tích đáp án
├── inspect_*.py          # Công cụ quan sát DOM/trạng thái màn hình
├── run_unit2*.py         # Luồng thử nghiệm dành riêng cho Unit 2
├── requirements.txt      # Phiên bản dependency đã kiểm thử
├── .env.example          # Mẫu cấu hình an toàn để commit
├── session_state.json    # Phiên cục bộ, được Git bỏ qua
└── run_artifacts/        # Dữ liệu sinh khi chạy, được Git bỏ qua
```

## Dữ liệu đầu ra

Trong quá trình chạy, agent ghi ảnh theo từng bước vào `run_artifacts/universal_step_<n>.png` và ảnh dashboard cuối vào `run_artifacts/universal_final_dashboard.png`. Thư mục này có thể chứa nội dung bài học hoặc dữ liệu gắn với tài khoản, vì vậy không nên công khai.

## Xử lý sự cố

- **Chromium chưa được cài:** chạy `python -m playwright install chromium`.
- **Phiên hết hạn hoặc bị đăng nhập ở thiết bị khác:** chạy lại `python session_manager.py`; agent sẽ thử đăng nhập mới và ghi lại `session_state.json`.
- **Không kết nối được trang:** mặc định dự án dùng DNS của hệ thống. Chỉ đặt `ED_HOST_RESOLVER_RULES` trong `.env` khi môi trường của bạn thực sự cần ánh xạ host thủ công; xóa giá trị này nếu địa chỉ IP đã thay đổi.
- **AI trả lỗi quota:** thêm key vào `GEMINI_BACKUP_KEYS` hoặc cấu hình một provider dự phòng.
- **Selector không còn hoạt động:** giao diện English Discoveries có thể đã thay đổi. Dùng các script `inspect_*.py` và ảnh trong `run_artifacts/` để xác định selector mới.

## Lưu ý bảo mật

`.gitignore` đã loại trừ các tệp nhạy cảm và dữ liệu sinh tự động:

```gitignore
.env
.env.*
!.env.example
.venv/
__pycache__/
session_state.json
run_artifacts/
```

- Không đưa screenshot, HTML dump, audio hoặc storage state lên issue/PR vì chúng có thể chứa thông tin tài khoản.
- Nếu thông tin đăng nhập hoặc API key từng được chia sẻ/commit, hãy đổi mật khẩu, thu hồi key cũ và đăng xuất các phiên đang hoạt động. Thêm chúng vào `.gitignore` không xóa bí mật khỏi lịch sử Git cũ.
