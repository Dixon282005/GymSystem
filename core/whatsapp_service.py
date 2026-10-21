"""WhatsApp integration helper for Gymsis.
Formats international phone numbers and generates wa.me links with customized reminder templates.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, date
from typing import Optional


def format_whatsapp_number(phone: str) -> str:
    """Format phone numbers for WhatsApp wa.me links.
    Handles Venezuelan local numbers (0414, 0424, 0412, 0416, 0426, 0422, etc.)
    and international numbers, stripping non-digit characters.
    """
    if not phone:
        return ""
    digits = "".join(ch for ch in str(phone).strip() if ch.isdigit())
    if not digits or len(digits) < 7:
        return ""

    # Venezuelan local format: 04141234567 (11 digits starting with 0) -> 584141234567
    if digits.startswith("0") and len(digits) >= 11:
        digits = "58" + digits[1:]
    # Venezuelan without leading 0: 4141234567 (10 digits starting with 4) -> 584141234567
    elif digits.startswith("4") and len(digits) == 10:
        digits = "58" + digits
    # 10 digits without country code -> default to +58
    elif not digits.startswith("58") and len(digits) == 10:
        digits = "58" + digits

    return digits


def generate_membership_reminder_message(member: dict) -> str:
    """Generate a personalized, polite message reminding the member of their membership status."""
    nombre = (member.get("nombre") or "socio").strip()
    plan = (member.get("plan") or "Membresía").strip()
    venc_str = (member.get("vencimiento") or "").strip()

    dias_restantes: Optional[int] = None
    if venc_str:
        try:
            v_date = datetime.strptime(venc_str[:10], "%Y-%m-%d").date()
            today = date.today()
            dias_restantes = (v_date - today).days
        except Exception:
            pass

    if dias_restantes is None:
        return (
            f"¡Hola {nombre}! Te saludamos de Gymsis para recordarte consultar el estado "
            f"de tu membresía ({plan}). ¡Te esperamos para seguir entrenando! 💪"
        )

    if dias_restantes > 1:
        return (
            f"¡Hola {nombre}! Te escribimos de Gymsis para recordarte que a tu membresía ({plan}) "
            f"le quedan {dias_restantes} días de vigencia (vence el {venc_str}). ¡Te esperamos para seguir entrenando! 💪"
        )
    elif dias_restantes == 1:
        return (
            f"¡Hola {nombre}! Te saludamos de Gymsis para recordarte que tu membresía ({plan}) "
            f"vence mañana ({venc_str}). Pasa por recepción para renovarla y seguir disfrutando de tus entrenamientos 💪."
        )
    elif dias_restantes == 0:
        return (
            f"¡Hola {nombre}! Te recordamos desde Gymsis que tu membresía ({plan}) vence HOY ({venc_str}). "
            f"Te esperamos en recepción para gestionar tu renovación sin interrupciones. ¡Que tengas un excelente día! 🏋️‍♂️"
        )
    else:
        dias_vencido = abs(dias_restantes)
        return (
            f"¡Hola {nombre}! Te escribimos de Gymsis para recordarte que tu membresía ({plan}) "
            f"venció hace {dias_vencido} día{'s' if dias_vencido > 1 else ''} ({venc_str}). "
            f"Pasa por recepción o contáctanos para reactivar tu acceso y continuar con tus metas fitness. ¡Te esperamos! 🏋️‍♀️"
        )


def get_whatsapp_url(member: dict) -> Optional[str]:
    """Return the https://wa.me/ URL for the member, or None if no valid phone number is present."""
    phone = member.get("telefono", "")
    formatted = format_whatsapp_number(phone)
    if not formatted or len(formatted) < 8:
        return None

    message = generate_membership_reminder_message(member)
    encoded_text = urllib.parse.quote(message)
    return f"https://wa.me/{formatted}?text={encoded_text}"
