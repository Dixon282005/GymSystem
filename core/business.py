"""Business rules and calculations for Gymsis mock mode."""

from collections import Counter
from datetime import datetime

from core.mock_data import ACCESS_LOG, APP_SETTINGS, DAILY_SALES, MEMBERS
from core.db_store import save_access_event, save_sale_row, save_member


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def get_dashboard_metrics():
    """Compute dashboard KPIs from current in-memory data and database records."""
    from core.bcv_service import bcv_service
    from core.db_store import load_membership_payments

    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")
    alert_days = int(APP_SETTINGS.get("expiry_alert_days", 7))

    entrenando = sum(1 for m in MEMBERS if m.get("entrenando"))
    morosos = [m for m in MEMBERS if m.get("estado") == "Moroso"]
    inactivos = [m for m in MEMBERS if m.get("estado") == "Inactivo"]
    activos = [m for m in MEMBERS if m.get("estado") == "Activo"]

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

    # POS sales
    pos_income = sum(float(s.get("monto", 0)) for s in DAILY_SALES)
    total_sales = len(DAILY_SALES)

    # Membership payments recorded today
    try:
        payments = load_membership_payments(limit=500)
    except Exception:
        payments = []
    payments_today = [p for p in payments if str(p.get("fecha_pago", "")).startswith(today_str)]
    payments_income = sum(float(p.get("monto", 0)) for p in payments_today)

    daily_income = pos_income + payments_income
    bcv_rate = bcv_service.get_rate()
    daily_income_bs = bcv_service.to_bs(daily_income)

    total_transactions = total_sales + len(payments_today)
    avg_ticket = (daily_income / total_transactions) if total_transactions else 0.0

    allowed_events = sum(1 for e in ACCESS_LOG if e.get("status") in ("ENTRADA", "PERMITIDO"))
    denied_events = sum(1 for e in ACCESS_LOG if e.get("status") == "DENEGADO")
    exits_events = sum(1 for e in ACCESS_LOG if e.get("status") == "SALIDA")
    total_eval = allowed_events + denied_events
    access_success_rate = (allowed_events / total_eval * 100) if total_eval else 0.0

    return {
        "entrenando": entrenando,
        "total_members": len(MEMBERS),
        "activos": len(activos),
        "morosos": morosos,
        "inactivos": inactivos,
        "proximos_vencer": proximos,
        "plan_popular": popular,
        "ocupacion": ocupacion,
        "daily_income": daily_income,
        "daily_income_bs": daily_income_bs,
        "bcv_rate": bcv_rate,
        "total_sales": total_sales,
        "payments_count": len(payments_today),
        "avg_ticket": avg_ticket,
        "access_success_rate": access_success_rate,
        "entries_today": allowed_events,
        "exits_today": exits_events,
        "denied_today": denied_events,
    }


def can_member_access(member):
    """Return (allowed, reason) following access rules with dynamic date checking."""
    if not member:
        return False, "Tarjeta no registrada"

    estado = member.get("estado")
    if estado == "Inactivo" and not APP_SETTINGS.get("allow_inactive_access", False):
        return False, "Miembro inactivo"
    if estado == "Moroso":
        return False, "Membresía morosa"

    # Dynamic expiration check
    vencimiento_str = member.get("vencimiento")
    if vencimiento_str:
        try:
            from datetime import timedelta
            venc_date = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            grace_days = int(APP_SETTINGS.get("moroso_grace_days", 0))
            if today > (venc_date + timedelta(days=grace_days)):
                member["estado"] = "Moroso"
                save_member(member)
                return False, "Membresía vencida"
        except Exception:
            pass

    return True, "Acceso permitido"


def register_access_attempt(cedula, member, allowed, action="ENTRADA"):
    """Persist an access event in ACCESS_LOG and update training flag."""
    now = datetime.now().strftime("%H:%M")

    if action == "SALIDA":
        status = "SALIDA"
        if member:
            member["entrenando"] = False
            save_member(member)
    elif allowed:
        status = "ENTRADA"
        if member:
            member["entrenando"] = True
            save_member(member)
    else:
        status = "DENEGADO"

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


