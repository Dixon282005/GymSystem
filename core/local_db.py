"""Local SQLite database persistence module for Gymsis.
Zero-configuration default database with automatic migrations,
WAL mode, password hashing, user RBAC, audit logging, and attendance tracking.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from core.paths import get_db_path

LOCAL_ROLE_PERMISSIONS: dict[str, set] = {
    "admin": {
        "view_pos",
        "view_access",
        "manage_users",
        "manage_pos",
        "view_dashboard",
        "view_members",
        "view_settings",
        "view_plans",
        "view_reports",
        "view_audit",
    },
    "staff": {
        "view_pos",
        "view_access",
        "manage_pos",
        "view_dashboard",
        "view_members",
        "view_plans",
    },
    "viewer": {
        "view_dashboard",
        "view_access",
    },
}


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    """Generate a PBKDF2-HMAC-SHA256 password hash with 100,000 iterations and salt."""
    import secrets

    if salt is None:
        salt_bytes = secrets.token_bytes(16)
        salt_hex = salt_bytes.hex()
    else:
        salt_hex = salt
        try:
            salt_bytes = bytes.fromhex(salt_hex)
        except ValueError:
            salt_bytes = salt_hex.encode("utf-8")

    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 100_000)
    return f"pbkdf2:sha256:100000${salt_hex}${dk.hex()}"


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against modern PBKDF2 hash with fallback to legacy single-round SHA-256."""
    if not hashed:
        return False

    if hashed.startswith("pbkdf2:sha256:"):
        try:
            parts = hashed.split("$")
            if len(parts) == 3:
                _, salt_hex, expected_hex = parts
                try:
                    salt_bytes = bytes.fromhex(salt_hex)
                except ValueError:
                    salt_bytes = salt_hex.encode("utf-8")
                dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 100_000)
                return hmac.compare_digest(dk.hex(), expected_hex)
        except Exception:
            return False

    # Backwards compatibility with legacy SHA-256 hashes
    legacy_salt = os.getenv("GYMSIS_PASSWORD_SALT", "gymsis-dev-salt")
    legacy_hash = hashlib.sha256(f"{legacy_salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, hashed)


def _db_path() -> str:
    return get_db_path()


@contextlib.contextmanager
def _conn():
    from core.db_store import _connect_sqlite
    connection = _connect_sqlite()
    try:
        yield connection
        connection.commit()
    except Exception as exc:
        try:
            connection.rollback()
        except Exception:
            pass
        print(f"[local_db] SQLite error: {exc}")
        raise
    finally:
        try:
            connection.close()
        except Exception:
            pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    cedula      TEXT PRIMARY KEY,
    nombre      TEXT NOT NULL,
    plan        TEXT NOT NULL,
    vencimiento TEXT NOT NULL,
    estado      TEXT NOT NULL,
    nfc_id      TEXT NOT NULL,
    entrenando  INTEGER NOT NULL DEFAULT 0,
    creado_por  TEXT DEFAULT 'sistema',
    telefono    TEXT DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cedula      TEXT NOT NULL,
    nombre      TEXT NOT NULL,
    plan        TEXT NOT NULL,
    status      TEXT NOT NULL,
    event_time  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    producto    TEXT NOT NULL,
    monto       REAL NOT NULL,
    sold_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pos_products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT NOT NULL UNIQUE,
    precio      REAL NOT NULL,
    stock       INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plans (
    nombre      TEXT PRIMARY KEY,
    precio      REAL NOT NULL,
    descripcion TEXT DEFAULT '',
    dias        INTEGER NOT NULL DEFAULT 30,
    is_active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'viewer',
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS membership_payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cedula       TEXT NOT NULL,
    plan         TEXT NOT NULL,
    monto        REAL NOT NULL,
    fecha_pago   TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_inicio TEXT NOT NULL,
    fecha_fin    TEXT NOT NULL,
    metodo       TEXT NOT NULL DEFAULT 'efectivo',
    nota         TEXT NOT NULL DEFAULT '',
    referencia   TEXT DEFAULT '',
    tasa_tipo    TEXT DEFAULT 'BCV',
    tasa_valor   REAL DEFAULT 0.0,
    registrado_por TEXT DEFAULT 'sistema'
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    action      TEXT NOT NULL,
    details     TEXT NOT NULL,
    ip_address  TEXT DEFAULT '127.0.0.1',
    timestamp   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_access_time   ON access_log(event_time);
CREATE INDEX IF NOT EXISTS idx_access_cedula_status_time ON access_log(cedula, status, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_sales_time    ON sales(sold_at);
CREATE INDEX IF NOT EXISTS idx_prod_active   ON pos_products(is_active);
CREATE INDEX IF NOT EXISTS idx_pay_cedula    ON membership_payments(cedula);
CREATE INDEX IF NOT EXISTS idx_pay_fecha     ON membership_payments(fecha_pago);
CREATE INDEX IF NOT EXISTS idx_audit_time    ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user    ON audit_logs(username);
CREATE INDEX IF NOT EXISTS idx_audit_action  ON audit_logs(action);
"""


def _table_has_rows(connection: sqlite3.Connection, table: str) -> bool:
    try:
        row = connection.execute(f"SELECT 1 FROM {table} LIMIT 1;").fetchone()
        return row is not None
    except Exception:
        return False


def bootstrap(initial_data: Optional[Dict[str, Any]] = None) -> None:
    """Create schema, run safe alterations, seed admin user and default plans."""
    with _conn() as c:
        c.executescript(_SCHEMA)

        # Migrations / Alterations
        for migration in [
            "ALTER TABLE membership_payments ADD COLUMN referencia TEXT DEFAULT '';",
            "ALTER TABLE membership_payments ADD COLUMN tasa_tipo TEXT DEFAULT 'BCV';",
            "ALTER TABLE membership_payments ADD COLUMN tasa_valor REAL DEFAULT 0.0;",
            "ALTER TABLE plans ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;",
            "ALTER TABLE members ADD COLUMN creado_por TEXT DEFAULT 'sistema';",
            "ALTER TABLE membership_payments ADD COLUMN registrado_por TEXT DEFAULT 'sistema';",
            "ALTER TABLE members ADD COLUMN telefono TEXT DEFAULT '';",
            "CREATE INDEX IF NOT EXISTS idx_access_cedula_status_time ON access_log(cedula, status, event_time DESC);",
        ]:
            try:
                c.execute(migration)
            except sqlite3.OperationalError:
                pass

        from core.seed_data import SEED_PLANS, SEED_USERS

        if not _table_has_rows(c, "users"):
            for user in SEED_USERS:
                c.execute(
                    """
                    INSERT INTO users (username, password_hash, role, is_active)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(username) DO UPDATE SET
                        role = excluded.role,
                        is_active = 1,
                        updated_at = datetime('now')
                    """,
                    (user["username"], _hash_password(user["password"]), user["role"]),
                )

        if not _table_has_rows(c, "plans"):
            for plan in SEED_PLANS:
                _do_save_plan(c, plan)

        if initial_data:
            if not _table_has_rows(c, "members") and "members" in initial_data:
                for m in initial_data["members"]:
                    _do_save_member(c, m)
            if not _table_has_rows(c, "access_log") and "access_log" in initial_data:
                for ev in initial_data["access_log"]:
                    _do_save_access_event(c, ev)
            if not _table_has_rows(c, "sales") and "sales" in initial_data:
                for s in initial_data["sales"]:
                    _do_save_sale(c, s)
            if not _table_has_rows(c, "pos_products") and "pos_products" in initial_data:
                for p in initial_data["pos_products"]:
                    _do_save_pos_product(c, p)
            if not _table_has_rows(c, "app_settings") and "settings" in initial_data:
                _do_save_settings(c, initial_data["settings"])


def _do_save_member(c: sqlite3.Connection, member: dict) -> None:
    c.execute(
        """
        INSERT INTO members (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, creado_por, telefono, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(cedula) DO UPDATE SET
            nombre = excluded.nombre, plan = excluded.plan,
            vencimiento = excluded.vencimiento, estado = excluded.estado,
            nfc_id = excluded.nfc_id, entrenando = excluded.entrenando,
            telefono = excluded.telefono,
            updated_at = datetime('now')
        """,
        (
            member.get("cedula"),
            member.get("nombre", ""),
            member.get("plan", "Basico"),
            member.get("vencimiento"),
            member.get("estado", "Activo"),
            member.get("nfc_id", ""),
            1 if member.get("entrenando") else 0,
            member.get("creado_por", "sistema"),
            member.get("telefono", ""),
        ),
    )


def save_member(member: dict) -> bool:
    with _conn() as c:
        _do_save_member(c, member)
    return True


def load_members() -> List[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, creado_por, telefono
            FROM members ORDER BY nombre ASC
            """
        ).fetchall()
        return [
            {
                "cedula": r["cedula"],
                "nombre": r["nombre"],
                "plan": r["plan"],
                "vencimiento": r["vencimiento"],
                "estado": r["estado"],
                "nfc_id": r["nfc_id"],
                "entrenando": bool(r["entrenando"]),
                "creado_por": r["creado_por"] if "creado_por" in r.keys() else "sistema",
                "telefono": r["telefono"] if "telefono" in r.keys() else "",
            }
            for r in rows
        ]


def _do_save_access_event(c: sqlite3.Connection, event: dict, event_time: Optional[str] = None) -> None:
    if event_time is None:
        hora = event.get("hora", "")
        fecha = event.get("fecha", "")
        if fecha and hora:
            event_time = f"{fecha} {hora}:00" if len(hora) == 5 else f"{fecha} {hora}"
        else:
            event_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        """
        INSERT INTO access_log (cedula, nombre, plan, status, event_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            event.get("cedula", ""),
            event.get("nombre", ""),
            event.get("plan", ""),
            event.get("status", "PERMITIDO"),
            event_time,
        ),
    )


def save_access_event(event: dict) -> bool:
    with _conn() as c:
        _do_save_access_event(c, event)
    return True


def _access_event_from_row(row: sqlite3.Row) -> dict:
    event_time = row["event_time"] if "event_time" in row.keys() else ""
    return {
        "cedula": row["cedula"],
        "nombre": row["nombre"] if "nombre" in row.keys() else "",
        "plan": row["plan"] if "plan" in row.keys() else "",
        "status": row["status"] if "status" in row.keys() else "PERMITIDO",
        "hora": event_time[11:16] if event_time else "",
        "fecha": event_time[:10] if event_time else "",
        "event_time": event_time,
    }


def load_access_log(limit: int = 50) -> List[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT nombre, plan, status, cedula, event_time
            FROM access_log ORDER BY event_time DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "nombre": r["nombre"],
                "plan": r["plan"],
                "status": r["status"],
                "cedula": r["cedula"],
                "hora": r["event_time"][11:16] if r["event_time"] else "",
                "fecha": r["event_time"][:10] if r["event_time"] else "",
            }
            for r in rows
        ]


def get_last_checkin(cedula: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            """
            SELECT cedula, nombre, plan, status, event_time
            FROM access_log
            WHERE cedula = ? AND status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED')
            ORDER BY event_time DESC
            LIMIT 1
            """,
            (cedula,),
        ).fetchone()
        if not row:
            return None
        return _access_event_from_row(row)


def get_last_checkins_for_cedulas(cedulas: List[str]) -> Dict[str, dict]:
    if not cedulas:
        return {}
    normalized = [c.strip().upper() for c in cedulas if c]
    if not normalized:
        return {}
    placeholders = ",".join("?" for _ in normalized)
    with _conn() as c:
        rows = c.execute(
            f"""
            SELECT cedula, MAX(event_time) AS event_time
            FROM access_log
            WHERE status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED') AND cedula IN ({placeholders})
            GROUP BY cedula
            """,
            normalized,
        ).fetchall()
        result = {}
        for r in rows:
            et = r["event_time"] or ""
            result[r["cedula"]] = {
                "cedula": r["cedula"],
                "status": "ENTRADA",
                "hora": et[11:16] if et else "",
                "fecha": et[:10] if et else "",
                "event_time": et,
            }
        return result


def list_members_low_attendance(
    min_days: int = 7, estados: Tuple[str, ...] = ("Activo", "Vigente")
) -> List[dict]:
    placeholders = ",".join("?" for _ in estados)
    with _conn() as c:
        rows = c.execute(
            f"""
            SELECT m.cedula, m.nombre, m.telefono, m.plan, m.estado, m.vencimiento,
                   lc.last_checkin
            FROM members m
            LEFT JOIN (
                SELECT cedula, MAX(event_time) AS last_checkin
                FROM access_log
                WHERE status IN ('ENTRADA', 'PERMITIDO', 'CONCEDIDO', 'ACCESO', 'GRANTED')
                GROUP BY cedula
            ) lc ON lc.cedula = m.cedula
            WHERE m.estado IN ({placeholders})
              AND (
                lc.last_checkin IS NULL
                OR date(lc.last_checkin) <= date('now', '-' || ? || ' days')
              )
            ORDER BY lc.last_checkin IS NOT NULL, lc.last_checkin ASC
            """,
            (*estados, min_days),
        ).fetchall()

        today = datetime.now().date()
        result = []
        for r in rows:
            last = r["last_checkin"]
            if last:
                try:
                    last_date = datetime.strptime(last[:10], "%Y-%m-%d").date()
                    dias = (today - last_date).days
                    ultimo_ingreso = f"{last[:10]} {last[11:16]}".strip()
                except ValueError:
                    dias = -1
                    ultimo_ingreso = last
            else:
                dias = -1
                ultimo_ingreso = "Nunca"

            result.append(
                {
                    "cedula": r["cedula"],
                    "nombre": r["nombre"],
                    "telefono": r["telefono"] if "telefono" in r.keys() else "",
                    "plan": r["plan"],
                    "estado": r["estado"],
                    "vencimiento": r["vencimiento"],
                    "ultimo_ingreso": ultimo_ingreso,
                    "dias_sin_ingreso": dias,
                }
            )
        return result


def _do_save_sale(c: sqlite3.Connection, row: dict, sold_at: Optional[str] = None) -> None:
    if sold_at is None:
        hora = row.get("hora", "")
        fecha = row.get("fecha", "")
        if fecha and hora:
            sold_at = f"{fecha} {hora}:00" if len(hora) == 5 else f"{fecha} {hora}"
        else:
            sold_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        """
        INSERT INTO sales (producto, monto, sold_at)
        VALUES (?, ?, ?)
        """,
        (row.get("producto", ""), float(row.get("monto", 0.0)), sold_at),
    )


def save_sale(row: dict) -> bool:
    with _conn() as c:
        _do_save_sale(c, row)
    return True


def load_sales(limit: int = 100) -> List[dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT producto, monto, sold_at FROM sales ORDER BY sold_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "producto": r["producto"],
                "monto": float(r["monto"]),
                "hora": r["sold_at"][11:16] if r["sold_at"] else "",
                "fecha": r["sold_at"][:10] if r["sold_at"] else "",
            }
            for r in rows
        ]


def _do_save_pos_product(c: sqlite3.Connection, product: dict) -> None:
    c.execute(
        """
        INSERT INTO pos_products (nombre, precio, stock, is_active, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(nombre) DO UPDATE SET
            precio = excluded.precio, stock = excluded.stock,
            is_active = excluded.is_active, updated_at = datetime('now')
        """,
        (
            product.get("nombre", "").strip(),
            float(product.get("precio", 0.0)),
            int(product.get("stock", 0)),
            1 if product.get("is_active", True) else 0,
        ),
    )


def save_pos_product(product: dict) -> Tuple[bool, str]:
    name = product.get("nombre", "").strip()
    if not name:
        return False, "Nombre requerido"
    with _conn() as c:
        _do_save_pos_product(c, product)
    return True, "Producto guardado"


def rename_pos_product(old_name: str, product: dict) -> Tuple[bool, str]:
    old_clean = (old_name or "").strip()
    new_clean = (product.get("nombre") or "").strip()
    if not new_clean:
        return False, "Nombre requerido"
    if not old_clean or old_clean.lower() == new_clean.lower():
        return save_pos_product(product)
    with _conn() as c:
        c.execute("DELETE FROM pos_products WHERE LOWER(nombre) = LOWER(?)", (old_clean,))
        _do_save_pos_product(c, product)
    return True, "Producto renombrado y guardado"


def delete_pos_product(nombre: str) -> Tuple[bool, str]:
    with _conn() as c:
        cur = c.execute(
            "UPDATE pos_products SET is_active = 0, updated_at = datetime('now') WHERE nombre = ?",
            (nombre.strip(),),
        )
        if cur.rowcount == 0:
            return False, "Producto no encontrado"
    return True, "Producto desactivado"


def set_product_active(nombre: str, is_active: bool) -> Tuple[bool, str]:
    with _conn() as c:
        cur = c.execute(
            "UPDATE pos_products SET is_active = ?, updated_at = datetime('now') WHERE nombre = ?",
            (1 if is_active else 0, nombre.strip()),
        )
        if cur.rowcount == 0:
            return False, "Producto no encontrado"
    return True, "Producto activado" if is_active else "Producto desactivado"


def decrement_stock(nombre: str, qty: int = 1) -> bool:
    with _conn() as c:
        c.execute(
            """
            UPDATE pos_products
            SET stock = MAX(0, stock - ?), updated_at = datetime('now')
            WHERE nombre = ? AND is_active = 1
            """,
            (qty, nombre.strip()),
        )
    return True


def load_pos_products(active_only: bool = False) -> List[dict]:
    where = "WHERE is_active = 1" if active_only else ""
    with _conn() as c:
        rows = c.execute(
            f"SELECT nombre, precio, stock, is_active FROM pos_products {where} ORDER BY nombre ASC"
        ).fetchall()
        return [
            {
                "nombre": r["nombre"],
                "precio": float(r["precio"]),
                "stock": int(r["stock"]),
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]


def _do_save_plan(c: sqlite3.Connection, plan: dict) -> None:
    c.execute(
        """
        INSERT INTO plans (nombre, precio, descripcion, dias, is_active)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(nombre) DO UPDATE SET
            precio = excluded.precio, descripcion = excluded.descripcion,
            dias = excluded.dias, is_active = excluded.is_active
        """,
        (
            plan.get("nombre", "").strip(),
            float(plan.get("precio", 0.0)),
            plan.get("descripcion", ""),
            int(plan.get("dias", 30)),
            1 if plan.get("is_active", True) else 0,
        ),
    )


def save_plan(plan: dict) -> Tuple[bool, str]:
    name = plan.get("nombre", "").strip()
    if not name:
        return False, "Nombre de plan requerido"
    with _conn() as c:
        _do_save_plan(c, plan)
    return True, "Plan guardado"


def delete_plan(nombre: str) -> Tuple[bool, str]:
    with _conn() as c:
        row = c.execute(
            "SELECT EXISTS(SELECT 1 FROM members WHERE plan = ? LIMIT 1);",
            (nombre.strip(),),
        ).fetchone()
        if row and row[0]:
            return False, f"No se puede eliminar el plan '{nombre}' porque tiene clientes asignados."
        cur = c.execute("UPDATE plans SET is_active = 0 WHERE nombre = ?", (nombre.strip(),))
        if cur.rowcount == 0:
            return False, "Plan no encontrado"
    return True, "Plan desactivado"


def set_plan_active(nombre: str, is_active: bool) -> Tuple[bool, str]:
    with _conn() as c:
        if not is_active:
            row = c.execute(
                "SELECT EXISTS(SELECT 1 FROM members WHERE plan = ? LIMIT 1);",
                (nombre.strip(),),
            ).fetchone()
            if row and row[0]:
                return False, f"No se puede desactivar el plan '{nombre}' porque tiene clientes asignados."
        cur = c.execute(
            "UPDATE plans SET is_active = ? WHERE nombre = ?",
            (1 if is_active else 0, nombre.strip()),
        )
        if cur.rowcount == 0:
            return False, "Plan no encontrado"
    status_msg = "activado" if is_active else "desactivado"
    return True, f"Plan {status_msg}"


def load_plans(active_only: bool = False) -> List[dict]:
    query = "SELECT nombre, precio, descripcion, dias, is_active FROM plans"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY nombre ASC"
    with _conn() as c:
        rows = c.execute(query).fetchall()
        return [
            {
                "nombre": r["nombre"],
                "precio": float(r["precio"]),
                "descripcion": r["descripcion"] or "",
                "dias": int(r["dias"]),
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]


def _do_save_settings(c: sqlite3.Connection, settings: dict) -> None:
    for key, value in settings.items():
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        c.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
            """,
            (key, val_str),
        )


def save_settings(settings: dict) -> bool:
    with _conn() as c:
        _do_save_settings(c, settings)
    return True


def load_settings() -> Dict[str, Any]:
    with _conn() as c:
        rows = c.execute("SELECT key, value FROM app_settings").fetchall()
        result = {}
        for r in rows:
            val = r["value"]
            try:
                result[r["key"]] = json.loads(val)
            except Exception:
                result[r["key"]] = val
        return result


def save_membership_payment(payment: dict) -> Tuple[bool, str]:
    cedula = payment.get("cedula", "").strip().upper()
    plan = payment.get("plan", "").strip()
    monto = float(payment.get("monto", 0.0))
    dias = int(payment.get("dias", 30))
    metodo = payment.get("metodo", "efectivo")
    nota = payment.get("nota", "")
    referencia = payment.get("referencia", "")
    tasa_tipo = payment.get("tasa_tipo", "BCV")
    tasa_valor = float(payment.get("tasa_valor", 0.0))
    registrado_por = payment.get("registrado_por", "sistema")

    if not cedula or not plan:
        return False, "Cedula y plan son obligatorios"
    if monto < 0:
        return False, "Monto inválido"

    with _conn() as c:
        member_row = c.execute(
            "SELECT vencimiento FROM members WHERE cedula = ?", (cedula,)
        ).fetchone()
        hoy = datetime.now().date()
        fecha_inicio = hoy.isoformat()

        if member_row and member_row["vencimiento"]:
            try:
                venc_date = datetime.strptime(member_row["vencimiento"], "%Y-%m-%d").date()
                if venc_date >= hoy:
                    fecha_inicio = venc_date.isoformat()
            except ValueError:
                pass

        from core.business import calculate_expiry_date

        fecha_fin = calculate_expiry_date(fecha_inicio, dias)
        fecha_pago = payment.get("fecha_pago") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute(
            """
            INSERT INTO membership_payments (cedula, plan, monto, fecha_pago, fecha_inicio, fecha_fin, metodo, nota, referencia, tasa_tipo, tasa_valor, registrado_por)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cedula,
                plan,
                monto,
                fecha_pago,
                fecha_inicio,
                fecha_fin,
                metodo,
                nota,
                referencia,
                tasa_tipo,
                tasa_valor,
                registrado_por,
            ),
        )

        c.execute(
            """
            UPDATE members SET
                vencimiento = ?, plan = ?, estado = 'Activo',
                updated_at = datetime('now')
            WHERE cedula = ?
            """,
            (fecha_fin, plan, cedula),
        )

    return True, "Pago registrado"


def load_membership_payments(cedula: Optional[str] = None, limit: int = 100) -> List[dict]:
    with _conn() as c:
        if cedula and cedula.strip():
            rows = c.execute(
                """
                SELECT cedula, plan, monto, fecha_pago, fecha_inicio, fecha_fin, metodo, nota, referencia, tasa_tipo, tasa_valor, registrado_por
                FROM membership_payments WHERE cedula = ?
                ORDER BY fecha_pago DESC LIMIT ?
                """,
                (cedula.strip().upper(), limit),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT cedula, plan, monto, fecha_pago, fecha_inicio, fecha_fin, metodo, nota, referencia, tasa_tipo, tasa_valor, registrado_por
                FROM membership_payments ORDER BY fecha_pago DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "cedula": r["cedula"],
                "plan": r["plan"],
                "monto": float(r["monto"]),
                "fecha_pago": r["fecha_pago"][:16] if r["fecha_pago"] else "",
                "fecha_inicio": r["fecha_inicio"],
                "fecha_fin": r["fecha_fin"],
                "metodo": r["metodo"],
                "nota": r["nota"],
                "referencia": r["referencia"] if "referencia" in r.keys() else "",
                "tasa_tipo": r["tasa_tipo"] if "tasa_tipo" in r.keys() else "BCV",
                "tasa_valor": float(r["tasa_valor"]) if "tasa_valor" in r.keys() and r["tasa_valor"] is not None else 0.0,
                "registrado_por": r["registrado_por"] if "registrado_por" in r.keys() else "sistema",
            }
            for r in rows
        ]


def authenticate_user(username: str, password: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username = ?",
            (username.strip().lower(),),
        ).fetchone()
        if not row:
            return None
        if not row["is_active"]:
            return None
        if not _verify_password(password, row["password_hash"]):
            return None

        # Auto-upgrade legacy hash to PBKDF2
        stored_hash = row["password_hash"] or ""
        if not stored_hash.startswith("pbkdf2:sha256:"):
            try:
                new_hash = _hash_password(password)
                c.execute(
                    "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE username = ?",
                    (new_hash, row["username"]),
                )
            except Exception:
                pass

        return {"username": row["username"], "role": row["role"]}


def get_user_permissions(username: str) -> Set[str]:
    with _conn() as c:
        row = c.execute(
            "SELECT role FROM users WHERE username = ? AND is_active = 1",
            (username.strip().lower(),),
        ).fetchone()
        if not row:
            return set()
        return LOCAL_ROLE_PERMISSIONS.get(row["role"], set())


def list_users() -> List[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT username, role, is_active FROM users ORDER BY username ASC"
        ).fetchall()
        return [
            {
                "username": r["username"],
                "role": r["role"],
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]


def list_roles() -> List[str]:
    return sorted(LOCAL_ROLE_PERMISSIONS.keys())


def create_user(username: str, password: str, role: str) -> Tuple[bool, str]:
    if not username.strip() or not password:
        return False, "Usuario y clave son obligatorios"
    if len(password) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres"
    normalized = role.strip().lower()
    if normalized not in LOCAL_ROLE_PERMISSIONS:
        return False, "Rol inválido"

    with _conn() as c:
        c.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(username) DO UPDATE SET
                password_hash = excluded.password_hash,
                role = excluded.role, is_active = 1,
                updated_at = datetime('now')
            """,
            (username.strip().lower(), _hash_password(password), normalized),
        )
    return True, "Usuario guardado"


def update_user(username: str, role: str, password: Optional[str] = None) -> Tuple[bool, str]:
    if not username.strip():
        return False, "Usuario es obligatorio"
    normalized = role.strip().lower()
    if normalized not in LOCAL_ROLE_PERMISSIONS:
        return False, "Rol inválido"

    with _conn() as c:
        if password and password.strip():
            if len(password) < 6:
                return False, "La contraseña debe tener al menos 6 caracteres"
            cur = c.execute(
                "UPDATE users SET role = ?, password_hash = ?, updated_at = datetime('now') WHERE username = ?",
                (normalized, _hash_password(password), username.strip().lower()),
            )
        else:
            cur = c.execute(
                "UPDATE users SET role = ?, updated_at = datetime('now') WHERE username = ?",
                (normalized, username.strip().lower()),
            )
        if cur.rowcount == 0:
            return False, "Usuario no encontrado"
    return True, "Usuario actualizado"


def set_user_active(username: str, is_active: bool) -> Tuple[bool, str]:
    with _conn() as c:
        cur = c.execute(
            "UPDATE users SET is_active = ?, updated_at = datetime('now') WHERE username = ?",
            (1 if is_active else 0, username.strip().lower()),
        )
        if cur.rowcount == 0:
            return False, "Usuario no encontrado"
    return True, "Estado actualizado"


def delete_user(username: str) -> Tuple[bool, str]:
    normalized = username.strip().lower()
    if normalized == "admin":
        return False, "No puedes desactivar el admin base"
    with _conn() as c:
        cur = c.execute(
            "UPDATE users SET is_active = 0, updated_at = datetime('now') WHERE username = ?",
            (normalized,),
        )
        if cur.rowcount == 0:
            return False, "Usuario no encontrado"
    return True, "Usuario desactivado"


def save_audit_log(log_entry: dict) -> bool:
    """Persist a single audit log entry."""
    with _conn() as c:
        timestamp = log_entry.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """
            INSERT INTO audit_logs (username, action, details, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                log_entry.get("username", "sistema"),
                log_entry.get("action", "DESCONOCIDA"),
                log_entry.get("details", "{}"),
                log_entry.get("ip_address", "127.0.0.1"),
                timestamp,
            ),
        )
    return True


def load_audit_logs(
    limit: int = 100,
    action_filter: Optional[str] = None,
    user_filter: Optional[str] = None,
    query_search: Optional[str] = None,
) -> List[dict]:
    """Load audit log entries with optional filters."""
    sql = "SELECT id, username, action, details, ip_address, timestamp FROM audit_logs"
    conditions = []
    params: list = []

    if action_filter and action_filter.strip():
        conditions.append("action = ?")
        params.append(action_filter.strip())

    if user_filter and user_filter.strip():
        conditions.append("username = ?")
        params.append(user_filter.strip())

    if query_search and query_search.strip():
        conditions.append("(details LIKE ? OR action LIKE ? OR username LIKE ?)")
        q = f"%{query_search.strip()}%"
        params.extend([q, q, q])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _conn() as c:
        rows = c.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "username": r["username"],
                "action": r["action"],
                "details": r["details"],
                "ip_address": r["ip_address"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]


def load_audit_actions() -> List[str]:
    """Return distinct action types from the audit log."""
    with _conn() as c:
        rows = c.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action ASC").fetchall()
        return [r["action"] for r in rows if r["action"]]


def load_audit_users() -> List[str]:
    """Return distinct usernames from the audit log."""
    with _conn() as c:
        rows = c.execute("SELECT DISTINCT username FROM audit_logs ORDER BY username ASC").fetchall()
        return [r["username"] for r in rows if r["username"]]
