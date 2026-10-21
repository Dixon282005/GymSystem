"""Business rules and calculations for Gymsis mock mode."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import logging
import time
from typing import Any, Optional

from core.mock_data import ACCESS_LOG, APP_SETTINGS, DAILY_SALES, MEMBERS
from core.db_store import save_access_event, save_sale_row, save_member

logger = logging.getLogger("GymsisBusiness")
_RECENT_MEMBER_SCANS: dict[str, tuple[str, float]] = {}

import contextvars
_CURRENT_USER_VAR: contextvars.ContextVar[str] = contextvars.ContextVar("gymsis_current_user", default="sistema")
_GLOBAL_FALLBACK_USER: str = "sistema"


def set_active_user(username: Optional[str]) -> None:
    """Set the currently logged-in username for auditing and transactions (isolated per context)."""
    global _GLOBAL_FALLBACK_USER
    val = (username or "sistema").strip()
    _CURRENT_USER_VAR.set(val)
    _GLOBAL_FALLBACK_USER = val


def get_active_user() -> str:
    """Return the currently logged-in username."""
    try:
        return _CURRENT_USER_VAR.get()
    except LookupError:
        return _GLOBAL_FALLBACK_USER


def log_action(action: str, details: Any = None, username: Optional[str] = None) -> bool:
    """Record an audit trail event for security, traceability, and operations."""
    from core import db_store

    active_user = (username or get_active_user()).strip()

    if isinstance(details, dict):
        details_str = json.dumps(details, ensure_ascii=False, default=str)
    elif details:
        details_str = str(details)
    else:
        details_str = "{}"

    log_entry = {
        "username": active_user,
        "action": action,
        "details": details_str,
        "ip_address": "127.0.0.1",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        return db_store.save_audit_log(log_entry)
    except Exception as exc:
        print(f"[AUDIT] Error guardando log: {exc}")
        return False



def _parse_date(value):
    if not value:
        raise ValueError("Fecha vacía")
    val = str(value).strip().split()[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Formato de fecha no reconocido: {value}")


def sync_member_statuses() -> int:
    """Audit and synchronize member statuses (Activo vs Moroso) based on expiration and grace days."""
    from datetime import timedelta
    today = datetime.now().date()
    grace_days = int(APP_SETTINGS.get("moroso_grace_days", 0))

    changed = 0
    for member in MEMBERS:
        if member.get("estado") == "Inactivo":
            continue

        venc_str = member.get("vencimiento", "")
        if not venc_str:
            continue

        try:
            venc_date = _parse_date(venc_str)
            is_expired = today > (venc_date + timedelta(days=grace_days))
            if is_expired and member.get("estado") != "Moroso":
                member["estado"] = "Moroso"
                try:
                    save_member(member)
                except Exception:
                    pass
                changed += 1
            elif not is_expired and member.get("estado") == "Moroso":
                member["estado"] = "Activo"
                try:
                    save_member(member)
                except Exception:
                    pass
                changed += 1
        except Exception:
            continue

    return changed


def get_weekly_attendance() -> list[dict]:
    """Calculate REAL unique member attendance for each day of the current week (Lun-Dom).
    Uses COUNT(DISTINCT cedula) to avoid false inflation from multiple entry scans by the same member.
    """
    from datetime import timedelta
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    day_labels = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    counts_by_date: dict[str, int] = {}
    scans_by_date: dict[str, int] = {}

    try:
        from core.db_store import _connect_sqlite, get_active_engine, _connect_pg
        engine = get_active_engine()
        if engine == "postgresql":
            conn = _connect_pg()
            if conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT event_time::date, count(DISTINCT cedula), count(*) 
                        FROM access_log 
                        WHERE status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED') 
                          AND event_time::date BETWEEN %s AND %s 
                        GROUP BY event_time::date
                        """,
                        (monday, sunday),
                    )
                    for r in cur.fetchall():
                        counts_by_date[str(r[0])] = int(r[1])
                        scans_by_date[str(r[0])] = int(r[2])
                conn.close()
        else:
            conn = _connect_sqlite()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT date(event_time), count(DISTINCT cedula), count(*) 
                FROM access_log 
                WHERE status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED') 
                  AND date(event_time) BETWEEN ? AND ? 
                GROUP BY date(event_time)
                """,
                (str(monday), str(sunday)),
            )
            for r in cur.fetchall():
                counts_by_date[str(r[0])] = int(r[1])
                scans_by_date[str(r[0])] = int(r[2])
            conn.close()
    except Exception as exc:
        logger.debug(f"[Dashboard] Error leyendo asistencia semanal: {exc}")

    result = []
    for i in range(7):
        target_date = monday + timedelta(days=i)
        target_str = str(target_date)
        cnt = counts_by_date.get(target_str, 0)
        scans = scans_by_date.get(target_str, 0)
        result.append({
            "dia": day_labels[i],
            "count": cnt,
            "total_scans": scans,
            "date": target_str,
        })

    return result


def get_hourly_attendance_breakdown() -> dict:
    """Analyze hourly entry distribution across operating hours (06:00 to 22:00)
    using COUNT(DISTINCT cedula) to accurately identify Peak Hours (Horas Pico) vs Quiet Hours.
    """
    hourly_counts: dict[int, dict] = {h: {"unique": 0, "total": 0} for h in range(6, 23)}

    try:
        from core.db_store import _connect_sqlite, get_active_engine, _connect_pg
        engine = get_active_engine()
        if engine == "postgresql":
            conn = _connect_pg()
            if conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            EXTRACT(HOUR FROM event_time)::integer as hora_int,
                            count(DISTINCT cedula),
                            count(*)
                        FROM access_log
                        WHERE status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED')
                        GROUP BY hora_int
                        ORDER BY hora_int ASC
                        """
                    )
                    for r in cur.fetchall():
                        h = int(r[0])
                        if h in hourly_counts:
                            hourly_counts[h] = {"unique": int(r[1]), "total": int(r[2])}
                conn.close()
        else:
            conn = _connect_sqlite()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    cast(strftime('%H', event_time) as integer) as hora_int,
                    count(DISTINCT cedula),
                    count(*)
                FROM access_log
                WHERE status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED')
                GROUP BY hora_int
                ORDER BY hora_int ASC
                """
            )
            for r in cur.fetchall():
                h = int(r[0])
                if h in hourly_counts:
                    hourly_counts[h] = {"unique": int(r[1]), "total": int(r[2])}
            conn.close()
    except Exception as exc:
        logger.debug(f"[Dashboard] Error leyendo distribución horaria: {exc}")

    hours_list = []
    max_count = 0
    peak_h = 18
    min_count = 999999
    quiet_h = 14

    morning_total = 0   # 6 - 11
    afternoon_total = 0 # 12 - 16
    evening_total = 0   # 17 - 22

    for h in range(6, 23):
        u_cnt = hourly_counts[h]["unique"]
        t_cnt = hourly_counts[h]["total"]
        if u_cnt > max_count:
            max_count = u_cnt
            peak_h = h
        if u_cnt < min_count:
            min_count = u_cnt
            quiet_h = h

        if 6 <= h <= 11:
            morning_total += u_cnt
        elif 12 <= h <= 16:
            afternoon_total += u_cnt
        else:
            evening_total += u_cnt

        label = f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"
        hours_list.append({
            "hour": h,
            "label": label,
            "hour_range": f"{h:02d}:00 - {h+1:02d}:00",
            "unique": u_cnt,
            "total": t_cnt,
        })

    shifts = [
        ("Mañana (6am - 12pm)", morning_total),
        ("Mediodía / Tarde (12pm - 5pm)", afternoon_total),
        ("Tarde / Noche (5pm - 10pm)", evening_total),
    ]
    shifts.sort(key=lambda s: s[1], reverse=True)
    best_shift = shifts[0][0]

    return {
        "hours": hours_list,
        "peak_hour": f"{peak_h:02d}:00 - {peak_h+1:02d}:00",
        "peak_count": max_count,
        "quiet_hour": f"{quiet_h:02d}:00 - {quiet_h+1:02d}:00",
        "morning_total": morning_total,
        "afternoon_total": afternoon_total,
        "evening_total": evening_total,
        "best_shift": best_shift,
    }


def get_member_schedule_analytics(limit: int = 50) -> dict:
    """Analyze which members habitually train at which time shifts (Mañana, Tarde, Noche),
    their training frequency, and last seen timestamps.
    """
    from core.mock_data import MEMBERS

    members_by_cedula = {m.get("cedula", "").strip().upper(): m for m in MEMBERS}
    habits_by_member: dict[str, dict] = {}

    try:
        from core.db_store import _connect_sqlite, get_active_engine, _connect_pg
        engine = get_active_engine()
        rows = []
        if engine == "postgresql":
            conn = _connect_pg()
            if conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 
                            cedula,
                            nombre,
                            EXTRACT(HOUR FROM event_time)::integer as hora_int,
                            count(*) as freq,
                            max(event_time) as last_seen
                        FROM access_log
                        WHERE status IN ('ENTRADA', 'PERMITIDO')
                        GROUP BY cedula, nombre, hora_int
                        ORDER BY freq DESC
                        """
                    )
                    rows = cur.fetchall()
                conn.close()
        else:
            conn = _connect_sqlite()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    cedula,
                    nombre,
                    cast(strftime('%H', event_time) as integer) as hora_int,
                    count(*) as freq,
                    max(event_time) as last_seen
                FROM access_log
                WHERE status IN ('ENTRADA', 'PERMITIDO')
                GROUP BY cedula, nombre, hora_int
                ORDER BY freq DESC
                """
            )
            rows = cur.fetchall()
            conn.close()

        for r in rows:
            ced = str(r[0]).strip().upper()
            nom = str(r[1])
            h = int(r[2])
            freq = int(r[3])
            last_dt = str(r[4])

            if ced not in habits_by_member:
                habits_by_member[ced] = {
                    "cedula": ced,
                    "nombre": nom,
                    "primary_hour": h,
                    "max_freq": freq,
                    "last_seen": last_dt,
                    "total_visits": freq,
                }
            else:
                habits_by_member[ced]["total_visits"] += freq
                if freq > habits_by_member[ced]["max_freq"]:
                    habits_by_member[ced]["primary_hour"] = h
                    habits_by_member[ced]["max_freq"] = freq

    except Exception as exc:
        logger.debug(f"[Dashboard] Error leyendo hábitos de socios: {exc}")

    morning_members = []
    afternoon_members = []
    evening_members = []
    all_habits = []

    for ced, data in habits_by_member.items():
        m_info = members_by_cedula.get(ced, {})
        data["telefono"] = m_info.get("telefono", "")
        data["plan"] = m_info.get("plan", "-")
        data["estado"] = m_info.get("estado", "Activo")
        data["entrenando"] = bool(m_info.get("entrenando", False))

        h = data["primary_hour"]
        data["habitual_time"] = f"{h:02d}:00 - {h+1:02d}:00"

        if 6 <= h <= 11:
            data["shift"] = "Mañana"
            morning_members.append(data)
        elif 12 <= h <= 16:
            data["shift"] = "Tarde"
            afternoon_members.append(data)
        else:
            data["shift"] = "Noche"
            evening_members.append(data)

        all_habits.append(data)

    all_habits.sort(key=lambda x: x["total_visits"], reverse=True)
    morning_members.sort(key=lambda x: x["total_visits"], reverse=True)
    afternoon_members.sort(key=lambda x: x["total_visits"], reverse=True)
    evening_members.sort(key=lambda x: x["total_visits"], reverse=True)

    return {
        "all": all_habits[:limit],
        "morning": morning_members[:limit],
        "afternoon": afternoon_members[:limit],
        "evening": evening_members[:limit],
    }


def get_dashboard_metrics():
    """Compute dashboard KPIs from current in-memory data and database records."""
    from core.bcv_service import bcv_service
    from core.db_store import load_membership_payments

    sync_member_statuses()

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

    allowed_events = sum(
        1 for e in ACCESS_LOG
        if e.get("status") in ("ENTRADA", "PERMITIDO")
        and (not e.get("fecha") or e.get("fecha") == today_str)
    )
    denied_events = sum(
        1 for e in ACCESS_LOG
        if e.get("status") == "DENEGADO"
        and (not e.get("fecha") or e.get("fecha") == today_str)
    )
    exits_events = sum(
        1 for e in ACCESS_LOG
        if e.get("status") == "SALIDA"
        and (not e.get("fecha") or e.get("fecha") == today_str)
    )
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
        "weekly_attendance": get_weekly_attendance(),
        "hourly_traffic": get_hourly_attendance_breakdown(),
        "member_habits": get_member_schedule_analytics(),
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
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "status": status,
        "cedula": member["cedula"] if member else cedula,
    }
    ACCESS_LOG.insert(0, event)
    save_access_event(event)
    return event


def compute_membership_urgency(member: dict | None) -> dict:
    """Calculate remaining days and urgency status color:
    - > 12 days: green (Vigente)
    - <= 12 and >= 3 days: yellow (Próximo a vencer)
    - < 3 days: red (Urgente / Vencido)
    """
    if not member:
        return {
            "days_remaining": None,
            "color": "red",
            "hex": "#EF4444",
            "label": "Sin membresía",
            "plan": "-",
        }

    plan_name = member.get("plan", "Básico")
    venc_str = member.get("vencimiento", "")
    days_remaining = None
    color = "green"
    hex_color = "#10B981"
    label = "Vigente"

    if venc_str:
        try:
            venc_date = _parse_date(venc_str)
            today = datetime.now().date()
            days_remaining = (venc_date - today).days

            if days_remaining > 12:
                color = "green"
                hex_color = "#10B981"
                label = f"{days_remaining} días restantes"
            elif days_remaining >= 3:
                color = "yellow"
                hex_color = "#F59E0B"
                label = f"¡Atención! {days_remaining} días restantes"
            elif days_remaining >= 0:
                color = "red"
                hex_color = "#EF4444"
                label = f"¡Urgente! Vence en {days_remaining} {'día' if days_remaining == 1 else 'días'}"
            else:
                color = "red"
                hex_color = "#EF4444"
                label = f"Membresía vencida hace {abs(days_remaining)} días"
        except Exception:
            pass

    return {
        "days_remaining": days_remaining,
        "color": color,
        "hex": hex_color,
        "label": label,
        "plan": plan_name,
    }


def process_nfc_scan(nfc_uid: str, min_interval: float = 0.0):
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
            "urgency": compute_membership_urgency(None),
        }
        event_bus.publish("access_scan", result)
        return result

    cedula = member.get("cedula", "")
    now = time.time()
    urgency = compute_membership_urgency(member)
    member["urgency"] = urgency

    # Anti-bounce: Prevent instantaneous entrance -> exit flip from double tapping or holding card
    if min_interval > 0.0 and cedula in _RECENT_MEMBER_SCANS:
        last_action, last_time = _RECENT_MEMBER_SCANS[cedula]
        if (now - last_time) < min_interval:
            logger.info(f"[Access] Doble toque ignorado para {cedula} (hace {now - last_time:.2f}s)")
            result = {
                "action": last_action,
                "event": None,
                "member": member,
                "allowed": True,
                "reason": f"Acceso reciente ya registrado para {member['nombre']}",
                "cooldown": True,
                "urgency": urgency,
            }
            event_bus.publish("access_scan", result)
            return result

    # 3. Case: Member is ALREADY inside the gym -> Trigger SALIDA!
    if member.get("entrenando") is True:
        event = register_access_attempt(member["cedula"], member, True, action="SALIDA")
        _RECENT_MEMBER_SCANS[cedula] = ("SALIDA", now)
        nfc_reader.beep_exit()
        audio.announce_access_exit(member["nombre"])
        result = {
            "action": "SALIDA",
            "event": event,
            "member": member,
            "allowed": True,
            "reason": "Salida registrada",
            "urgency": urgency,
        }
        event_bus.publish("access_scan", result)
        event_bus.publish("members_changed", member)
        return result

    # 4. Case: Member is OUTSIDE and wants to enter -> Validate membership
    allowed, reason = can_member_access(member)
    if allowed:
        event = register_access_attempt(member["cedula"], member, True, action="ENTRADA")
        _RECENT_MEMBER_SCANS[cedula] = ("ENTRADA", now)
        nfc_reader.beep_success()
        audio.announce_access_granted(member["nombre"], member.get("plan", ""))
        result = {
            "action": "ENTRADA",
            "event": event,
            "member": member,
            "allowed": True,
            "reason": f"¡Bienvenido, {member['nombre']}!",
            "urgency": urgency,
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
            "urgency": urgency,
        }
        event_bus.publish("access_scan", result)
        return result


def build_access_snapshot():
    """Summarize access area counters and present members list."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    present = [m for m in MEMBERS if m.get("entrenando")]
    # Allowed today counts only entrance events (ENTRADA or legacy PERMITIDO), never SALIDA
    allowed_today = sum(
        1 for e in ACCESS_LOG
        if e.get("status") in ("ENTRADA", "PERMITIDO")
        and (not e.get("fecha") or e.get("fecha") == today_str)
    )
    denied_today = sum(
        1 for e in ACCESS_LOG
        if e.get("status") == "DENEGADO"
        and (not e.get("fecha") or e.get("fecha") == today_str)
    )
    exits_today = sum(
        1 for e in ACCESS_LOG
        if e.get("status") == "SALIDA"
        and (not e.get("fecha") or e.get("fecha") == today_str)
    )

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
    from core.bcv_service import bcv_service
    from core.db_store import transaction, save_sale_row

    now = datetime.now().strftime("%H:%M")
    new_rows = []
    with transaction():
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

        total_usd = sum(float(i.get("subtotal", 0.0)) for i in cart_items)
        total_bs = bcv_service.to_bs(total_usd)
        log_action("VENTA_POS", {
            "items": [f"{i['nombre']} x{i['qty']}" for i in cart_items],
            "total_usd": total_usd,
            "total_bs": total_bs,
            "cajero": get_active_user(),
        })

    event_bus.publish("sales_changed", {"type": "pos", "rows": new_rows})
    return new_rows


