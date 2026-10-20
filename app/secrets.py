"""Load optional secrets (Mindat token) from env / key.env / Render secret files."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ENV_CANDIDATES = (_ROOT / ".env", _ROOT / "key.env")
_SECRETS_DIR = Path("/etc/secrets")
_KEY_NAMES = (
    "MINDAT_API_KEY",
    "MINDAT_TOKEN",
    "MINDAT_KEY",
    "OPENMINDAT_API_KEY",
)


def _load_dotenv() -> None:
    for path in _ENV_CANDIDATES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export ") :].strip()
                value = value.strip().strip("'").strip('"')
                if key and value and key not in os.environ:
                    os.environ[key] = value
            elif "MINDAT_API_KEY" not in os.environ:
                os.environ["MINDAT_API_KEY"] = line.strip("'").strip('"')
        break


def mindat_api_key() -> str | None:
    _load_dotenv()
    for name in _KEY_NAMES:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    for fname in ("MINDAT_API_KEY", "mindat_api_key", "key.env"):
        path = _SECRETS_DIR / fname
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() in _KEY_NAMES and v.strip():
                        return v.strip().strip("'").strip('"')
                else:
                    return line.strip("'").strip('"')
        except OSError:
            continue
    return None
