"""Security, session token generation and verification for Gymsis.
Eliminates client-side authentication bypass vulnerabilities via cryptographic HMAC-SHA256 signatures.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional, Dict, Any

_SESSION_SECRET = None


def get_session_secret() -> bytes:
    """Retrieve or generate a stable secret key for signing session tokens."""
    global _SESSION_SECRET
    if _SESSION_SECRET is None:
        secret = os.getenv("GYMSIS_SECRET_KEY", "").strip()
        if not secret:
            try:
                from core.db_store import load_settings, save_settings
                settings = load_settings()
                stored = settings.get("gymsis_session_secret")
                if stored:
                    secret = stored
                else:
                    import secrets
                    secret = secrets.token_hex(32)
                    save_settings({"gymsis_session_secret": secret})
            except Exception:
                import secrets
                secret = secrets.token_hex(32)
        _SESSION_SECRET = secret.encode("utf-8")
    return _SESSION_SECRET


def create_session_token(username: str, role: str, expires_in_seconds: int = 7 * 86400) -> str:
    """Create a tamper-proof HMAC signed session token."""
    payload = {
        "u": username.strip().lower(),
        "r": role.strip().lower(),
        "exp": int(time.time() + expires_in_seconds),
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8")
    sig = hmac.new(get_session_secret(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session_token(token: str) -> Optional[Dict[str, str]]:
    """Verify HMAC signature and expiration of session token.
    Returns dict with username and role if valid, else None.
    """
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.split(".", 1)
        expected_sig = hmac.new(get_session_secret(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)
        if time.time() > payload.get("exp", 0):
            return None
        return {"username": payload["u"], "role": payload["r"]}
    except Exception:
        return None
