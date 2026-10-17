"""Mock data for the gym management system.

Includes small helper functions to centralize member lookups and updates.
"""

from datetime import datetime, timedelta

from core.db_store import (
    save_member,
    delete_member,
    save_product,
    delete_product,
    deduct_product_stock,
)

today = datetime.now()

MEMBERS = []

PLANS = {
    "VIP": {"precio": 50.00, "descripcion": "Acceso total + clases grupales"},
    "Basico": {"precio": 25.00, "descripcion": "Acceso a sala de musculacion"},
}

POS_PRODUCTS = []

WEEKLY_ATTENDANCE = [
    {"dia": "Lun", "count": 0},
    {"dia": "Mar", "count": 0},
    {"dia": "Mie", "count": 0},
    {"dia": "Jue", "count": 0},
    {"dia": "Vie", "count": 0},
    {"dia": "Sab", "count": 0},
    {"dia": "Dom", "count": 0},
]

ACCESS_LOG = []

DAILY_INCOME = 0.0
DAILY_SALES = []

APP_SETTINGS = {
    "gym_name": "Gymsis",
    "currency": "USD",
    "moroso_grace_days": 0,
    "expiry_alert_days": 7,
    "allow_inactive_access": False,
    "enable_nfc_simulation": False,
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


def find_member_by_cedula(cedula: str):
    """O(1) member lookup by cedula with prefix-agnostic fallback."""
    norm = normalize_cedula(cedula)
    if not norm:
        return None
    if norm in MEMBER_BY_CEDULA:
        return MEMBER_BY_CEDULA[norm]

    # Try matching without prefix if stored with prefix or vice-versa
    digits = "".join(ch for ch in norm if ch.isdigit())
    if digits:
        for prefix in ("", "V-", "E-", "J-", "G-", "P-", "V"):
            cand = f"{prefix}{digits}"
            if cand in MEMBER_BY_CEDULA:
                return MEMBER_BY_CEDULA[cand]
        # Also check against all members by comparing raw digit sequences
        for m in MEMBERS:
            m_digits = "".join(ch for ch in m.get("cedula", "") if ch.isdigit())
            if m_digits and m_digits == digits:
                return m

    return None


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


def register_member(cedula: str, nombre: str, plan: str = "Basico", nfc_id: str = ""):
    """Create a new active member in the in-memory store and persist to DB."""
    normalized = normalize_cedula(cedula)
    if not normalized:
        raise ValueError("Cédula inválida")
    if normalized in MEMBER_BY_CEDULA:
        raise ValueError("La cédula ya existe")

    plan_name = (plan or "Basico").strip() or "Basico"
    plan_info = PLANS.get(plan_name, {})
    plan_days = int(plan_info.get("dias", 30))

    new_member = {
        "cedula": normalized,
        "nombre": (nombre or "").strip(),
        "plan": plan_name,
        "vencimiento": (datetime.now() + timedelta(days=plan_days)).strftime("%Y-%m-%d"),
        "estado": "Activo",
        "nfc_id": (nfc_id or "").strip().upper() or f"NFC-{len(MEMBERS) + 1:04d}",
        "entrenando": False,
    }

    if not new_member["nombre"]:
        raise ValueError("Nombre inválido")

    MEMBERS.append(new_member)
    MEMBER_BY_CEDULA[normalized] = new_member
    save_member(new_member)
    return new_member


def update_member(cedula: str, updates: dict) -> dict:
    """Update fields of an existing member and persist."""
    member = find_member_by_cedula(cedula)
    if not member:
        raise ValueError("Socio no encontrado")

    if "nombre" in updates and updates["nombre"]:
        member["nombre"] = updates["nombre"].strip()
    if "plan" in updates and updates["plan"]:
        member["plan"] = updates["plan"].strip()
    if "vencimiento" in updates and updates["vencimiento"]:
        member["vencimiento"] = updates["vencimiento"].strip()
    if "estado" in updates and updates["estado"]:
        member["estado"] = updates["estado"].strip()
    if "nfc_id" in updates:
        member["nfc_id"] = normalize_nfc_id(updates["nfc_id"])
    if "entrenando" in updates:
        member["entrenando"] = bool(updates["entrenando"])

    save_member(member)
    rebuild_member_index()
    return member


def remove_member(cedula: str) -> bool:
    """Delete a member from storage and memory."""
    normalized = normalize_cedula(cedula)
    member = find_member_by_cedula(normalized)
    if not member:
        return False

    MEMBERS[:] = [m for m in MEMBERS if normalize_cedula(m["cedula"]) != normalized]
    if normalized in MEMBER_BY_CEDULA:
        del MEMBER_BY_CEDULA[normalized]

    delete_member(normalized)
    return True


def renew_member_plan(cedula: str, days: int = 30) -> dict:
    """Extend member expiry by specified days and set status to Activo."""
    member = find_member_by_cedula(cedula)
    if not member:
        raise ValueError("Socio no encontrado")

    today_date = datetime.now().date()
    current_venc_str = member.get("vencimiento", "")
    try:
        current_venc = datetime.strptime(current_venc_str, "%Y-%m-%d").date()
        base_date = max(today_date, current_venc)
    except Exception:
        base_date = today_date

    new_venc = base_date + timedelta(days=days)
    member["vencimiento"] = new_venc.strftime("%Y-%m-%d")
    member["estado"] = "Activo"

    save_member(member)
    return member


def normalize_nfc_id(nfc_id: str) -> str:
    """Normalize NFC UID: remove colons/dashes and uppercase."""
    return (nfc_id or "").replace(":", "").replace("-", "").strip().upper()


def find_member_by_nfc_id(nfc_id: str):
    """Find member by NFC tag UID or card ID."""
    clean = normalize_nfc_id(nfc_id)
    if not clean:
        return None
    for member in MEMBERS:
        tag = normalize_nfc_id(member.get("nfc_id", ""))
        if tag and tag == clean:
            return member
    return None


def update_member_nfc(cedula: str, nfc_id: str) -> bool:
    """Associate an NFC tag UID with an existing member."""
    member = find_member_by_cedula(cedula)
    if not member:
        return False
    clean = normalize_nfc_id(nfc_id)
    member["nfc_id"] = clean
    save_member(member)
    return True


# ---------------------------------------------------------------------------
# Inventory / POS Products Helpers
# ---------------------------------------------------------------------------

def add_or_update_product(data: dict) -> dict:
    """Add new product or update existing product in memory and DB."""
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El nombre del producto es obligatorio")

    precio = float(data.get("precio", 0.0))
    stock = max(0, int(data.get("stock", 0)))
    categoria = (data.get("categoria") or "General").strip()
    icono = (data.get("icono") or "INVENTORY").strip()

    prod_obj = {
        "nombre": nombre,
        "precio": precio,
        "stock": stock,
        "categoria": categoria,
        "icono": icono,
    }

    # Update in memory
    existing = next((p for p in POS_PRODUCTS if p["nombre"].strip().lower() == nombre.lower()), None)
    if existing:
        existing.update(prod_obj)
        prod_obj = existing
    else:
        POS_PRODUCTS.append(prod_obj)

    save_product(prod_obj)
    return prod_obj


def remove_product(nombre: str) -> bool:
    """Delete a product from memory and DB."""
    clean = (nombre or "").strip().lower()
    before_len = len(POS_PRODUCTS)
    POS_PRODUCTS[:] = [p for p in POS_PRODUCTS if p["nombre"].strip().lower() != clean]
    if len(POS_PRODUCTS) < before_len:
        delete_product(nombre)
        return True
    return False


def deduct_stock(nombre: str, qty: int = 1) -> bool:
    """Deduct stock in memory and database upon sale checkout."""
    clean = (nombre or "").strip().lower()
    for p in POS_PRODUCTS:
        if p["nombre"].strip().lower() == clean:
            p["stock"] = max(0, p.get("stock", 0) - qty)
            break
    deduct_product_stock(nombre, qty)
    return True
