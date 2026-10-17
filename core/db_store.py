"""Dual-engine database persistence (SQLite local auto-storage + PostgreSQL)
with automatic schema migration, backup export/import, and Excel CSV exports.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional


def is_postgres_enabled() -> bool:
    """Return True if user explicitly configured PostgreSQL."""
    return os.getenv("GYMSIS_USE_DB", "false").strip().lower() in {"1", "true", "yes", "on"}


def is_db_enabled() -> bool:
    """Always True because local SQLite is available as zero-config default."""
    return True


def get_active_engine() -> str:
    """Return 'postgresql' if Postgres is running, else 'sqlite'."""
    if is_postgres_enabled() and _connect_pg() is not None:
        return "postgresql"
    return "sqlite"


# ---------------------------------------------------------------------------
# SQLite Engine (Local Zero-Config Storage)
# ---------------------------------------------------------------------------

def _get_sqlite_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.getenv("GYMSIS_SQLITE_PATH", os.path.join(data_dir, "gymsis.db"))


def _connect_sqlite():
    db_path = _get_sqlite_path()
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    schema_sql = """
    CREATE TABLE IF NOT EXISTS members (
        cedula TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        plan TEXT NOT NULL,
        vencimiento TEXT NOT NULL,
        estado TEXT NOT NULL,
        nfc_id TEXT NOT NULL DEFAULT '',
        entrenando INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS access_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cedula TEXT NOT NULL,
        nombre TEXT NOT NULL,
        plan TEXT NOT NULL,
        status TEXT NOT NULL,
        event_time TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto TEXT NOT NULL,
        monto REAL NOT NULL,
        sold_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        precio REAL NOT NULL DEFAULT 0.0,
        stock INTEGER NOT NULL DEFAULT 0,
        categoria TEXT NOT NULL DEFAULT 'General',
        icono TEXT NOT NULL DEFAULT 'INVENTORY'
    );

    CREATE TABLE IF NOT EXISTS membership_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cedula TEXT NOT NULL,
        nombre TEXT NOT NULL DEFAULT '',
        plan TEXT NOT NULL,
        monto REAL NOT NULL,
        monto_bs REAL NOT NULL DEFAULT 0.0,
        tasa_bcv REAL NOT NULL DEFAULT 0.0,
        dias INTEGER NOT NULL DEFAULT 30,
        metodo TEXT NOT NULL DEFAULT 'efectivo',
        nota TEXT NOT NULL DEFAULT '',
        fecha_pago TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        precio REAL NOT NULL DEFAULT 0.0,
        dias INTEGER NOT NULL DEFAULT 30,
        descripcion TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1
    );
    """
    with conn:
        conn.executescript(schema_sql)

    # Automatic schema migration: verify columns in case an older version database is opened
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(members)")
    cols = {row["name"] for row in cur.fetchall()}
    if "nfc_id" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN nfc_id TEXT NOT NULL DEFAULT ''")
    if "entrenando" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN entrenando INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))")
    conn.commit()


# ---------------------------------------------------------------------------
# PostgreSQL Engine (Optional Production Scaler)
# ---------------------------------------------------------------------------

def _get_pg_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://gymsis:gymsis_dev@localhost:5433/gymsis")


def _connect_pg():
    try:
        import psycopg
        return psycopg.connect(_get_pg_database_url(), autocommit=True)
    except Exception:
        return None


def _ensure_pg_schema(conn) -> None:
    schema_sql = """
    CREATE TABLE IF NOT EXISTS members (
        cedula TEXT PRIMARY KEY,
        nombre TEXT NOT NULL,
        plan TEXT NOT NULL,
        vencimiento DATE NOT NULL,
        estado TEXT NOT NULL,
        nfc_id TEXT NOT NULL DEFAULT '',
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

    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS products (
        id BIGSERIAL PRIMARY KEY,
        nombre TEXT NOT NULL UNIQUE,
        precio NUMERIC(12, 2) NOT NULL DEFAULT 0.0,
        stock INTEGER NOT NULL DEFAULT 0,
        categoria TEXT NOT NULL DEFAULT 'General',
        icono TEXT NOT NULL DEFAULT 'INVENTORY'
    );

    CREATE TABLE IF NOT EXISTS membership_payments (
        id BIGSERIAL PRIMARY KEY,
        cedula TEXT NOT NULL,
        nombre TEXT NOT NULL DEFAULT '',
        plan TEXT NOT NULL,
        monto NUMERIC(12, 2) NOT NULL,
        monto_bs NUMERIC(14, 2) NOT NULL DEFAULT 0.0,
        tasa_bcv NUMERIC(10, 4) NOT NULL DEFAULT 0.0,
        dias INTEGER NOT NULL DEFAULT 30,
        metodo TEXT NOT NULL DEFAULT 'efectivo',
        nota TEXT NOT NULL DEFAULT '',
        fecha_pago TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS plans (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(128) NOT NULL UNIQUE,
        precio NUMERIC(10, 2) NOT NULL DEFAULT 0.0,
        dias INTEGER NOT NULL DEFAULT 30,
        descripcion TEXT NOT NULL DEFAULT '',
        is_active BOOLEAN NOT NULL DEFAULT TRUE
    );
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)


# ---------------------------------------------------------------------------
# Unified Database Bootstrap & Hydration
# ---------------------------------------------------------------------------

def bootstrap_database() -> bool:
    """Ensure core tables and columns exist on the active database."""
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            _ensure_pg_schema(conn)
            return True

    # Fallback to SQLite
    conn = _connect_sqlite()
    _ensure_sqlite_schema(conn)
    conn.close()
    return True


def hydrate_mock_data_from_db() -> bool:
    """Load DB data into in-memory lists so UI modules consume persisted state."""
    bootstrap_database()

    members = load_members()
    access_log = load_access_log()
    sales = load_sales()
    settings = load_settings()
    products = load_products()

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
        md.DAILY_INCOME = sum(float(s.get("monto", 0)) for s in sales)

    if settings:
        md.APP_SETTINGS.update(settings)

    if not products:
        # Seed default inventory items if table is brand new
        defaults = [
            {"nombre": "Agua Mineral 500ml", "precio": 1.00, "stock": 40, "categoria": "Bebidas", "icono": "LOCAL_DRINK"},
            {"nombre": "Bebida Isotónica 600ml", "precio": 2.50, "stock": 25, "categoria": "Bebidas", "icono": "LOCAL_DRINK"},
            {"nombre": "Barra Proteica Chocolate", "precio": 3.00, "stock": 20, "categoria": "Suplementos", "icono": "FITNESS_CENTER"},
            {"nombre": "Batido Proteína Whey", "precio": 4.50, "stock": 15, "categoria": "Suplementos", "icono": "LOCAL_CAFE"},
            {"nombre": "Toalla Gymsis Microfibra", "precio": 6.00, "stock": 10, "categoria": "Accesorios", "icono": "DRY_CLEANING"},
        ]
        for it in defaults:
            save_product(it)
        products = load_products()

    if products:
        md.POS_PRODUCTS.clear()
        md.POS_PRODUCTS.extend(products)

    plans = load_plans(active_only=True)
    if not plans:
        defaults_plans = [
            {"nombre": "Mensual", "precio": 30.00, "dias": 30, "descripcion": "Acceso ilimitado a sala de pesas y máquinas", "is_active": 1},
            {"nombre": "Quincenal", "precio": 18.00, "dias": 15, "descripcion": "Acceso libre por 15 días continuos", "is_active": 1},
            {"nombre": "Semanal", "precio": 10.00, "dias": 7, "descripcion": "Pase semanal completo", "is_active": 1},
            {"nombre": "Pase Diario", "precio": 3.00, "dias": 1, "descripcion": "Entrenamiento individual por el día", "is_active": 1},
            {"nombre": "Trimestral", "precio": 80.00, "dias": 90, "descripcion": "3 meses con descuento especial", "is_active": 1},
            {"nombre": "VIP", "precio": 50.00, "dias": 30, "descripcion": "Acceso total + clases grupales y lockers", "is_active": 1},
            {"nombre": "Estudiante", "precio": 20.00, "dias": 30, "descripcion": "Tarifa especial presentando carnet", "is_active": 1},
            {"nombre": "Basico", "precio": 25.00, "dias": 30, "descripcion": "Acceso regular a sala de musculación", "is_active": 1},
        ]
        for dp in defaults_plans:
            save_plan(dp)
        plans = load_plans(active_only=True)

    if plans:
        md.PLANS.clear()
        for p in plans:
            md.PLANS[p["nombre"]] = {
                "precio": float(p["precio"]),
                "dias": int(p["dias"]),
                "descripcion": p.get("descripcion", ""),
            }

    try:
        from core.audio_service import audio
        audio.warm_reusable_cache()
    except Exception:
        pass

    return True


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------

def load_members() -> List[Dict[str, Any]]:
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = """
            SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando
            FROM members ORDER BY nombre ASC;
            """
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    rows = cur.fetchall()
            return [
                {
                    "cedula": r[0],
                    "nombre": r[1],
                    "plan": r[2],
                    "vencimiento": r[3].strftime("%Y-%m-%d") if r[3] else "",
                    "estado": r[4],
                    "nfc_id": r[5] or "",
                    "entrenando": bool(r[6]),
                }
                for r in rows
            ]

    # SQLite
    conn = _connect_sqlite()
    cur = conn.cursor()
    cur.execute("SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando FROM members ORDER BY nombre ASC")
    rows = cur.fetchall()
    members = [
        {
            "cedula": r["cedula"],
            "nombre": r["nombre"],
            "plan": r["plan"],
            "vencimiento": r["vencimiento"],
            "estado": r["estado"],
            "nfc_id": r["nfc_id"] or "",
            "entrenando": bool(r["entrenando"]),
        }
        for r in rows
    ]
    conn.close()
    return members


def save_member(member: Dict[str, Any]) -> bool:
    cedula = (member.get("cedula") or "").strip().upper()
    if not cedula:
        return False

    nombre = (member.get("nombre") or "").strip()
    plan = (member.get("plan") or "Basico").strip()
    vencimiento = (member.get("vencimiento") or "").strip()
    estado = (member.get("estado") or "Activo").strip()
    nfc_id = (member.get("nfc_id") or "").strip().upper()
    entrenando = int(bool(member.get("entrenando", False)))

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
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
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (cedula, nombre, plan, vencimiento, estado, nfc_id, bool(entrenando)))
                return True
            except Exception:
                pass

    # SQLite
    conn = _connect_sqlite()
    query = """
    INSERT INTO members (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
    ON CONFLICT(cedula) DO UPDATE SET
        nombre = excluded.nombre,
        plan = excluded.plan,
        vencimiento = excluded.vencimiento,
        estado = excluded.estado,
        nfc_id = excluded.nfc_id,
        entrenando = excluded.entrenando,
        updated_at = datetime('now', 'localtime');
    """
    try:
        with conn:
            conn.execute(query, (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando))
        return True
    finally:
        conn.close()