def process_nfc_scan(nfc_uid: str):
    """Process an NFC card tap: detects entrance vs exit, plays voice announcements, sounds buzzer, logs event, and publishes to EventBus."""
    from core.mock_data import find_member_by_nfc_id, find_member_by_cedula
    from core.audio_service import audio
    from core.nfc_service import nfc_reader
    from core.event_bus import event_bus

    clean_uid = (nfc_uid or "").strip()

    # 1. Lookup member by NFC UID or fallback to cedula or name
    member = find_member_by_nfc_id(clean_uid)
    if not member:
        member = find_member_by_cedula(clean_uid)
    if not member and clean_uid:
        clean_lower = clean_uid.lower()
        from core.mock_data import MEMBERS
        for m in MEMBERS:
            m_nom = (m.get("nombre") or "").strip().lower()
            if m_nom == clean_lower or m_nom.startswith(clean_lower) or clean_lower in m_nom:
                member = m
                break

    # 2. Case: Unknown member / Unregistered card
    if not member:
        reason = "Tarjeta no registrada"
        event = register_access_attempt(clean_uid, None, False, action="DENEGADO")
        nfc_reader.beep_denied()
        audio.announce_access_denied("", reason)
        result = {
            "action": "DENEGADO",
            "event": event,
            "member": None,
            "allowed": False,
            "reason": reason,
        }
        event_bus.publish("access_scan", result)
        return result

    # 3. Case: Member is ALREADY inside the gym -> Trigger SALIDA!
    if member.get("entrenando") is True:
        event = register_access_attempt(member["cedula"], member, True, action="SALIDA")
        nfc_reader.beep_exit()
        audio.announce_access_exit(member["nombre"])
        result = {
            "action": "SALIDA",
            "event": event,
            "member": member,
            "allowed": True,
            "reason": "Salida registrada",
        }
        event_bus.publish("access_scan", result)
        event_bus.publish("members_changed", member)
        return result

    # 4. Case: Member is OUTSIDE and wants to enter -> Validate membership
    allowed, reason = can_member_access(member)
    if allowed:
        event = register_access_attempt(member["cedula"], member, True, action="ENTRADA")
        nfc_reader.beep_success()
        audio.announce_access_granted(member["nombre"], member.get("plan", ""))
        result = {
            "action": "ENTRADA",
            "event": event,
            "member": member,
            "allowed": True,
            "reason": f"¡Bienvenido, {member['nombre']}!",
        }
        event_bus.publish("access_scan", result)
        event_bus.publish("members_changed", member)
        return result
    else:
        event = register_access_attempt(member["cedula"], member, False, action="DENEGADO")
        nfc_reader.beep_denied()
        audio.announce_access_denied(member["nombre"], reason)
        result = {
            "action": "DENEGADO",
            "event": event,
            "member": member,
            "allowed": False,
            "reason": reason,
        }
        event_bus.publish("access_scan", result)
        return result


def build_access_snapshot():
    """Summarize access area counters and present members list."""
    present = [m for m in MEMBERS if m.get("entrenando")]
    # Allowed today counts only entrance events (ENTRADA or legacy PERMITIDO), never SALIDA
    allowed_today = sum(1 for e in ACCESS_LOG if e.get("status") in ("ENTRADA", "PERMITIDO"))
    denied_today = sum(1 for e in ACCESS_LOG if e.get("status") == "DENEGADO")
    exits_today = sum(1 for e in ACCESS_LOG if e.get("status") == "SALIDA")

    return {
        "present": present,
        "allowed_today": allowed_today,
        "denied_today": denied_today,
        "exits_today": exits_today,
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
    """Append checkout rows to DAILY_SALES, deduct stock from inventory, publish to EventBus and return rows."""
    from core.mock_data import deduct_stock
    from core.event_bus import event_bus

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
        # Deduct sold stock in database and inventory
        deduct_stock(item["nombre"], item["qty"])
        new_rows.append(row)

    event_bus.publish("sales_changed", {"type": "pos", "rows": new_rows})
    return new_rows


def process_membership_payment(
    cedula: str,
    plan: str,
    amount: float,
    days: int = 30,
    method: str = "efectivo",
    note: str = "",
) -> dict:
    """Record a membership renewal payment, update member expiration, and sync event bus."""
    from datetime import date, timedelta
    from core.mock_data import find_member_by_cedula
    from core.bcv_service import bcv_service
    from core.db_store import save_membership_payment, save_member
    from core.event_bus import event_bus

    member = find_member_by_cedula(cedula)
    if not member:
        return {"success": False, "error": "Socio no encontrado"}

    rate = bcv_service.get_rate()
    monto_bs = bcv_service.to_bs(amount)

    today = date.today()
    try:
        curr_venc = datetime.strptime(member.get("vencimiento", ""), "%Y-%m-%d").date()
        if curr_venc >= today:
            new_venc = curr_venc + timedelta(days=days)
        else:
            new_venc = today + timedelta(days=days)
    except Exception:
        new_venc = today + timedelta(days=days)

    member["vencimiento"] = new_venc.strftime("%Y-%m-%d")
    member["plan"] = plan
    member["estado"] = "Activo"
    save_member(member)

    payment_record = {
        "cedula": member["cedula"],
        "nombre": member["nombre"],
        "plan": plan,
        "monto": float(amount),
        "monto_bs": float(monto_bs),
        "tasa_bcv": float(rate),
        "dias": int(days),
        "metodo": method,
        "nota": note,
    }
    save_membership_payment(payment_record)

    event_bus.publish("members_changed", member)
    event_bus.publish("sales_changed", {"type": "membership", "payment": payment_record})

    return {
        "success": True,
        "member": member,
        "payment": payment_record,
        "new_vencimiento": member["vencimiento"],
    }

