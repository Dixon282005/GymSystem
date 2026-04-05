"""Business rules and calculations for Gymsis mock mode."""

from collections import Counter
from datetime import datetime

from core.mock_data import ACCESS_LOG, APP_SETTINGS, DAILY_SALES, MEMBERS
from core.db_store import save_access_event, save_sale_row


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def get_dashboard_metrics():
    """Compute dashboard KPIs from current in-memory data."""
    today = datetime.now().date()
    alert_days = int(APP_SETTINGS.get("expiry_alert_days", 7))

    entrenando = sum(1 for m in MEMBERS if m.get("entrenando"))
    morosos = [m for m in MEMBERS if m.get("estado") == "Moroso"]
    inactivos = [m for m in MEMBERS if m.get("estado") == "Inactivo"]

    proximos = []
    for member in MEMBERS:
        if member.get("estado") != "Activo":
            continue
        try:
            days_left = (_parse_date(member["vencimiento"]) - today).days
            if 0 <= days_left <= alert_days:
                proximos.append(member)
        except Exception:
            continue

    plans = [m.get("plan", "-") for m in MEMBERS]
    popular = Counter(plans).most_common(1)[0][0] if plans else "-"
    ocupacion = f"{entrenando}/{len(MEMBERS)}" if MEMBERS else "0/0"
    daily_income = sum(float(s.get("monto", 0)) for s in DAILY_SALES)
    total_sales = len(DAILY_SALES)
    avg_ticket = (daily_income / total_sales) if total_sales else 0.0

    allowed_events = sum(1 for e in ACCESS_LOG if e.get("status") == "PERMITIDO")
    denied_events = sum(1 for e in ACCESS_LOG if e.get("status") == "DENEGADO")
    total_events = allowed_events + denied_events
    access_success_rate = (allowed_events / total_events * 100) if total_events else 0.0

    return {
        "entrenando": entrenando,
        "morosos": morosos,
        "inactivos": inactivos,
        "proximos_vencer": proximos,
        "plan_popular": popular,
        "ocupacion": ocupacion,
        "daily_income": daily_income,
        "total_sales": total_sales,
        "avg_ticket": avg_ticket,
        "access_success_rate": access_success_rate,
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
        member["entrenando"] = True

    event = {
        "nombre": member["nombre"] if member else "Desconocido",
        "plan": member["plan"] if member else "-",
        "hora": now,
        "status": status,
        "cedula": member["cedula"] if member else cedula,
    }
    ACCESS_LOG.insert(0, event)
    save_access_event(event)
    return event


def build_access_snapshot():
    """Summarize access area counters and present members list."""
    present = [m for m in MEMBERS if m.get("entrenando")]
    allowed_today = sum(1 for e in ACCESS_LOG if e.get("status") == "PERMITIDO")
    denied_today = sum(1 for e in ACCESS_LOG if e.get("status") == "DENEGADO")

    return {
        "present": present,
        "allowed_today": allowed_today,
        "denied_today": denied_today,
        "total_events": len(ACCESS_LOG),
    }


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
        DAILY_SALES.append(row)
        save_sale_row(row)
        new_rows.append(row)
    return new_rows