def delete_member(cedula: str) -> bool:
    clean_cedula = (cedula or "").strip().upper()
    if not clean_cedula:
        return False

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM members WHERE cedula = %s", (clean_cedula,))
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("DELETE FROM members WHERE cedula = ?", (clean_cedula,))
        return True
    finally:
        conn.close()


def load_access_log(limit: int = 500) -> List[Dict[str, Any]]:
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = """
            SELECT nombre, plan, status, cedula, event_time
            FROM access_log ORDER BY event_time DESC LIMIT %s;
            """
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
            return [
                {
                    "nombre": r[0],
                    "plan": r[1],
                    "status": r[2],
                    "cedula": r[3],
                    "hora": r[4].strftime("%H:%M") if r[4] else "",
                }
                for r in rows
            ]

    conn = _connect_sqlite()
    cur = conn.cursor()
    cur.execute(
        "SELECT nombre, plan, status, cedula, event_time FROM access_log ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    events = []
    for r in rows:
        time_str = r["event_time"] or ""
        if " " in time_str:
            time_part = time_str.split(" ")[1][:5]
        else:
            time_part = time_str[:5]
        events.append(
            {
                "nombre": r["nombre"],
                "plan": r["plan"],
                "status": r["status"],
                "cedula": r["cedula"],
                "hora": time_part,
            }
        )
    conn.close()
    return events


def save_access_event(event: Dict[str, Any]) -> bool:
    cedula = event.get("cedula", "")
    nombre = event.get("nombre", "Desconocido")
    plan = event.get("plan", "-")
    status = event.get("status", "DENEGADO")

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = """
            INSERT INTO access_log (cedula, nombre, plan, status, event_time)
            VALUES (%s, %s, %s, %s, NOW());
            """
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (cedula, nombre, plan, status))
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute(
                "INSERT INTO access_log (cedula, nombre, plan, status) VALUES (?, ?, ?, ?)",
                (cedula, nombre, plan, status),
            )
        return True
    finally:
        conn.close()


