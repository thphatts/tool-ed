"""Local configuration loaded from environment variables.

Keep real credentials in ``.env`` only. That file is intentionally ignored by Git.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)

URL = os.getenv("ED_URL", "").strip()
USERNAME = os.getenv("ED_USERNAME", "").strip()
PASSWORD = os.getenv("ED_PASSWORD", "").strip()
STORAGE_STATE = os.getenv("ED_STORAGE_STATE", "session_state.json").strip()
OUTPUT_DIR = os.getenv("ED_OUTPUT_DIR", "run_artifacts").strip()

_parsed_url = urlsplit(URL)
ORIGIN = f"{_parsed_url.scheme}://{_parsed_url.netloc}" if _parsed_url.scheme and _parsed_url.netloc else ""

CHROMIUM_ARGS = []
_resolver_rules = os.getenv("ED_HOST_RESOLVER_RULES", "").strip()
if _resolver_rules:
    CHROMIUM_ARGS.append(f"--host-resolver-rules={_resolver_rules}")


def require_login_config() -> None:
    """Fail with an actionable message instead of attempting an empty login."""
    missing = [
        name
        for name, value in (
            ("ED_URL", URL),
            ("ED_USERNAME", USERNAME),
            ("ED_PASSWORD", PASSWORD),
        )
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Thiếu cấu hình {joined}. Hãy sao chép .env.example thành .env và điền giá trị.")
