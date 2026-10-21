"""State machine for member status transitions.

Valid manual account states: Activo, Inactivo
Dynamic payment states: Vigente, En Gracia, Vencido
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional, Tuple, Dict, Any

VALID_STATES = frozenset({"Activo", "Inactivo", "Moroso"})


def get_moroso_grace_days() -> int:
    """Read moroso_grace_days from app settings (days as Activo after expiry)."""
    try:
        from core.db_store import load_settings
        settings = load_settings()
        return max(0, int(settings.get("moroso_grace_days", 0)))
    except (TypeError, ValueError, Exception):
        return 0


def get_payment_status(vencimiento_str: str) -> str:
    """Determine subscription payment status: 'Vigente', 'En Gracia', or 'Vencido'.
    Uses moroso_grace_days from app settings.
    """
    if not vencimiento_str:
        return "Vencido"

    try:
        raw_date = vencimiento_str.split()[0]
        venc = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return "Vencido"

    today = datetime.now().date()
    days_expired = (today - venc).days

    if days_expired <= 0:
        return "Vigente"

    grace = get_moroso_grace_days()
    if days_expired <= grace:
        return "En Gracia"

    return "Vencido"


def compute_member_status(vencimiento_str: str = "", current_estado: str = "Activo", moroso_grace_days: int = 0) -> str:
    """Compute what the member's account status should be.
    Keeps manual account status as is (Activo/Inactivo).
    """
    if current_estado not in {"Activo", "Inactivo"}:
        return "Activo"
    return current_estado


def can_activate(current_estado: str, has_valid_payment: bool = True) -> Tuple[bool, str]:
    """Check whether a member can be set to 'Activo'."""
    return True, "Permitido"


def can_transition(current: str, target: str, has_valid_payment: bool = True) -> Tuple[bool, str]:
    """Validate a status transition."""
    if target not in VALID_STATES:
        return False, f"Estado destino inválido: {target}"
    return True, "Permitido"


def has_active_payment_for(cedula: str) -> bool:
    """Check if a member has a payment whose fecha_fin >= today."""
    today = datetime.now().date().isoformat()
    try:
        from core.db_store import load_membership_payments
        payments = load_membership_payments(cedula=cedula, limit=1)
        if not payments:
            return False
        latest = payments[0]
        fecha_fin = latest.get("fecha_fin", "")
        if not fecha_fin:
            return False
        return fecha_fin >= today
    except Exception:
        return False


def refresh_all_statuses(moroso_grace_days: Optional[int] = None) -> list:
    """Sync cache from DB."""
    _sync_cache()
    return []


def _sync_cache():
    """Reload members from DB into the in-memory mock_data cache."""
    try:
        from core.db_store import load_members
        from core import mock_data as md
        members = load_members()
        if members:
            md.MEMBERS.clear()
            md.MEMBERS.extend(members)
            md.rebuild_member_index()
    except Exception:
        pass