def load_sales(limit: int = 500) -> List[Dict[str, Any]]:
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = """
            SELECT producto, monto, sold_at
            FROM sales ORDER BY sold_at DESC LIMIT %s;
            """
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query, (limit,))
                    rows = cur.fetchall()
            return [
                {
                    "producto": r[0],
                    "monto": float(r[1]),
                    "hora": r[2].strftime("%H:%M") if r[2] else "",
                }
                for r in rows
            ]

    conn = _connect_sqlite()
    cur = conn.cursor()
    cur.execute("SELECT producto, monto, sold_at FROM sales ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    sales = []
    for r in rows:
        time_str = r["sold_at"] or ""
        time_part = time_str.split(" ")[1][:5] if " " in time_str else time_str[:5]
        sales.append({"producto": r["producto"], "monto": float(r["monto"]), "hora": time_part})
    conn.close()
    return sales


def save_sale_row(row: Dict[str, Any]) -> bool:
    producto = row.get("producto", "")
    monto = float(row.get("monto", 0))

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = "INSERT INTO sales (producto, monto, sold_at) VALUES (%s, %s, NOW());"
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (producto, monto))
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("INSERT INTO sales (producto, monto) VALUES (?, ?)", (producto, monto))
        return True
    finally:
        conn.close()


def load_settings() -> Dict[str, Any]:
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = "SELECT key, value FROM app_settings;"
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    rows = cur.fetchall()
            return {key: val for key, val in rows}

    conn = _connect_sqlite()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM app_settings")
    rows = cur.fetchall()
    settings = {}
    for r in rows:
        try:
            settings[r["key"]] = json.loads(r["value"])
        except Exception:
            settings[r["key"]] = r["value"]
    conn.close()
    return settings


