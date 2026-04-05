"""Business rules and calculations for Gymsis."""

from collections import Counter
from datetime import datetime

from core.mock_data import APP_SETTINGS, PLANS
from core.repositories import (
    AccessRepository,
    MemberRepository,
    SalesRepository,
    compute_plan_popularity,
)
from core.db_store import expire_memberships


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def run_auto_expiration() -> list[dict]:
    """Run the automatic membership expiration check.

    Returns list of members whose status changed.
    """
    grace = int(APP_SETTINGS.get("moroso_grace_days", 0))
    return expire_memberships(grace_days=grace)


def get_expiry_notifications() -> list[dict]:
    """Return members whose membership expires within the alert window.

    Each entry has extra key 'days_left'.
    """
    today = datetime.now().date()
    alert_days = int(APP_SETTINGS.get("expiry_alert_days", 7))
    notifications = []

    for member in MemberRepository.list_all():
        if member.get("estado") != "Activo":
            continue
        try:
            venc = _parse_date(member["vencimiento"])
            days_left = (venc - today).days
            if 0 <= days_left <= alert_days:
                notifications.append({**member, "days_left": days_left})
        except Exception:
            continue

    notifications.sort(key=lambda m: m.get("days_left", 999))
    return notifications


def get_dashboard_metrics():
    """Compute dashboard KPIs from current in-memory data."""
    members = MemberRepository.list_all()
    access_log = AccessRepository.list_recent(limit=2000)
    sales = SalesRepository.list_recent(limit=2000)

    today = datetime.now().date()
    alert_days = int(APP_SETTINGS.get("expiry_alert_days", 7))

    entrenando = sum(1 for m in members if m.get("entrenando"))
    morosos = [m for m in members if m.get("estado") == "Moroso"]
    inactivos = [m for m in members if m.get("estado") == "Inactivo"]

    proximos = []
    for member in members:
        if member.get("estado") != "Activo":
            continue
        try:
            days_left = (_parse_date(member["vencimiento"]) - today).days
            if 0 <= days_left <= alert_days:
                proximos.append({**member, "days_left": days_left})
        except Exception:
            continue

    proximos.sort(key=lambda m: m.get("days_left", 999))

    popular = compute_plan_popularity()
    ocupacion = f"{entrenando}/{len(members)}" if members else "0/0"
    daily_income = sum(float(s.get("monto", 0)) for s in sales)
    total_sales = len(sales)
    avg_ticket = (daily_income / total_sales) if total_sales else 0.0

    allowed_events = sum(1 for e in access_log if e.get("status") == "PERMITIDO")
    denied_events = sum(1 for e in access_log if e.get("status") == "DENEGADO")
    total_events = allowed_events + denied_events
    access_success_rate = (allowed_events / total_events * 100) if total_events else 0.0

    # Weekly attendance from real access events (PERMITIDO) over last 7 days.
    day_labels = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    counts = Counter()
    for event in access_log:
        try:
            if event.get("status") != "PERMITIDO":
                continue
            fecha = event.get("fecha")
            if fecha:
                event_date = datetime.strptime(fecha, "%Y-%m-%d").date()
                if (today - event_date).days > 6:
                    continue
                weekday = event_date.weekday()
            else:
                weekday = today.weekday()
            counts[weekday] += 1
        except Exception:
            continue

    weekly_attendance = [
        {"dia": day_labels[idx], "count": int(counts.get(idx, 0))}
        for idx in range(7)
    ]

    return {
        "entrenando": entrenando,
        "morosos": morosos,
        "inactivos": inactivos,
        "proximos_vencer": proximos,
        "plan_popular": popular,
        "ocupacion": ocupacion,
        "total_members": len(members),
        "daily_income": daily_income,
        "total_sales": total_sales,
        "avg_ticket": avg_ticket,
        "access_success_rate": access_success_rate,
        "weekly_attendance": weekly_attendance,
    }


def can_member_access(member):
    """Return (allowed, reason) following access rules."""
    if not member:
        return False, "Miembro no encontrado"

    estado = member.get("estado")
    if estado == "Inactivo" and not APP_SETTINGS.get("allow_inactive_access", False):
        return False, "Miembro inactivo"
    if estado == "Moroso":
        return False, "Membresia morosa"

    return True, "Acceso permitido"


def register_access_attempt(cedula, member, allowed):
    """Persist a simulated access event in ACCESS_LOG and toggle training flag."""
    now = datetime.now().strftime("%H:%M")
    status = "PERMITIDO" if allowed else "DENEGADO"

    if member and allowed:
        MemberRepository.set_training_status(member["cedula"], True)

    event = {
        "nombre": member["nombre"] if member else "Desconocido",
        "plan": member["plan"] if member else "-",
        "hora": now,
        "status": status,
        "cedula": member["cedula"] if member else cedula,
    }
    AccessRepository.add_event(event)
    return event


def build_access_snapshot():
    """Summarize access area counters and present members list."""
    return AccessRepository.snapshot()


def compute_sales_summary(cart_items):
    """Return subtotal and total for POS checkout."""
    subtotal = sum(item["subtotal"] for item in cart_items)
    tax_rate = 0.0
    taxes = subtotal * tax_rate
    total = subtotal + taxes
    return {
        "subtotal": subtotal,
        "taxes": taxes,
        "total": total,
    }


def register_sale_rows(cart_items):
    """Append checkout rows to DAILY_SALES and return generated rows."""
    now = datetime.now().strftime("%H:%M")
    new_rows = []
    for item in cart_items:
        row = {
            "producto": f"{item['nombre']} x{item['qty']}",
            "monto": item["subtotal"],
            "hora": now,
        }
        SalesRepository.add_row(row)
        new_rows.append(row)
    return new_rows