def process_membership_payment(
    cedula: str,
    plan: str,
    amount: Optional[float] = None,
    days: int = 30,
    method: str = "efectivo",
    note: str = "",
    monto: Optional[float] = None,
    dias: Optional[int] = None,
    metodo: Optional[str] = None,
    nota: Optional[str] = None,
    referencia: Optional[str] = None,
    is_initial: bool = False,
) -> dict:
    """Record a membership renewal payment, update member expiration, and sync event bus."""
    from datetime import date, timedelta
    from core.mock_data import find_member_by_cedula
    from core.bcv_service import bcv_service
    from core.db_store import save_membership_payment, save_member
    from core.event_bus import event_bus

    real_amount = float(amount if amount is not None else (monto if monto is not None else 0.0))
    real_days = int(dias if dias is not None else days)
    real_method = metodo or method or "efectivo"
    real_note = nota or note or (f"Ref: {referencia}" if referencia else "")

    member = find_member_by_cedula(cedula)
    if not member:
        return {"success": False, "error": "Socio no encontrado"}

    rate = bcv_service.get_rate()
    monto_bs = bcv_service.to_bs(real_amount)

    today = date.today()
    try:
        curr_venc = datetime.strptime(member.get("vencimiento", ""), "%Y-%m-%d").date()
        if is_initial:
            # Member was just registered; do not add days a second time!
            new_venc = curr_venc
        elif curr_venc >= today:
            if real_days <= 1:
                new_venc = max(today, curr_venc)
            else:
                new_venc = curr_venc + timedelta(days=real_days)
        else:
            if real_days <= 1:
                new_venc = today
            else:
                new_venc = today + timedelta(days=real_days)
    except Exception:
        if real_days <= 1:
            new_venc = today
        else:
            new_venc = today + timedelta(days=real_days)

    from core.db_store import transaction, save_membership_payment, save_member
    with transaction():
        member["vencimiento"] = new_venc.strftime("%Y-%m-%d")
        member["plan"] = plan
        member["estado"] = "Activo"
        save_member(member)

        payment_record = {
            "cedula": member["cedula"],
            "nombre": member["nombre"],
            "plan": plan,
            "monto": float(real_amount),
            "monto_bs": float(monto_bs),
            "tasa_bcv": float(rate),
            "dias": int(real_days),
            "metodo": real_method,
            "nota": real_note,
        }
        save_membership_payment(payment_record)

        log_action("PAGO_MEMBRESIA", {
            "cedula": member["cedula"],
            "nombre": member["nombre"],
            "plan": plan,
            "monto_usd": float(real_amount),
            "monto_bs": float(monto_bs),
            "tasa_bcv": float(rate),
            "dias": int(real_days),
            "metodo": real_method,
            "referencia": real_note,
            "vencimiento": member["vencimiento"],
        })

    event_bus.publish("members_changed", member)
    event_bus.publish("sales_changed", {"type": "membership", "payment": payment_record})

    return {
        "success": True,
        "member": member,
        "payment": payment_record,
        "new_vencimiento": member["vencimiento"],
    }