def save_settings(settings: Dict[str, Any]) -> bool:
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
            """
            try:
                with conn:
                    with conn.cursor() as cur:
                        for k, v in settings.items():
                            cur.execute(query, (k, json.dumps(v)))
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            for k, v in settings.items():
                payload = json.dumps(v)
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, datetime('now', 'localtime'))
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now', 'localtime')
                    """,
                    (k, payload),
                )
        return True
    finally:
        conn.close()


def load_products() -> List[Dict[str, Any]]:
    """Load all inventory products ordered alphabetically."""
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id, nombre, precio, stock, categoria, icono FROM products ORDER BY nombre ASC;")
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r[0],
                                "nombre": r[1],
                                "precio": float(r[2]),
                                "stock": int(r[3]),
                                "categoria": r[4] or "General",
                                "icono": r[5] or "INVENTORY",
                            }
                            for r in rows
                        ]
            except Exception:
                pass

    conn = _connect_sqlite()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, precio, stock, categoria, icono FROM products ORDER BY nombre ASC")
    rows = cur.fetchall()
    products = [
        {
            "id": r["id"],
            "nombre": r["nombre"],
            "precio": float(r["precio"]),
            "stock": int(r["stock"]),
            "categoria": r["categoria"] or "General",
            "icono": r["icono"] or "INVENTORY",
        }
        for r in rows
    ]
    conn.close()
    return products


