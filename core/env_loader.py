"""Environment loader for desktop/dev execution."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str = ".env") -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False

    # Prefer python-dotenv when available for robust parsing.
    try:
        from dotenv import load_dotenv

        return bool(load_dotenv(dotenv_path=env_path, override=False))
    except Exception:
        pass

    loaded = False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value
            loaded = True

    return loaded
