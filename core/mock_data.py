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
MEMBER_NFC_KEYS = []

PLANS = {
    "Pase Diario": {"precio": 2.50, "dias": 1, "descripcion": "Entrenamiento individual por el día"},
    "Semanal": {"precio": 7.00, "dias": 7, "descripcion": "Pase semanal completo"},
    "Mensual": {"precio": 20.00, "dias": 30, "descripcion": "Acceso ilimitado a sala de pesas y máquinas"},
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


def _safe_log(action: str, details: dict):
    try:
        from core.business import log_action
        log_action(action, details)
    except Exception:
        pass


def normalize_cedula(cedula):
    """Normalize cedula input for consistent lookups."""
    return (cedula or "").strip().upper()


def _build_member_index():
    return {normalize_cedula(member["cedula"]): member for member in MEMBERS}


MEMBER_BY_CEDULA = _build_member_index()

def normalize_telefono(telefono: str | None) -> str:
    """Normalize phone numbers allowing digits and formatting symbols (+ - ( ) space)."""
    return "".join(c for c in (telefono or "") if c.isdigit() or c in "+-() ").strip()


def rebuild_member_index():
    """Recompute cedula index when member list is replaced or bulk-updated."""
    MEMBER_BY_CEDULA.clear()
    MEMBER_BY_CEDULA.update(_build_member_index())


def find_member_by_cedula(cedula: str):
    """Member lookup by cedula with in-memory canonical caching and DB fallback."""
    norm = normalize_cedula(cedula)
    if not norm:
        return None

    if norm in MEMBER_BY_CEDULA:
        return MEMBER_BY_CEDULA[norm]

    # Prefix-agnostic fallback for standard Venezuelan cedula variations
    digits = "".join(ch for ch in norm if ch.isdigit())
    if digits and (norm == digits or any(norm == f"{p}{digits}" for p in ("V-", "E-", "J-", "G-", "P-", "V", "E"))):
        for prefix in ("", "V-", "E-", "J-", "G-", "P-", "V", "E"):
            cand = f"{prefix}{digits}"
            if cand in MEMBER_BY_CEDULA:
                return MEMBER_BY_CEDULA[cand]

    try:
        from core.db_store import find_member_by_cedula as db_find_member_by_cedula
        db_member = db_find_member_by_cedula(norm)
        if db_member:
            c_norm = normalize_cedula(db_member.get("cedula", norm))
            MEMBER_BY_CEDULA[c_norm] = db_member
            if not any(normalize_cedula(m.get("cedula", "")) == c_norm for m in MEMBERS):
                MEMBERS.append(db_member)
            return db_member
    except Exception:
        pass

    return None


def search_members_by_name_or_cedula(query):
    """Return members matching a partial name or cedula, querying DB first."""
    q = normalize_cedula(query)
    if not q:
        return []

    try:
        from core.db_store import search_members as db_search_members
        results = db_search_members(q)
        if results:
            return results
    except Exception:
        pass

    results = []
    for member in MEMBERS:
        cedula = normalize_cedula(member["cedula"])
        nombre = (member["nombre"] or "").upper()
        if q in cedula or q in nombre:
            results.append(member)
    return results


def register_member(
    cedula: str,
    nombre: str,
    plan: str = "Basico",
    nfc_id: str = "",
    estado: str = "Activo",
    telefono: str = "",
    creado_por: str = "sistema",
    dias: int = 0,
    initial_payment: Optional[dict] = None,
    **kwargs,
):
    """Create a new active member in the in-memory store and persist to DB."""
    normalized = normalize_cedula(cedula)
    if not normalized:
        raise ValueError("Cédula inválida")
    if normalized in MEMBER_BY_CEDULA:
        existing = MEMBER_BY_CEDULA[normalized]
        if existing.get("estado") != "Inactivo":
            raise ValueError("La cédula ya existe")

    clean_nfc = normalize_nfc_id(nfc_id)
    if clean_nfc:
        existing_owner = find_member_by_nfc_id(clean_nfc)
        if existing_owner and normalize_cedula(existing_owner.get("cedula")) != normalized:
            raise ValueError(f"Esta llave NFC ya pertenece a {existing_owner['nombre']} (Cédula: {existing_owner['cedula']})")

    plan_name = (plan or "Basico").strip() or "Basico"
    plan_info = PLANS.get(plan_name, {})
    plan_days = int(dias) if int(dias or 0) > 0 else int(plan_info.get("dias", 30))

    today_dt = datetime.now().date()
    if plan_days <= 1:
        venc_str = today_dt.strftime("%Y-%m-%d")
    else:
        venc_str = (today_dt + timedelta(days=plan_days)).strftime("%Y-%m-%d")

    new_member = {
        "cedula": normalized,
        "nombre": (nombre or "").strip(),
        "plan": plan_name,
        "vencimiento": venc_str,
        "estado": (estado or "Activo").strip(),
        "telefono": (telefono or "").strip(),
        "nfc_id": clean_nfc or "",
        "entrenando": False,
        "creado_por": creado_por,
    }

    if not new_member["nombre"]:
        raise ValueError("Nombre inválido")

    if normalized in MEMBER_BY_CEDULA:
        MEMBER_BY_CEDULA[normalized].update(new_member)
        new_member = MEMBER_BY_CEDULA[normalized]
    else:
        MEMBERS.append(new_member)
        MEMBER_BY_CEDULA[normalized] = new_member
    save_member(new_member)

    if clean_nfc:
        try:
            register_member_nfc_key(normalized, clean_nfc, alias="Llavero Principal")
        except Exception:
            pass

    log_payload = {
        "cedula": normalized,
        "nombre": new_member["nombre"],
        "plan": plan_name,
        "nfc_id": new_member["nfc_id"],
    }
    if initial_payment:
        log_payload["monto_pago_usd"] = initial_payment.get("monto_usd", 0.0)
        log_payload["metodo"] = initial_payment.get("metodo", "efectivo")
        log_payload["referencia"] = initial_payment.get("referencia", "")

    _safe_log("REGISTRO_SOCIO", log_payload)
    return new_member


def update_member(cedula: str, updates: Optional[dict] = None, **kwargs) -> dict:
    """Update fields of an existing member and persist."""
    merged_updates = {}
    if updates and isinstance(updates, dict):
        merged_updates.update(updates)
    if kwargs:
        merged_updates.update(kwargs)

    member = find_member_by_cedula(cedula)
    if not member:
        raise ValueError("Socio no encontrado")

    if "nombre" in merged_updates and merged_updates["nombre"]:
        member["nombre"] = merged_updates["nombre"].strip()
    if "plan" in merged_updates and merged_updates["plan"]:
        member["plan"] = merged_updates["plan"].strip()
    if "telefono" in merged_updates:
        member["telefono"] = (merged_updates["telefono"] or "").strip()
    if "vencimiento" in merged_updates and merged_updates["vencimiento"]:
        member["vencimiento"] = merged_updates["vencimiento"].strip()
    if "estado" in merged_updates and merged_updates["estado"]:
        member["estado"] = merged_updates["estado"].strip()
    if "nfc_id" in merged_updates:
        cand_nfc = normalize_nfc_id(merged_updates["nfc_id"])
        if cand_nfc:
            existing_owner = find_member_by_nfc_id(cand_nfc)
            if existing_owner and normalize_cedula(existing_owner.get("cedula")) != normalize_cedula(cedula):
                raise ValueError(f"Esta llave NFC ya pertenece a {existing_owner['nombre']} (Cédula: {existing_owner['cedula']})")
        member["nfc_id"] = cand_nfc
    if "entrenando" in merged_updates:
        member["entrenando"] = bool(merged_updates["entrenando"])

    save_member(member)
    rebuild_member_index()
    _safe_log("EDICION_SOCIO", {
        "cedula": member["cedula"],
        "nombre": member.get("nombre", ""),
        "cambios": updates,
    })
    return member


def deactivate_member(cedula: str) -> bool:
    """Soft delete: deactivates a member without deleting historical payments or records."""
    normalized = normalize_cedula(cedula)
    member = find_member_by_cedula(normalized)
    if not member:
        return False

    nombre = member.get("nombre", "")
    member["estado"] = "Inactivo"
    member["entrenando"] = False
    save_member(member)
    _safe_log("DESACTIVAR_SOCIO", {"cedula": normalized, "nombre": nombre, "estado": "Inactivo"})
    return True


def reactivate_member(cedula: str) -> bool:
    """Reactivate a previously deactivated (Inactivo) member."""
    normalized = normalize_cedula(cedula)
    member = find_member_by_cedula(normalized)
    if not member:
        return False

    nombre = member.get("nombre", "")
    venc_str = member.get("vencimiento", "")
    try:
        venc_date = datetime.strptime(venc_str, "%Y-%m-%d").date()
        today_date = datetime.now().date()
        if today_date > venc_date:
            member["estado"] = "Moroso"
        else:
            member["estado"] = "Activo"
    except Exception:
        member["estado"] = "Activo"

    save_member(member)
    _safe_log("REACTIVAR_SOCIO", {"cedula": normalized, "nombre": nombre, "estado": member["estado"]})
    return True


def remove_member(cedula: str, hard_delete: bool = False) -> bool:
    """Delete or deactivate a member. Soft deletes (Inactivo) by default; purges if hard_delete=True."""
    if not hard_delete:
        return deactivate_member(cedula)

    normalized = normalize_cedula(cedula)
    member = find_member_by_cedula(normalized)
    if not member:
        return False

    nombre = member.get("nombre", "")
    MEMBERS[:] = [m for m in MEMBERS if normalize_cedula(m["cedula"]) != normalized]
    MEMBER_NFC_KEYS[:] = [k for k in MEMBER_NFC_KEYS if normalize_cedula(k.get("cedula", "")) != normalized]
    if normalized in MEMBER_BY_CEDULA:
        del MEMBER_BY_CEDULA[normalized]

    delete_member(normalized)
    _safe_log("ELIMINAR_SOCIO", {"cedula": normalized, "nombre": nombre})
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
        if current_venc >= today_date:
            if days <= 1:
                new_venc = max(today_date, current_venc)
            else:
                new_venc = current_venc + timedelta(days=days)
        else:
            if days <= 1:
                new_venc = today_date
            else:
                new_venc = today_date + timedelta(days=days)
    except Exception:
        if days <= 1:
            new_venc = today_date
        else:
            new_venc = today_date + timedelta(days=days)

    member["vencimiento"] = new_venc.strftime("%Y-%m-%d")
    member["estado"] = "Activo"

    save_member(member)
    return member


def normalize_nfc_id(nfc_id: str) -> str:
    """Normalize NFC UID: remove colons/dashes and uppercase."""
    return (nfc_id or "").replace(":", "").replace("-", "").strip().upper()


def refresh_nfc_keys_cache():
    """Refresh in-memory NFC keys list from DB."""
    try:
        from core.db_store import load_member_nfc_keys
        MEMBER_NFC_KEYS.clear()
        MEMBER_NFC_KEYS.extend(load_member_nfc_keys())
    except Exception:
        pass


def get_member_nfc_keys(cedula: str) -> list[dict]:
    """Get all registered NFC keys for a specific member."""
    norm = normalize_cedula(cedula)
    return [k for k in MEMBER_NFC_KEYS if normalize_cedula(k.get("cedula", "")) == norm]


def find_member_by_nfc_id(nfc_id: str):
    """Find member by NFC tag UID or card ID, checking cache and multi-keys first."""
    clean = normalize_nfc_id(nfc_id)
    if not clean:
        return None

    # 1. Check in multi-keys cache
    for key in MEMBER_NFC_KEYS:
        key_uid = normalize_nfc_id(key.get("nfc_id", ""))
        if key_uid and key_uid == clean:
            member = find_member_by_cedula(key.get("cedula", ""))
            if member:
                return member

    # 2. Check legacy / primary nfc_id field in MEMBERS
    for member in MEMBERS:
        tag = normalize_nfc_id(member.get("nfc_id", ""))
        if tag and tag == clean:
            return find_member_by_cedula(member.get("cedula", ""))

    # 3. Fallback to DB query
    try:
        from core.db_store import find_member_by_nfc_id as db_find_member_by_nfc_id
        db_member = db_find_member_by_nfc_id(clean)
        if db_member:
            return find_member_by_cedula(db_member.get("cedula", ""))
    except Exception:
        pass

    return None


def register_member_nfc_key(
    cedula: str, nfc_id: str = "", alias: str = "Llavero", nfc_uid: str = "", label: str = ""
) -> tuple[bool, str]:
    from core.db_store import add_member_nfc_key as db_add_key
    target_uid = nfc_id or nfc_uid
    target_alias = alias or label or "Llavero"
    ok, msg = db_add_key(cedula, target_uid, target_alias)
    if ok:
        refresh_nfc_keys_cache()
        _safe_log("VINCULAR_LLAVE_NFC", {"cedula": cedula, "nfc_id": target_uid, "alias": target_alias})
    return ok, msg


def update_member_nfc_key_entry(key_id: int, new_nfc_id: str, new_alias: str) -> tuple[bool, str]:
    from core.db_store import update_member_nfc_key as db_update_key
    ok, msg = db_update_key(key_id, new_nfc_id, new_alias)
    if ok:
        refresh_nfc_keys_cache()
        _safe_log("EDITAR_LLAVE_NFC", {"id": key_id, "nfc_id": new_nfc_id, "alias": new_alias})
    return ok, msg


def delete_member_nfc_key_entry(key_id: int) -> bool:
    from core.db_store import delete_member_nfc_key as db_del_key
    ok = db_del_key(key_id)
    if ok:
        refresh_nfc_keys_cache()
        _safe_log("ELIMINAR_LLAVE_NFC", {"id": key_id})
    return ok


def update_member_nfc(cedula: str, nfc_id: str) -> bool:
    """Associate an NFC tag UID with an existing member."""
    member = find_member_by_cedula(cedula)
    if not member:
        return False
    clean = normalize_nfc_id(nfc_id)
    member["nfc_id"] = clean
    save_member(member)
    # Also register as a key if not already there
    try:
        register_member_nfc_key(cedula, clean, alias="Llavero Principal")
    except Exception:
        pass
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
    _safe_log("GUARDAR_PRODUCTO", prod_obj)
    return prod_obj


def rename_and_update_product(old_name: str, data: dict) -> dict:
    """Update a product with support for renaming its name."""
    from core.db_store import rename_product as db_rename_product
    old_clean = (old_name or "").strip()
    new_nombre = (data.get("nombre") or "").strip()
    if not new_nombre:
        raise ValueError("El nuevo nombre del producto es obligatorio")

    if not old_clean or old_clean.lower() == new_nombre.lower():
        return add_or_update_product(data)

    precio = float(data.get("precio", 0.0))
    stock = max(0, int(data.get("stock", 0)))
    categoria = (data.get("categoria") or "General").strip()
    icono = (data.get("icono") or "INVENTORY").strip()

    prod_obj = {
        "nombre": new_nombre,
        "precio": precio,
        "stock": stock,
        "categoria": categoria,
        "icono": icono,
    }

    # Update in memory
    matched = False
    for p in POS_PRODUCTS:
        if p["nombre"].strip().lower() == old_clean.lower():
            p.update(prod_obj)
            matched = True
            break
    if not matched:
        POS_PRODUCTS.append(prod_obj)

    db_rename_product(old_clean, prod_obj)
    _safe_log("GUARDAR_PRODUCTO", {"accion": "renombrar", "anterior": old_clean, "nuevo": prod_obj})
    return prod_obj


def remove_product(nombre: str) -> bool:
    """Delete a product from memory and DB."""
    clean = (nombre or "").strip().lower()
    before_len = len(POS_PRODUCTS)
    POS_PRODUCTS[:] = [p for p in POS_PRODUCTS if p["nombre"].strip().lower() != clean]
    if len(POS_PRODUCTS) < before_len:
        delete_product(nombre)
        _safe_log("ELIMINAR_PRODUCTO", {"nombre": nombre})
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