def save_product(product: Dict[str, Any]) -> bool:
    """Insert or update a product by name."""
    nombre = (product.get("nombre") or "").strip()
    if not nombre:
        return False
    precio = float(product.get("precio", 0.0))
    stock = max(0, int(product.get("stock", 0)))
    categoria = (product.get("categoria") or "General").strip()
    icono = (product.get("icono") or "INVENTORY").strip()

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                query = """
                INSERT INTO products (nombre, precio, stock, categoria, icono)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nombre) DO UPDATE SET
                    precio = EXCLUDED.precio,
                    stock = EXCLUDED.stock,
                    categoria = EXCLUDED.categoria,
                    icono = EXCLUDED.icono;
                """
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (nombre, precio, stock, categoria, icono))
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO products (nombre, precio, stock, categoria, icono)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(nombre) DO UPDATE SET
                    precio = excluded.precio,
                    stock = excluded.stock,
                    categoria = excluded.categoria,
                    icono = excluded.icono;
                """,
                (nombre, precio, stock, categoria, icono),
            )
        return True
    finally:
        conn.close()


def delete_product(nombre: str) -> bool:
    """Delete a product by name."""
    clean_nombre = (nombre or "").strip()
    if not clean_nombre:
        return False

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM products WHERE LOWER(nombre) = LOWER(%s);", (clean_nombre,))
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("DELETE FROM products WHERE LOWER(nombre) = LOWER(?)", (clean_nombre,))
        return True
    finally:
        conn.close()


def deduct_product_stock(nombre: str, qty: int = 1) -> bool:
    """Subtract sold quantity from product stock (clamped at 0)."""
    clean_nombre = (nombre or "").strip()
    if not clean_nombre or qty <= 0:
        return False

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE products SET stock = GREATEST(0, stock - %s) WHERE LOWER(nombre) = LOWER(%s);", (qty, clean_nombre))
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE LOWER(nombre) = LOWER(?)", (qty, clean_nombre))
        return True
    finally:
        conn.close()


def save_membership_payment(payment: Dict[str, Any]) -> bool:
    """Record a membership renewal/payment and calculate local currency."""
    cedula = (payment.get("cedula") or "").strip().upper()
    if not cedula:
        return False
    nombre = (payment.get("nombre") or "").strip()
    plan = (payment.get("plan") or "Mensual").strip()
    monto = float(payment.get("monto", 0.0))
    monto_bs = float(payment.get("monto_bs", 0.0))
    tasa_bcv = float(payment.get("tasa_bcv", 0.0))
    dias = int(payment.get("dias", 30))
    metodo = (payment.get("metodo") or "efectivo").strip()
    nota = (payment.get("nota") or "").strip()
    fecha_pago = payment.get("fecha_pago")

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                query = """
                INSERT INTO membership_payments (cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()));
                """
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago))
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            if fecha_pago:
                conn.execute(
                    """
                    INSERT INTO membership_payments (cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO membership_payments (cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota),
                )
        return True
    finally:
        conn.close()


def load_membership_payments(cedula: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    """Load membership payments history, optionally filtered by cedula."""
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        if cedula:
                            cur.execute(
                                """
                                SELECT id, cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, TO_CHAR(fecha_pago, 'YYYY-MM-DD HH24:MI:SS') as fecha_pago
                                FROM membership_payments
                                WHERE UPPER(cedula) = UPPER(%s)
                                ORDER BY id DESC LIMIT %s;
                                """,
                                (cedula.strip(), limit),
                            )
                        else:
                            cur.execute(
                                """
                                SELECT id, cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, TO_CHAR(fecha_pago, 'YYYY-MM-DD HH24:MI:SS') as fecha_pago
                                FROM membership_payments
                                ORDER BY id DESC LIMIT %s;
                                """,
                                (limit,),
                            )
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r[0],
                                "cedula": r[1],
                                "nombre": r[2],
                                "plan": r[3],
                                "monto": float(r[4]),
                                "monto_bs": float(r[5]),
                                "tasa_bcv": float(r[6]),
                                "dias": r[7],
                                "metodo": r[8],
                                "nota": r[9],
                                "fecha_pago": str(r[10]),
                            }
                            for r in rows
                        ]
            except Exception:
                pass

    conn = _connect_sqlite()
    cur = conn.cursor()
    if cedula:
        cur.execute(
            """
            SELECT id, cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago
            FROM membership_payments
            WHERE UPPER(cedula) = UPPER(?)
            ORDER BY id DESC LIMIT ?
            """,
            (cedula.strip(), limit),
        )
    else:
        cur.execute(
            """
            SELECT id, cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago
            FROM membership_payments
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )
    rows = cur.fetchall()
    payments = [
        {
            "id": r["id"],
            "cedula": r["cedula"],
            "nombre": r["nombre"],
            "plan": r["plan"],
            "monto": float(r["monto"]),
            "monto_bs": float(r["monto_bs"]),
            "tasa_bcv": float(r["tasa_bcv"]),
            "dias": r["dias"],
            "metodo": r["metodo"],
            "nota": r["nota"],
            "fecha_pago": str(r["fecha_pago"]),
        }
        for r in rows
    ]
    conn.close()
    return payments


def load_plans(active_only: bool = True) -> List[Dict[str, Any]]:
    """Load all configured gym membership plans."""
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                query = "SELECT id, nombre, precio, dias, descripcion, is_active FROM plans"
                if active_only:
                    query += " WHERE is_active = TRUE"
                query += " ORDER BY precio ASC;"
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query)
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r[0],
                                "nombre": r[1],
                                "precio": float(r[2]),
                                "dias": int(r[3]),
                                "descripcion": r[4] or "",
                                "is_active": bool(r[5]),
                            }
                            for r in rows
                        ]
            except Exception:
                pass

    conn = _connect_sqlite()
    cur = conn.cursor()
    query = "SELECT id, nombre, precio, dias, descripcion, is_active FROM plans"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY precio ASC"
    cur.execute(query)
    rows = cur.fetchall()
    plans = [
        {
            "id": r["id"],
            "nombre": r["nombre"],
            "precio": float(r["precio"]),
            "dias": int(r["dias"]),
            "descripcion": r["descripcion"] or "",
            "is_active": bool(r["is_active"]),
        }
        for r in rows
    ]
    conn.close()
    return plans


def save_plan(plan: Dict[str, Any]) -> bool:
    """Create or update a gym membership plan by name."""
    nombre = (plan.get("nombre") or "").strip()
    if not nombre:
        return False
    precio = max(0.0, float(plan.get("precio", 0.0)))
    dias = max(1, int(plan.get("dias", 30)))
    descripcion = (plan.get("descripcion") or "").strip()
    is_active = 1 if plan.get("is_active", True) else 0

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                query = """
                INSERT INTO plans (nombre, precio, dias, descripcion, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nombre) DO UPDATE SET
                    precio = EXCLUDED.precio,
                    dias = EXCLUDED.dias,
                    descripcion = EXCLUDED.descripcion,
                    is_active = EXCLUDED.is_active;
                """
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (nombre, precio, dias, descripcion, bool(is_active)))
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO plans (nombre, precio, dias, descripcion, is_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(nombre) DO UPDATE SET
                    precio = excluded.precio,
                    dias = excluded.dias,
                    descripcion = excluded.descripcion,
                    is_active = excluded.is_active;
                """,
                (nombre, precio, dias, descripcion, is_active),
            )
        return True
    finally:
        conn.close()