def get_member_full_profile(cedula: str) -> dict:
    """Retrieve comprehensive 360-degree profile for a member:
    personal info, NFC keys, attendance metrics (habitual hour, frequent days, total visits),
    and complete financial history (membership payments and POS sales).
    """
    from collections import Counter
    from datetime import datetime, date
    from core.mock_data import find_member_by_cedula, get_member_nfc_keys, normalize_cedula
    from core.db_store import load_membership_payments, load_access_log

    norm_cedula = normalize_cedula(cedula)
    member = find_member_by_cedula(norm_cedula)
    if not member:
        return {"error": "Socio no encontrado", "cedula": norm_cedula}

    # NFC Keys
    keys = get_member_nfc_keys(norm_cedula)

    # Payments history
    payments = load_membership_payments(cedula=norm_cedula, limit=100)
    total_paid_usd = sum(float(p.get("monto", 0.0) or 0.0) for p in payments)
    total_paid_bs = sum(float(p.get("monto_bs", 0.0) or 0.0) for p in payments)

    # Access history
    access_logs = load_access_log(cedula=norm_cedula, limit=100)
    granted_logs = [a for a in access_logs if a.get("status") in ("ENTRADA", "CONCEDIDO", "PERMITIDO")]

    unique_dates = set()
    hours_counter = Counter()
    days_counter = Counter()
    day_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}

    for log in granted_logs:
        f_str = log.get("fecha", "")
        h_str = log.get("hora", "")
        if f_str:
            unique_dates.add(f_str)
            try:
                dt_obj = datetime.strptime(f_str[:10], "%Y-%m-%d").date()
                days_counter[day_map[dt_obj.weekday()]] += 1
            except Exception:
                pass
        if h_str and ":" in h_str:
            try:
                hr_int = int(h_str.split(":")[0])
                hours_counter[hr_int] += 1
            except Exception:
                pass

    total_visits = len(unique_dates)
    total_entries = len(granted_logs)

    # Habitual hour & shift
    if hours_counter:
        common_h, _ = hours_counter.most_common(1)[0]
        usual_hour_str = f"{common_h:02d}:00 - {common_h+1:02d}:00"
        if 6 <= common_h <= 11:
            usual_shift = "Mañana"
        elif 12 <= common_h <= 16:
            usual_shift = "Tarde"
        else:
            usual_shift = "Noche"
    else:
        usual_hour_str = "Sin datos suficientes"
        usual_shift = "Sin definir"

    # Most frequent days
    if days_counter:
        top_days = [d[0] for d in days_counter.most_common(2)]
        usual_days_str = ", ".join(top_days)
    else:
        usual_days_str = "Sin datos suficientes"

    # Days remaining calculation
    venc_str = member.get("vencimiento", "")
    dias_restantes = 0
    if venc_str:
        try:
            v_date = datetime.strptime(venc_str[:10], "%Y-%m-%d").date()
            dias_restantes = (v_date - date.today()).days
        except Exception:
            pass

    return {
        "member": dict(member),
        "keys": keys,
        "payments": payments,
        "access_logs": access_logs,
        "stats": {
            "total_visits": total_visits,
            "total_entries": total_entries,
            "usual_hour": usual_hour_str,
            "usual_shift": usual_shift,
            "usual_days": usual_days_str,
            "total_paid_usd": total_paid_usd,
            "total_paid_bs": total_paid_bs,
            "dias_restantes": dias_restantes,
            "last_visit": access_logs[0] if access_logs else None,
            "in_gym": bool(member.get("entrenando", False)),
        },
    }


