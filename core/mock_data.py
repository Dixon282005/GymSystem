"""Mock data for the gym management system.

Includes small helper functions to centralize member lookups and updates.
"""

from datetime import datetime, timedelta

from core.db_store import save_member

today = datetime.now()

MEMBERS = [
    {
        "cedula": "V-12345678",
        "nombre": "Carlos Mendoza",
        "plan": "VIP",
        "vencimiento": (today + timedelta(days=15)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": "NFC-A001",
        "entrenando": True,
    },
    {
        "cedula": "V-23456789",
        "nombre": "Maria Rodriguez",
        "plan": "Basico",
        "vencimiento": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": "NFC-A002",
        "entrenando": True,
    },
    {
        "cedula": "V-34567890",
        "nombre": "Jose Hernandez",
        "plan": "VIP",
        "vencimiento": (today - timedelta(days=5)).strftime("%Y-%m-%d"),
        "estado": "Moroso",
        "nfc_id": "NFC-A003",
        "entrenando": False,
    },
    {
        "cedula": "V-45678901",
        "nombre": "Ana Gutierrez",
        "plan": "Basico",
        "vencimiento": (today - timedelta(days=12)).strftime("%Y-%m-%d"),
        "estado": "Moroso",
        "nfc_id": "NFC-A004",
        "entrenando": False,
    },
    {
        "cedula": "V-56789012",
        "nombre": "Luis Ramirez",
        "plan": "VIP",
        "vencimiento": (today + timedelta(days=28)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": "NFC-A005",
        "entrenando": True,
    },
    {
        "cedula": "V-67890123",
        "nombre": "Patricia Diaz",
        "plan": "Basico",
        "vencimiento": (today + timedelta(days=8)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": "NFC-A006",
        "entrenando": False,
    },
    {
        "cedula": "V-78901234",
        "nombre": "Roberto Silva",
        "plan": "VIP",
        "vencimiento": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": "NFC-A007",
        "entrenando": True,
    },
    {
        "cedula": "V-89012345",
        "nombre": "Carmen Flores",
        "plan": "Basico",
        "vencimiento": (today - timedelta(days=30)).strftime("%Y-%m-%d"),
        "estado": "Inactivo",
        "nfc_id": "NFC-A008",
        "entrenando": False,
    },
]

PLANS = {
    "VIP": {"precio": 50.00, "descripcion": "Acceso total + clases grupales"},
    "Basico": {"precio": 25.00, "descripcion": "Acceso a sala de musculacion"},
}

POS_PRODUCTS = [
    {"nombre": "Agua 500ml", "precio": 1.50, "stock": 48},
    {"nombre": "Proteina (scoop)", "precio": 3.00, "stock": 20},
    {"nombre": "Pase Diario", "precio": 5.00, "stock": 999},
    {"nombre": "Bebida Energetica", "precio": 2.50, "stock": 30},
    {"nombre": "Barra Proteica", "precio": 2.00, "stock": 25},
]

WEEKLY_ATTENDANCE = [
    {"dia": "Lun", "count": 42},
    {"dia": "Mar", "count": 38},
    {"dia": "Mie", "count": 55},
    {"dia": "Jue", "count": 47},
    {"dia": "Vie", "count": 61},
    {"dia": "Sab", "count": 33},
    {"dia": "Dom", "count": 18},
]

ACCESS_LOG = [
    {
        "nombre": "Carlos Mendoza",
        "plan": "VIP",
        "hora": "08:15",
        "status": "PERMITIDO",
        "cedula": "V-12345678",
    },
    {
        "nombre": "Jose Hernandez",
        "plan": "VIP",
        "hora": "08:22",
        "status": "DENEGADO",
        "cedula": "V-34567890",
    },
    {
        "nombre": "Maria Rodriguez",
        "plan": "Basico",
        "hora": "08:30",
        "status": "PERMITIDO",
        "cedula": "V-23456789",
    },
]

DAILY_INCOME = 127.50
DAILY_SALES = [
    {"producto": "Mensualidad VIP - Carlos M.", "monto": 50.00, "hora": "08:00"},
    {"producto": "Agua 500ml x2", "monto": 3.00, "hora": "08:16"},
    {"producto": "Pase Diario - Visitante", "monto": 5.00, "hora": "09:00"},
]

APP_SETTINGS = {
    "gym_name": "Gymsis",
    "currency": "USD",
    "moroso_grace_days": 0,
    "expiry_alert_days": 7,
    "allow_inactive_access": False,
    "enable_nfc_simulation": True,
}


def normalize_cedula(cedula):
    """Normalize cedula input for consistent lookups."""
    return (cedula or "").strip().upper()


def _build_member_index():
    return {normalize_cedula(member["cedula"]): member for member in MEMBERS}


MEMBER_BY_CEDULA = _build_member_index()


def rebuild_member_index():
    """Recompute cedula index when member list is replaced or bulk-updated."""
    MEMBER_BY_CEDULA.clear()
    MEMBER_BY_CEDULA.update(_build_member_index())


def find_member_by_cedula(cedula):
    """O(1) member lookup by cedula."""
    return MEMBER_BY_CEDULA.get(normalize_cedula(cedula))


def search_members_by_name_or_cedula(query):
    """Return members matching a partial name or cedula."""
    q = normalize_cedula(query)
    if not q:
        return []

    results = []
    for member in MEMBERS:
        cedula = normalize_cedula(member["cedula"])
        nombre = (member["nombre"] or "").upper()
        if q in cedula or q in nombre:
            results.append(member)
    return results


def register_member(cedula, nombre, plan, nfc_id):
    """Create a new active member in the in-memory store."""
    normalized = normalize_cedula(cedula)
    if not normalized:
        raise ValueError("Cedula invalida")
    if normalized in MEMBER_BY_CEDULA:
        raise ValueError("La cedula ya existe")

    from datetime import datetime, timedelta

    new_member = {
        "cedula": normalized,
        "nombre": (nombre or "").strip(),
        "plan": (plan or "Basico").strip() or "Basico",
        "vencimiento": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": (nfc_id or "").strip().upper() or f"NFC-{len(MEMBERS) + 1:04d}",
        "entrenando": False,
    }

    if not new_member["nombre"]:
        raise ValueError("Nombre invalido")

    MEMBERS.append(new_member)
    MEMBER_BY_CEDULA[normalized] = new_member
    save_member(new_member)
    return new_member