def delete_plan(nombre: str) -> bool:
    """Delete a plan by name."""
    clean_nombre = (nombre or "").strip()
    if not clean_nombre:
        return False

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM plans WHERE LOWER(nombre) = LOWER(%s);", (clean_nombre,))
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("DELETE FROM plans WHERE LOWER(nombre) = LOWER(?)", (clean_nombre,))
        return True
    finally:
        conn.close()



# ---------------------------------------------------------------------------
# Backup Export & Import (Compatible across versions)
# ---------------------------------------------------------------------------

def _get_backups_dir() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    b_dir = os.path.join(base_dir, "backups")
    os.makedirs(b_dir, exist_ok=True)
    return b_dir


def export_backup_json(target_path: Optional[str] = None) -> str:
    """Export the entire system database to a portable JSON backup file."""
    bootstrap_database()
    members = load_members()
    access_log = load_access_log(limit=5000)
    sales = load_sales(limit=5000)
    settings = load_settings()
    products = load_products()
    payments = load_membership_payments(limit=5000)

    plans = load_plans(active_only=False)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not target_path:
        filename = f"gymsis_backup_{timestamp}.json"
        target_path = os.path.join(_get_backups_dir(), filename)

    backup_payload = {
        "format": "gymsis_database_backup",
        "version": "2.0.0",
        "exported_at": datetime.now().isoformat(),
        "stats": {
            "members_count": len(members),
            "access_log_count": len(access_log),
            "sales_count": len(sales),
            "products_count": len(products),
            "membership_payments_count": len(payments),
            "plans_count": len(plans),
        },
        "members": members,
        "access_log": access_log,
        "sales": sales,
        "app_settings": settings,
        "products": products,
        "membership_payments": payments,
        "plans": plans,
    }

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(backup_payload, f, indent=2, ensure_ascii=False)

    return target_path


