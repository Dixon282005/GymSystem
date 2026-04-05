"""PostgreSQL persistence helpers with graceful fallback for local desktop mode."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta


LOCAL_ROLE_PERMISSIONS = {
    "admin": {
        "view_dashboard",
        "view_access",
        "view_members",
        "view_pos",
        "view_settings",
        "manage_users",
        "manage_pos",
    },
    "staff": {"view_dashboard", "view_access", "view_members", "view_pos", "manage_pos"},
    "viewer": {"view_dashboard", "view_access"},
}

_LOCAL_USERS: dict[str, dict] = {}
_LOCAL_PAYMENTS: list[dict] = []


def is_db_enabled() -> bool:
    return os.getenv("GYMSIS_USE_DB", "false").strip().lower() in {"1", "true", "yes", "on"}


def _get_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://gymsis:gymsis_dev@localhost:5433/gymsis")


@contextmanager
def _db_connection():
    """Context manager that guarantees the connection is closed after use."""
    conn = None
    try:
        import psycopg
        conn = psycopg.connect(_get_database_url(), autocommit=True)
        yield conn
    except ImportError:
        yield None
    except Exception:
        yield None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _hash_password(password: str) -> str:
    salt = os.getenv("GYMSIS_PASSWORD_SALT", "gymsis-dev-salt")
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return digest


def _verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(_hash_password(password), hashed or "")


def _ensure_local_admin() -> None:
    if "admin" in _LOCAL_USERS:
        return

    admin_password = os.getenv("GYMSIS_ADMIN_PASSWORD", "admin123")
    _LOCAL_USERS["admin"] = {
        "username": "admin",
        "password_hash": _hash_password(admin_password),
        "role": "admin",
        "is_active": True,
    }


def _ensure_schema(conn) -> None:
    schema_sql = """
    CREATE TABLE IF NOT EXISTS members (
        cedula TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        plan TEXT NOT NULL,
        vencimiento DATE NOT NULL,
        estado TEXT NOT NULL,
        nfc_id TEXT NOT NULL UNIQUE,
        entrenando BOOLEAN NOT NULL DEFAULT FALSE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS access_log (
        id BIGSERIAL PRIMARY KEY,
        cedula TEXT NOT NULL,
        nombre TEXT NOT NULL,
        plan TEXT NOT NULL,
        status TEXT NOT NULL,
        event_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS sales (
        id BIGSERIAL PRIMARY KEY,
        producto TEXT NOT NULL,
        monto NUMERIC(12, 2) NOT NULL,
        sold_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS pos_products (
        id BIGSERIAL PRIMARY KEY,
        nombre TEXT NOT NULL UNIQUE,
        precio NUMERIC(12, 2) NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS roles (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS permissions (
        id SERIAL PRIMARY KEY,
        code TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
        permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
        PRIMARY KEY(role_id, permission_id)
    );

    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role_id INTEGER NOT NULL REFERENCES roles(id),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS membership_payments (
        id BIGSERIAL PRIMARY KEY,
        cedula TEXT NOT NULL,
        plan TEXT NOT NULL,
        monto NUMERIC(12, 2) NOT NULL,
        fecha_pago TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE NOT NULL,
        metodo TEXT NOT NULL DEFAULT 'efectivo',
        nota TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_access_log_event_time ON access_log(event_time DESC);
    CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at DESC);
    CREATE INDEX IF NOT EXISTS idx_pos_products_active ON pos_products(is_active);
    CREATE INDEX IF NOT EXISTS idx_membership_payments_cedula ON membership_payments(cedula);
    CREATE INDEX IF NOT EXISTS idx_membership_payments_fecha ON membership_payments(fecha_pago DESC);
    """
    with conn.cursor() as cur:
        cur.execute(schema_sql)


def _table_has_rows(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1);")
        row = cur.fetchone()
    return bool(row and row[0])


def _seed_security_baseline(conn) -> None:
    role_names = ["admin", "staff", "viewer"]
    permission_codes = [
        "view_dashboard",
        "view_access",
        "view_members",
        "view_pos",
        "view_settings",
        "manage_users",
        "manage_pos",
    ]

    with conn.cursor() as cur:
        for role in role_names:
            cur.execute("INSERT INTO roles (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (role,))

        for code in permission_codes:
            cur.execute("INSERT INTO permissions (code) VALUES (%s) ON CONFLICT (code) DO NOTHING;", (code,))

        grants = {
            "admin": set(permission_codes),
            "staff": {"view_dashboard", "view_access", "view_members", "view_pos", "manage_pos"},
            "viewer": {"view_dashboard", "view_access"},
        }

        for role_name, perm_codes in grants.items():
            cur.execute("SELECT id FROM roles WHERE name = %s;", (role_name,))
            role_id = cur.fetchone()[0]
            for perm_code in perm_codes:
                cur.execute("SELECT id FROM permissions WHERE code = %s;", (perm_code,))
                perm_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    VALUES (%s, %s)
                    ON CONFLICT (role_id, permission_id) DO NOTHING;
                    """,
                    (role_id, perm_id),
                )

        admin_user = os.getenv("GYMSIS_ADMIN_USER", "admin")
        admin_password = os.getenv("GYMSIS_ADMIN_PASSWORD", "admin123")
        admin_hash = _hash_password(admin_password)

        cur.execute("SELECT id FROM roles WHERE name = 'admin';")
        admin_role_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO users (username, password_hash, role_id, is_active)
            VALUES (%s, %s, %s, TRUE)
            ON CONFLICT (username) DO UPDATE SET
                role_id = EXCLUDED.role_id,
                is_active = TRUE,
                updated_at = NOW();
            """,
            (admin_user, admin_hash, admin_role_id),
        )


def bootstrap_database() -> bool:
    """Create core tables and seed from in-memory mock data if DB is enabled."""
    if not is_db_enabled():
        return False

    with _db_connection() as conn:
        if not conn:
            return False

        _ensure_schema(conn)
        _seed_security_baseline(conn)

        try:
            from core.mock_data import ACCESS_LOG, APP_SETTINGS, DAILY_SALES, MEMBERS, POS_PRODUCTS
        except Exception:
            return True

        if not _table_has_rows(conn, "members"):
            for member in MEMBERS:
                save_member(member)

        if not _table_has_rows(conn, "access_log"):
            for event in ACCESS_LOG:
                save_access_event(event)

        if not _table_has_rows(conn, "sales"):
            for sale in DAILY_SALES:
                save_sale_row(sale)

        if not _table_has_rows(conn, "pos_products"):
            for product in POS_PRODUCTS:
                save_pos_product(product)

        if not _table_has_rows(conn, "app_settings"):
            save_settings(APP_SETTINGS)

    return True


def load_members() -> list[dict]:
    if not is_db_enabled():
        return []

    with _db_connection() as conn:
        if not conn:
            return []

        query = """
        SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando
        FROM members
        ORDER BY nombre ASC;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return [
        {
            "cedula": row[0],
            "nombre": row[1],
            "plan": row[2],
            "vencimiento": row[3].strftime("%Y-%m-%d") if row[3] else "",
            "estado": row[4],
            "nfc_id": row[5],
            "entrenando": bool(row[6]),
        }
        for row in rows
    ]


def load_access_log(limit: int = 300) -> list[dict]:
    if not is_db_enabled():
        return []

    with _db_connection() as conn:
        if not conn:
            return []

        query = """
        SELECT nombre, plan, status, cedula, event_time
        FROM access_log
        ORDER BY event_time DESC
        LIMIT %s;
        """
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

    return [
        {
            "nombre": row[0],
            "plan": row[1],
            "status": row[2],
            "cedula": row[3],
            "hora": row[4].strftime("%H:%M") if row[4] else "",
            "fecha": row[4].strftime("%Y-%m-%d") if row[4] else "",
        }
        for row in rows
    ]


def load_sales(limit: int = 500) -> list[dict]:
    if not is_db_enabled():
        return []

    with _db_connection() as conn:
        if not conn:
            return []

        query = """
        SELECT producto, monto, sold_at
        FROM sales
        ORDER BY sold_at DESC
        LIMIT %s;
        """
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

    return [
        {
            "producto": row[0],
            "monto": float(row[1]),
            "hora": row[2].strftime("%H:%M") if row[2] else "",
        }
        for row in rows
    ]


def load_settings() -> dict:
    if not is_db_enabled():
        return {}

    with _db_connection() as conn:
        if not conn:
            return {}

        query = "SELECT key, value FROM app_settings;"
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return {key: value for key, value in rows}


def hydrate_mock_data_from_db() -> bool:
    """Load DB data into in-memory lists so current UI modules consume persisted state."""
    if not is_db_enabled():
        return False

    members = load_members()
    access_log = load_access_log()
    sales = load_sales()
    settings = load_settings()

    try:
        from core import mock_data as md
    except Exception:
        return False

    if members:
        md.MEMBERS.clear()
        md.MEMBERS.extend(members)
        md.rebuild_member_index()

    if access_log:
        md.ACCESS_LOG.clear()
        md.ACCESS_LOG.extend(access_log)

    if sales:
        md.DAILY_SALES.clear()
        md.DAILY_SALES.extend(sales)

    if settings:
        md.APP_SETTINGS.update(settings)

    return bool(members or access_log or sales or settings)


def save_member(member: dict) -> bool:
    if not is_db_enabled():
        return False

    with _db_connection() as conn:
        if not conn:
            return False

        query = """
        INSERT INTO members (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (cedula) DO UPDATE SET
            nombre = EXCLUDED.nombre,
            plan = EXCLUDED.plan,
            vencimiento = EXCLUDED.vencimiento,
            estado = EXCLUDED.estado,
            nfc_id = EXCLUDED.nfc_id,
            entrenando = EXCLUDED.entrenando,
            updated_at = NOW();
        """

        values = (
            member.get("cedula"),
            member.get("nombre", ""),
            member.get("plan", "Basico"),
            member.get("vencimiento"),
            member.get("estado", "Activo"),
            member.get("nfc_id", ""),
            bool(member.get("entrenando", False)),
        )

        try:
            with conn.cursor() as cur:
                cur.execute(query, values)
            return True
        except Exception:
            return False


def save_access_event(event: dict) -> bool:
    if not is_db_enabled():
        return False

    with _db_connection() as conn:
        if not conn:
            return False

        query = """
        INSERT INTO access_log (cedula, nombre, plan, status, event_time)
        VALUES (%s, %s, %s, %s, NOW());
        """
        values = (
            event.get("cedula", ""),
            event.get("nombre", "Desconocido"),
            event.get("plan", "-"),
            event.get("status", "DENEGADO"),
        )

        try:
            with conn.cursor() as cur:
                cur.execute(query, values)
            return True
        except Exception:
            return False


def save_sale_row(row: dict) -> bool:
    if not is_db_enabled():
        return False

    with _db_connection() as conn:
        if not conn:
            return False

        query = """
        INSERT INTO sales (producto, monto, sold_at)
        VALUES (%s, %s, NOW());
        """
        values = (row.get("producto", ""), float(row.get("monto", 0)))

        try:
            with conn.cursor() as cur:
                cur.execute(query, values)
            return True
        except Exception:
            return False


def save_settings(settings: dict) -> bool:
    if not is_db_enabled():
        return False

    with _db_connection() as conn:
        if not conn:
            return False

        query = """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (%s, %s::jsonb, NOW())
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = NOW();
        """

        try:
            with conn.cursor() as cur:
                for key, value in settings.items():
                    cur.execute(query, (key, json.dumps(value)))
            return True
        except Exception:
            return False


# ── Roles / Users ─────────────────────────────────────────────────────

def list_roles() -> list[str]:
    if not is_db_enabled():
        return sorted(LOCAL_ROLE_PERMISSIONS.keys())

    with _db_connection() as conn:
        if not conn:
            return ["admin", "staff", "viewer"]

        with conn.cursor() as cur:
            cur.execute("SELECT name FROM roles ORDER BY name;")
            rows = cur.fetchall()
    return [row[0] for row in rows]


def list_users() -> list[dict]:
    if not is_db_enabled():
        _ensure_local_admin()
        return [
            {"username": u["username"], "role": u["role"], "is_active": bool(u["is_active"])}
            for u in sorted(_LOCAL_USERS.values(), key=lambda row: row["username"])
        ]

    with _db_connection() as conn:
        if not conn:
            return []

        query = """
        SELECT u.username, r.name, u.is_active
        FROM users u
        JOIN roles r ON r.id = u.role_id
        ORDER BY u.username;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    return [{"username": r[0], "role": r[1], "is_active": bool(r[2])} for r in rows]


def create_user(username: str, password: str, role: str) -> tuple[bool, str]:
    if not username or not password:
        return False, "Usuario y clave son obligatorios"
    if not is_db_enabled():
        _ensure_local_admin()
        normalized = username.strip().lower()
        if role not in LOCAL_ROLE_PERMISSIONS:
            return False, "Rol invalido"
        _LOCAL_USERS[normalized] = {
            "username": normalized,
            "password_hash": _hash_password(password),
            "role": role,
            "is_active": True,
        }
        return True, "Usuario guardado en memoria"

    with _db_connection() as conn:
        if not conn:
            return False, "Sin conexion a DB"

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM roles WHERE name = %s;", (role,))
                role_row = cur.fetchone()
                if not role_row:
                    return False, "Rol invalido"

                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, role_id, is_active)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT (username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        role_id = EXCLUDED.role_id,
                        is_active = TRUE,
                        updated_at = NOW();
                    """,
                    (username.strip().lower(), _hash_password(password), role_row[0]),
                )
            return True, "Usuario guardado"
        except Exception:
            return False, "No se pudo guardar el usuario"


def set_user_active(username: str, is_active: bool) -> tuple[bool, str]:
    if not is_db_enabled():
        _ensure_local_admin()
        normalized = username.strip().lower()
        user = _LOCAL_USERS.get(normalized)
        if not user:
            return False, "Usuario no encontrado"
        user["is_active"] = bool(is_active)
        return True, "Estado actualizado en memoria"

    with _db_connection() as conn:
        if not conn:
            return False, "Sin conexion a DB"

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET is_active = %s, updated_at = NOW() WHERE username = %s;",
                    (bool(is_active), username.strip().lower()),
                )
                if cur.rowcount == 0:
                    return False, "Usuario no encontrado"
            return True, "Estado actualizado"
        except Exception:
            return False, "No se pudo actualizar estado"


def delete_user(username: str) -> tuple[bool, str]:
    if not is_db_enabled():
        _ensure_local_admin()
        normalized = username.strip().lower()
        if normalized == "admin":
            return False, "No puedes borrar el admin base"
        if normalized not in _LOCAL_USERS:
            return False, "Usuario no encontrado"
        del _LOCAL_USERS[normalized]
        return True, "Usuario eliminado en memoria"
    if username.strip().lower() == "admin":
        return False, "No puedes borrar el admin base"

    with _db_connection() as conn:
        if not conn:
            return False, "Sin conexion a DB"

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE username = %s;", (username.strip().lower(),))
                if cur.rowcount == 0:
                    return False, "Usuario no encontrado"
            return True, "Usuario eliminado"
        except Exception:
            return False, "No se pudo eliminar usuario"


# ── POS Products ──────────────────────────────────────────────────────

def load_pos_products(active_only: bool = True) -> list[dict]:
    if not is_db_enabled():
        return []

    with _db_connection() as conn:
        if not conn:
            return []

        where = "WHERE is_active = TRUE" if active_only else ""
        query = f"""
        SELECT nombre, precio, stock, is_active
        FROM pos_products
        {where}
        ORDER BY nombre ASC;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return [
        {
            "nombre": row[0],
            "precio": float(row[1]),
            "stock": int(row[2]),
            "is_active": bool(row[3]),
        }
        for row in rows
    ]


def save_pos_product(product: dict) -> tuple[bool, str]:
    if not is_db_enabled():
        return False, "DB no habilitada"

    with _db_connection() as conn:
        if not conn:
            return False, "Sin conexion a DB"

        name = (product.get("nombre") or "").strip()
        if not name:
            return False, "Nombre requerido"

        try:
            price = float(product.get("precio", 0))
            stock = int(product.get("stock", 0))
        except Exception:
            return False, "Precio o stock invalido"

        is_active = bool(product.get("is_active", True))

        query = """
        INSERT INTO pos_products (nombre, precio, stock, is_active, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (nombre) DO UPDATE SET
            precio = EXCLUDED.precio,
            stock = EXCLUDED.stock,
            is_active = EXCLUDED.is_active,
            updated_at = NOW();
        """

        try:
            with conn.cursor() as cur:
                cur.execute(query, (name, price, stock, is_active))
            return True, "Producto guardado"
        except Exception:
            return False, "No se pudo guardar producto"


def delete_pos_product(nombre: str) -> tuple[bool, str]:
    if not is_db_enabled():
        return False, "DB no habilitada"

    with _db_connection() as conn:
        if not conn:
            return False, "Sin conexion a DB"

        query = "UPDATE pos_products SET is_active = FALSE, updated_at = NOW() WHERE nombre = %s;"
        try:
            with conn.cursor() as cur:
                cur.execute(query, (nombre.strip(),))
                if cur.rowcount == 0:
                    return False, "Producto no encontrado"
            return True, "Producto desactivado"
        except Exception:
            return False, "No se pudo desactivar producto"


# ── Auth ──────────────────────────────────────────────────────────────

def authenticate_user(username: str, password: str) -> dict | None:
    if not is_db_enabled():
        _ensure_local_admin()
        user = _LOCAL_USERS.get(username.strip().lower())
        if not user:
            return None
        if not user.get("is_active"):
            return None
        if not _verify_password(password, user.get("password_hash", "")):
            return None
        return {"username": user["username"], "role": user["role"]}

    with _db_connection() as conn:
        if not conn:
            return None

        query = """
        SELECT u.username, u.password_hash, u.is_active, r.name
        FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE u.username = %s;
        """
        with conn.cursor() as cur:
            cur.execute(query, (username.strip().lower(),))
            row = cur.fetchone()

    if not row:
        return None
    if not row[2]:
        return None
    if not _verify_password(password, row[1]):
        return None

    return {"username": row[0], "role": row[3]}


def get_user_permissions(username: str) -> set[str]:
    if not is_db_enabled():
        _ensure_local_admin()
        user = _LOCAL_USERS.get(username.strip().lower())
        if not user:
            return set()
        return set(LOCAL_ROLE_PERMISSIONS.get(user.get("role", "viewer"), set()))

    with _db_connection() as conn:
        if not conn:
            return set()

        query = """
        SELECT p.code
        FROM users u
        JOIN roles r ON r.id = u.role_id
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE u.username = %s AND u.is_active = TRUE;
        """
        with conn.cursor() as cur:
            cur.execute(query, (username.strip().lower(),))
            rows = cur.fetchall()
    return {row[0] for row in rows}


# ── Membership Payments ───────────────────────────────────────────────

def save_membership_payment(payment: dict) -> tuple[bool, str]:
    """Persist a membership payment and update the member's expiry date."""
    cedula = (payment.get("cedula") or "").strip().upper()
    plan = (payment.get("plan") or "").strip()
    if not cedula or not plan:
        return False, "Cedula y plan son obligatorios"

    try:
        monto = float(payment.get("monto", 0))
    except (ValueError, TypeError):
        return False, "Monto invalido"

    dias = int(payment.get("dias", 30))
    metodo = (payment.get("metodo") or "efectivo").strip()
    nota = (payment.get("nota") or "").strip()
    hoy = datetime.now().date()
    fecha_fin = hoy + timedelta(days=dias)

    if not is_db_enabled():
        _LOCAL_PAYMENTS.append({
            "cedula": cedula,
            "plan": plan,
            "monto": monto,
            "fecha_pago": datetime.now().isoformat(),
            "fecha_inicio": hoy.isoformat(),
            "fecha_fin": fecha_fin.isoformat(),
            "metodo": metodo,
            "nota": nota,
        })
        return True, "Pago registrado en memoria"

    with _db_connection() as conn:
        if not conn:
            return False, "Sin conexion a DB"

        query = """
        INSERT INTO membership_payments (cedula, plan, monto, fecha_inicio, fecha_fin, metodo, nota)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with conn.cursor() as cur:
                cur.execute(query, (cedula, plan, monto, hoy, fecha_fin, metodo, nota))
                # Update member expiry and reactivate
                cur.execute(
                    """
                    UPDATE members SET
                        vencimiento = %s,
                        plan = %s,
                        estado = 'Activo',
                        updated_at = NOW()
                    WHERE cedula = %s;
                    """,
                    (fecha_fin, plan, cedula),
                )
            return True, "Pago registrado"
        except Exception as exc:
            return False, f"Error al guardar pago: {exc}"


def load_membership_payments(cedula: str | None = None, limit: int = 200) -> list[dict]:
    if not is_db_enabled():
        payments = list(_LOCAL_PAYMENTS)
        if cedula:
            payments = [p for p in payments if p.get("cedula") == cedula.strip().upper()]
        return payments[:limit]

    with _db_connection() as conn:
        if not conn:
            return []

        if cedula:
            query = """
            SELECT cedula, plan, monto, fecha_pago, fecha_inicio, fecha_fin, metodo, nota
            FROM membership_payments
            WHERE cedula = %s
            ORDER BY fecha_pago DESC
            LIMIT %s;
            """
            params = (cedula.strip().upper(), limit)
        else:
            query = """
            SELECT cedula, plan, monto, fecha_pago, fecha_inicio, fecha_fin, metodo, nota
            FROM membership_payments
            ORDER BY fecha_pago DESC
            LIMIT %s;
            """
            params = (limit,)

        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [
        {
            "cedula": r[0],
            "plan": r[1],
            "monto": float(r[2]),
            "fecha_pago": r[3].strftime("%Y-%m-%d %H:%M") if r[3] else "",
            "fecha_inicio": r[4].strftime("%Y-%m-%d") if r[4] else "",
            "fecha_fin": r[5].strftime("%Y-%m-%d") if r[5] else "",
            "metodo": r[6],
            "nota": r[7],
        }
        for r in rows
    ]


# ── Auto-Expiration ──────────────────────────────────────────────────

def expire_memberships(grace_days: int = 0) -> list[dict]:
    """Check all active members and change status based on expiry.

    - Expired ≤ grace_days ago → Moroso
    - Expired > grace_days ago → Inactivo
    Returns list of members whose status changed.
    """
    today = datetime.now().date()
    changed: list[dict] = []

    try:
        from core import mock_data as md
    except Exception:
        return changed

    for member in list(md.MEMBERS):
        if member.get("estado") not in ("Activo", "Moroso"):
            continue
        try:
            venc = datetime.strptime(member["vencimiento"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue

        days_expired = (today - venc).days

        if days_expired <= 0:
            # Not yet expired — if it was Moroso and got renewed, mark Activo
            if member["estado"] == "Moroso":
                member["estado"] = "Activo"
                save_member(member)
                changed.append(member)
            continue

        if days_expired <= grace_days:
            if member["estado"] != "Moroso":
                member["estado"] = "Moroso"
                save_member(member)
                changed.append(member)
        else:
            new_status = "Moroso" if grace_days == 0 and days_expired <= 15 else "Inactivo"
            if grace_days == 0 and days_expired <= 15:
                new_status = "Moroso"
            elif grace_days == 0 and days_expired > 15:
                new_status = "Inactivo"
            else:
                new_status = "Inactivo"

            if member["estado"] != new_status:
                member["estado"] = new_status
                save_member(member)
                changed.append(member)

    md.rebuild_member_index()
    return changed


# ── Health ────────────────────────────────────────────────────────────

def get_db_health() -> dict:
    if not is_db_enabled():
        return {"enabled": False, "connected": False}

    with _db_connection() as conn:
        if not conn:
            return {"enabled": True, "connected": False}

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT NOW();")
                _ = cur.fetchone()
            return {"enabled": True, "connected": True}
        except Exception:
            return {"enabled": True, "connected": False}