def import_backup_json(source: Any) -> Dict[str, Any]:
    """Import a JSON backup from a file path or dict, supporting legacy schemas.
    
    Compatible with:
    - Version 2.0 full backup dicts.
    - Version 1.0 backups (which had members without nfc_id or different keys).
    - Raw lists of member dicts.
    """
    bootstrap_database()

    data: Any = None
    if isinstance(source, str):
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(source)
    elif isinstance(source, dict) or isinstance(source, list):
        data = source
    else:
        raise ValueError("Fuente de importación inválida")

    members_raw = []
    access_raw = []
    sales_raw = []
    settings_raw = {}
    products_raw = []
    payments_raw = []
    plans_raw = []

    if isinstance(data, list):
        # Legacy list of members
        members_raw = data
    elif isinstance(data, dict):
        members_raw = data.get("members") or data.get("socios") or []
        access_raw = data.get("access_log") or data.get("accesos") or []
        sales_raw = data.get("sales") or data.get("ventas") or []
        settings_raw = data.get("app_settings") or data.get("settings") or {}
        products_raw = data.get("products") or data.get("productos") or []
        payments_raw = data.get("membership_payments") or data.get("pagos") or []
        plans_raw = data.get("plans") or data.get("planes") or []

    imported_members = 0
    today = datetime.now().date()

    for item in members_raw:
        cedula = (item.get("cedula") or item.get("id") or "").strip().upper()
        if not cedula:
            continue
        nombre = (item.get("nombre") or item.get("name") or "Socio").strip()
        plan = (item.get("plan") or "Basico").strip()
        vencimiento = item.get("vencimiento") or (today + timedelta(days=30)).strftime("%Y-%m-%d")
        estado = item.get("estado") or "Activo"
        nfc_id = (item.get("nfc_id") or item.get("tag_id") or "").strip().upper()
        entrenando = bool(item.get("entrenando", False))

        member_record = {
            "cedula": cedula,
            "nombre": nombre,
            "plan": plan,
            "vencimiento": vencimiento,
            "estado": estado,
            "nfc_id": nfc_id,
            "entrenando": entrenando,
        }
        if save_member(member_record):
            imported_members += 1

    imported_events = 0
    for evt in access_raw:
        if save_access_event(evt):
            imported_events += 1

    imported_sales = 0
    for sale in sales_raw:
        if save_sale_row(sale):
            imported_sales += 1

    if settings_raw:
        save_settings(settings_raw)

    imported_products = 0
    for prod in products_raw:
        if save_product(prod):
            imported_products += 1

    imported_payments = 0
    for pay in payments_raw:
        if save_membership_payment(pay):
            imported_payments += 1

    imported_plans = 0
    for pl in plans_raw:
        if save_plan(pl):
            imported_plans += 1


    # Rehydrate in-memory state
    hydrate_mock_data_from_db()

    return {
        "success": True,
        "members_imported": imported_members,
        "events_imported": imported_events,
        "sales_imported": imported_sales,
        "products_imported": imported_products,
        "payments_imported": imported_payments,
        "plans_imported": imported_plans,
        "engine": get_active_engine(),
    }


def export_members_csv(target_path: Optional[str] = None) -> str:
    """Export all members to an Excel-friendly CSV with UTF-8 BOM."""
    members = load_members()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not target_path:
        target_path = os.path.join(_get_backups_dir(), f"socios_{timestamp}.csv")

    with open(target_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Cédula", "Nombre", "Plan", "Vencimiento", "Estado", "NFC UID", "En Gimnasio"])
        for m in members:
            writer.writerow([
                m.get("cedula", ""),
                m.get("nombre", ""),
                m.get("plan", ""),
                m.get("vencimiento", ""),
                m.get("estado", ""),
                m.get("nfc_id", ""),
                "SÍ" if m.get("entrenando") else "NO",
            ])
    return target_path


def export_access_log_csv(target_path: Optional[str] = None) -> str:
    """Export access log to Excel-friendly CSV."""
    logs = load_access_log(limit=10000)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not target_path:
        target_path = os.path.join(_get_backups_dir(), f"accesos_{timestamp}.csv")

    with open(target_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Cédula", "Nombre", "Plan", "Estado Acceso", "Hora"])
        for l in logs:
            writer.writerow([
                l.get("cedula", ""),
                l.get("nombre", ""),
                l.get("plan", ""),
                l.get("status", ""),
                l.get("hora", ""),
            ])
    return target_path


def get_db_health() -> Dict[str, Any]:
    engine = get_active_engine()
    if engine == "postgresql":
        return {"enabled": True, "engine": "postgresql", "connected": True}
    return {
        "enabled": True,
        "engine": "sqlite",
        "connected": True,
        "path": _get_sqlite_path(),
    }
