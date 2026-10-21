"""Dual-engine database persistence (SQLite local auto-storage + PostgreSQL)
with automatic schema migration, backup export/import, and Excel CSV exports.
"""

from __future__ import annotations

import contextlib
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
    if is_postgres_enabled():
        conn = _connect_pg()
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            return "postgresql"
    return "sqlite"



# ---------------------------------------------------------------------------
# SQLite Engine (Local Zero-Config Storage)
# ---------------------------------------------------------------------------

import threading

_thread_local = threading.local()


class _ManagedConnection:
    """Wrapper that prevents closing, beginning separate transactions, or committing when inside an active transaction."""
    def __init__(self, raw_conn: sqlite3.Connection):
        object.__setattr__(self, "_raw_conn", raw_conn)

    def __getattr__(self, name: str):
        return getattr(self._raw_conn, name)

    def __setattr__(self, name: str, value: Any):
        if name == "_raw_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(self._raw_conn, name, value)

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _get_sqlite_path() -> str:
    from core.paths import get_db_path
    return get_db_path()


def _connect_sqlite() -> sqlite3.Connection:
    active_tx = getattr(_thread_local, "tx_conn", None)
    if active_tx is not None:
        return _ManagedConnection(active_tx)

    db_path = _get_sqlite_path()
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextlib.contextmanager
def transaction(connection: Optional[sqlite3.Connection] = None):
    """Atomic transaction manager for SQLite."""
    existing = getattr(_thread_local, "tx_conn", None)
    if existing is not None:
        yield existing
        return

    raw_conn = connection or sqlite3.connect(_get_sqlite_path(), timeout=30.0, check_same_thread=False)
    raw_conn.row_factory = sqlite3.Row
    raw_conn.execute("PRAGMA journal_mode=WAL;")
    raw_conn.execute("PRAGMA synchronous=NORMAL;")
    raw_conn.execute("PRAGMA foreign_keys=ON;")

    _thread_local.tx_conn = raw_conn
    try:
        raw_conn.execute("BEGIN IMMEDIATE;")
        yield raw_conn
        raw_conn.commit()
    except Exception:
        try:
            raw_conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _thread_local.tx_conn = None
        if connection is None:
            try:
                raw_conn.close()
            except Exception:
                pass


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
        creado_por TEXT DEFAULT 'sistema',
        telefono TEXT DEFAULT '',
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
        icono TEXT NOT NULL DEFAULT 'INVENTORY',
        is_active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS pos_products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        precio REAL NOT NULL DEFAULT 0.0,
        stock INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
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
        referencia TEXT DEFAULT '',
        tasa_tipo TEXT DEFAULT 'BCV',
        tasa_valor REAL DEFAULT 0.0,
        registrado_por TEXT DEFAULT 'sistema',
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

    CREATE TABLE IF NOT EXISTS member_nfc_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cedula TEXT NOT NULL,
        nfc_id TEXT NOT NULL UNIQUE,
        alias TEXT NOT NULL DEFAULT 'Llavero',
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (cedula) REFERENCES members(cedula) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT NOT NULL,
        ip_address TEXT DEFAULT '127.0.0.1',
        timestamp TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
    );

    CREATE INDEX IF NOT EXISTS idx_members_nombre ON members(nombre);
    CREATE INDEX IF NOT EXISTS idx_members_nfc ON members(nfc_id);
    CREATE INDEX IF NOT EXISTS idx_member_nfc_keys_uid ON member_nfc_keys(nfc_id);
    CREATE INDEX IF NOT EXISTS idx_member_nfc_keys_cedula ON member_nfc_keys(cedula);
    CREATE INDEX IF NOT EXISTS idx_access_log_event_time ON access_log(event_time DESC);
    CREATE INDEX IF NOT EXISTS idx_access_log_cedula ON access_log(cedula);
    CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at DESC);
    CREATE INDEX IF NOT EXISTS idx_payments_cedula ON membership_payments(cedula);
    CREATE INDEX IF NOT EXISTS idx_payments_fecha ON membership_payments(fecha_pago DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(username);
    """
    with conn:
        conn.executescript(schema_sql)

    cur = conn.cursor()
    # Check members columns
    cur.execute("PRAGMA table_info(members)")
    cols = {row["name"] for row in cur.fetchall()}
    if "nfc_id" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN nfc_id TEXT NOT NULL DEFAULT ''")
    if "entrenando" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN entrenando INTEGER NOT NULL DEFAULT 0")
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))")
    if "telefono" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN telefono TEXT DEFAULT ''")
    if "creado_por" not in cols:
        conn.execute("ALTER TABLE members ADD COLUMN creado_por TEXT DEFAULT 'sistema'")

    # Migrate pos_products into products if products table is empty
    try:
        cur.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] == 0:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pos_products'")
            if cur.fetchone():
                conn.execute("""
                    INSERT OR IGNORE INTO products (nombre, precio, stock, is_active, updated_at)
                    SELECT nombre, precio, stock, is_active, updated_at FROM pos_products;
                """)
    except Exception:
        pass

    # Ensure columns in products
    try:
        cur.execute("PRAGMA table_info(products)")
        pcols = {row["name"] for row in cur.fetchall()}
        if "is_active" not in pcols:
            conn.execute("ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "updated_at" not in pcols:
            conn.execute("ALTER TABLE products ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))")
    except Exception:
        pass

    # Ensure default users
    try:
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            from core.local_db import _hash_password
            conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, 1)",
                ("admin", _hash_password("admin123"), "admin"),
            )
            conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, 1)",
                ("gerente", _hash_password("gerente123"), "admin"),
            )
    except Exception:
        pass

    conn.commit()


# ---------------------------------------------------------------------------
# PostgreSQL Engine (Optional Production Scaler)
# ---------------------------------------------------------------------------

def _get_pg_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://gymsis:gymsis_dev@localhost:5433/gymsis")


class _PGConnectionWrapper:
    """Wrapper around psycopg connection that ensures closing upon exiting transaction blocks."""

    def __init__(self, raw_conn):
        self._raw_conn = raw_conn

    def __getattr__(self, name):
        return getattr(self._raw_conn, name)

    def __enter__(self):
        if hasattr(self._raw_conn, "__enter__"):
            self._raw_conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if hasattr(self._raw_conn, "__exit__"):
                return self._raw_conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()

    def close(self):
        try:
            if hasattr(self._raw_conn, "close"):
                return self._raw_conn.close()
        except Exception:
            pass

    def cursor(self, *args, **kwargs):
        return self._raw_conn.cursor(*args, **kwargs)


def _connect_pg():
    try:
        import psycopg
        raw_conn = psycopg.connect(_get_pg_database_url(), autocommit=True)
        return _PGConnectionWrapper(raw_conn)
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

    CREATE TABLE IF NOT EXISTS member_nfc_keys (
        id SERIAL PRIMARY KEY,
        cedula VARCHAR(20) NOT NULL REFERENCES members(cedula) ON DELETE CASCADE,
        nfc_id VARCHAR(64) NOT NULL UNIQUE,
        alias VARCHAR(100) NOT NULL DEFAULT 'Llavero',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_member_nfc_keys_uid ON member_nfc_keys(nfc_id);
    CREATE INDEX IF NOT EXISTS idx_member_nfc_keys_cedula ON member_nfc_keys(cedula);
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute("ALTER TABLE members ADD COLUMN IF NOT EXISTS telefono TEXT DEFAULT '';")
            cur.execute("ALTER TABLE members ADD COLUMN IF NOT EXISTS creado_por TEXT DEFAULT 'sistema';")


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

    md.MEMBERS.clear()
    if members:
        md.MEMBERS.extend(members)
    md.rebuild_member_index()
    try:
        from core.business import sync_member_statuses
        sync_member_statuses()
    except Exception:
        pass

    md.ACCESS_LOG.clear()
    if access_log:
        md.ACCESS_LOG.extend(access_log)

    md.DAILY_SALES.clear()
    if sales:
        md.DAILY_SALES.extend(sales)
        md.DAILY_INCOME = sum(float(s.get("monto", 0)) for s in sales)
    else:
        md.DAILY_INCOME = 0.0

    if settings:
        md.APP_SETTINGS.update(settings)

    md.POS_PRODUCTS.clear()
    if products:
        md.POS_PRODUCTS.extend(products)

    plans = load_plans(active_only=True)
    if not plans:
        defaults_plans = [
            {"nombre": "Pase Diario", "precio": 2.50, "dias": 1, "descripcion": "Entrenamiento individual por el día", "is_active": 1},
            {"nombre": "Semanal", "precio": 7.00, "dias": 7, "descripcion": "Pase semanal completo", "is_active": 1},
            {"nombre": "Mensual", "precio": 20.00, "dias": 30, "descripcion": "Acceso ilimitado a sala de pesas y máquinas", "is_active": 1},
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
        sync_initial_nfc_keys()
        md.refresh_nfc_keys_cache()
    except Exception:
        pass

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
            SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por
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
                    "telefono": r[7] if len(r) > 7 and r[7] else "",
                    "creado_por": r[8] if len(r) > 8 and r[8] else "sistema",
                }
                for r in rows
            ]

    # SQLite
    conn = _connect_sqlite()
    cur = conn.cursor()
    cur.execute("SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por FROM members ORDER BY nombre ASC")
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
            "telefono": r["telefono"] if "telefono" in r.keys() else "",
            "creado_por": r["creado_por"] if "creado_por" in r.keys() else "sistema",
        }
        for r in rows
    ]
    conn.close()
    return members


def find_member_by_cedula(cedula: str) -> Optional[dict]:
    """Find a single member by cedula directly with indexed SQLite query."""
    clean = (cedula or "").strip().upper()
    if not clean:
        return None
    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por
            FROM members WHERE UPPER(cedula) = ? LIMIT 1
            """,
            (clean,),
        )
        row = cur.fetchone()
        if row:
            return {
                "cedula": row["cedula"],
                "nombre": row["nombre"],
                "plan": row["plan"],
                "vencimiento": row["vencimiento"],
                "estado": row["estado"],
                "nfc_id": row["nfc_id"] or "",
                "entrenando": bool(row["entrenando"]),
                "telefono": row["telefono"] if "telefono" in row.keys() else "",
                "creado_por": row["creado_por"] if "creado_por" in row.keys() else "sistema",
            }
        # Fallback with standard Venezuelan prefix variations
        digits = "".join(c for c in clean if c.isdigit())
        if digits:
            cand_cedulas = [digits] + [f"{p}{digits}" for p in ("V-", "E-", "J-", "G-", "P-", "V", "E")]
            placeholders = ",".join("?" for _ in cand_cedulas)
            cur.execute(
                f"""
                SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por
                FROM members WHERE UPPER(cedula) IN ({placeholders}) LIMIT 1
                """,
                cand_cedulas,
            )
            row = cur.fetchone()
            if row:
                return {
                    "cedula": row["cedula"],
                    "nombre": row["nombre"],
                    "plan": row["plan"],
                    "vencimiento": row["vencimiento"],
                    "estado": row["estado"],
                    "nfc_id": row["nfc_id"] or "",
                    "entrenando": bool(row["entrenando"]),
                    "telefono": row["telefono"] if "telefono" in row.keys() else "",
                    "creado_por": row["creado_por"] if "creado_por" in row.keys() else "sistema",
                }
        return None
    finally:
        conn.close()


def find_member_by_nfc_id(nfc_id: str) -> Optional[dict]:
    """Find a member by their primary or auxiliary NFC tag UID."""
    clean = "".join(c for c in (nfc_id or "").upper() if c.isalnum())
    if not clean:
        return None
    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        # 1. Auxiliary keys table
        cur.execute(
            """
            SELECT m.cedula, m.nombre, m.plan, m.vencimiento, m.estado, m.nfc_id, m.entrenando, m.telefono, m.creado_por
            FROM member_nfc_keys k
            JOIN members m ON UPPER(k.cedula) = UPPER(m.cedula)
            WHERE UPPER(k.nfc_id) = ?
            LIMIT 1
            """,
            (clean,),
        )
        row = cur.fetchone()
        if row:
            return {
                "cedula": row["cedula"],
                "nombre": row["nombre"],
                "plan": row["plan"],
                "vencimiento": row["vencimiento"],
                "estado": row["estado"],
                "nfc_id": row["nfc_id"] or "",
                "entrenando": bool(row["entrenando"]),
                "telefono": row["telefono"] if "telefono" in row.keys() else "",
                "creado_por": row["creado_por"] if "creado_por" in row.keys() else "sistema",
            }
        # 2. Primary nfc_id on members table
        cur.execute(
            """
            SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por
            FROM members
            WHERE UPPER(nfc_id) = ?
            LIMIT 1
            """,
            (clean,),
        )
        row = cur.fetchone()
        if row:
            return {
                "cedula": row["cedula"],
                "nombre": row["nombre"],
                "plan": row["plan"],
                "vencimiento": row["vencimiento"],
                "estado": row["estado"],
                "nfc_id": row["nfc_id"] or "",
                "entrenando": bool(row["entrenando"]),
                "telefono": row["telefono"] if "telefono" in row.keys() else "",
                "creado_por": row["creado_por"] if "creado_por" in row.keys() else "sistema",
            }
        return None
    finally:
        conn.close()


def search_members(query: str, limit: int = 100) -> List[dict]:
    """Search members by cedula or name directly with indexed SQL."""
    q = (query or "").strip().upper()
    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        if not q:
            cur.execute(
                """
                SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por
                FROM members ORDER BY nombre ASC LIMIT ?
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por
                FROM members
                WHERE UPPER(cedula) LIKE ? OR UPPER(nombre) LIKE ?
                ORDER BY nombre ASC LIMIT ?
                """,
                (f"%{q}%", f"%{q}%", limit),
            )
        rows = cur.fetchall()
        return [
            {
                "cedula": r["cedula"],
                "nombre": r["nombre"],
                "plan": r["plan"],
                "vencimiento": r["vencimiento"],
                "estado": r["estado"],
                "nfc_id": r["nfc_id"] or "",
                "entrenando": bool(r["entrenando"]),
                "telefono": r["telefono"] if "telefono" in r.keys() else "",
                "creado_por": r["creado_por"] if "creado_por" in r.keys() else "sistema",
            }
            for r in rows
        ]
    finally:
        conn.close()


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
    telefono = (member.get("telefono") or "").strip()
    creado_por = (member.get("creado_por") or "sistema").strip()

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            query = """
            INSERT INTO members (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (cedula) DO UPDATE SET
                nombre = EXCLUDED.nombre,
                plan = EXCLUDED.plan,
                vencimiento = EXCLUDED.vencimiento,
                estado = EXCLUDED.estado,
                nfc_id = EXCLUDED.nfc_id,
                entrenando = EXCLUDED.entrenando,
                telefono = EXCLUDED.telefono,
                creado_por = EXCLUDED.creado_por,
                updated_at = NOW();
            """
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (cedula, nombre, plan, vencimiento, estado, nfc_id, bool(entrenando), telefono, creado_por))
                return True
            except Exception:
                pass

    # SQLite
    conn = _connect_sqlite()
    query = """
    INSERT INTO members (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
    ON CONFLICT(cedula) DO UPDATE SET
        nombre = excluded.nombre,
        plan = excluded.plan,
        vencimiento = excluded.vencimiento,
        estado = excluded.estado,
        nfc_id = excluded.nfc_id,
        entrenando = excluded.entrenando,
        telefono = excluded.telefono,
        creado_por = excluded.creado_por,
        updated_at = datetime('now', 'localtime');
    """
    try:
        with conn:
            conn.execute(query, (cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando, telefono, creado_por))
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
                        cur.execute("DELETE FROM member_nfc_keys WHERE UPPER(cedula) = %s", (clean_cedula,))
                        cur.execute("DELETE FROM members WHERE cedula = %s", (clean_cedula,))
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("DELETE FROM member_nfc_keys WHERE UPPER(cedula) = ?", (clean_cedula,))
            conn.execute("DELETE FROM members WHERE cedula = ?", (clean_cedula,))
        return True
    finally:
        conn.close()


def load_member_nfc_keys(cedula: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all registered NFC keys, optionally filtered by member cedula."""
    engine = get_active_engine()
    clean_cedula = (cedula or "").strip().upper() if cedula else None

    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        if clean_cedula:
                            cur.execute(
                                "SELECT id, cedula, nfc_id, alias, created_at FROM member_nfc_keys WHERE UPPER(cedula) = %s ORDER BY id ASC;",
                                (clean_cedula,),
                            )
                        else:
                            cur.execute(
                                "SELECT id, cedula, nfc_id, alias, created_at FROM member_nfc_keys ORDER BY id ASC;"
                            )
                        rows = cur.fetchall()
                        return [
                            {
                                "id": r[0],
                                "cedula": r[1],
                                "nfc_id": r[2],
                                "alias": r[3] or "Llavero",
                                "created_at": str(r[4]) if r[4] else "",
                            }
                            for r in rows
                        ]
            except Exception as e:
                logger.debug(f"[DB] Error loading pg nfc keys: {e}")

    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        if clean_cedula:
            cur.execute(
                "SELECT id, cedula, nfc_id, alias, created_at FROM member_nfc_keys WHERE UPPER(cedula) = ? ORDER BY id ASC",
                (clean_cedula,),
            )
        else:
            cur.execute("SELECT id, cedula, nfc_id, alias, created_at FROM member_nfc_keys ORDER BY id ASC")
        rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "cedula": r["cedula"],
                "nfc_id": r["nfc_id"],
                "alias": r["alias"] or "Llavero",
                "created_at": str(r["created_at"]) if r["created_at"] else "",
            }
            for r in rows
        ]
    except Exception as e:
        logger.debug(f"[DB] Error loading sqlite nfc keys: {e}")
        return []
    finally:
        conn.close()


def add_member_nfc_key(cedula: str, nfc_id: str, alias: str = "Llavero") -> Tuple[bool, str]:
    """Register an additional NFC key (phone, card, fob) for a member."""
    clean_cedula = (cedula or "").strip().upper()
    clean_uid = "".join(c for c in (nfc_id or "").upper() if c.isalnum())
    clean_alias = (alias or "Llavero").strip()

    if not clean_cedula:
        return False, "Cédula de socio inválida"
    if not clean_uid:
        return False, "El UID de la tarjeta o dispositivo NFC no puede estar vacío"

    # Check for duplicate across all members
    existing_keys = load_member_nfc_keys()
    for k in existing_keys:
        if k["nfc_id"] == clean_uid:
            if k["cedula"].upper() == clean_cedula:
                return False, f"Esta llave ya está registrada para este socio con el alias '{k.get('alias')}'"
            owner_name = ""
            try:
                owner = find_member_by_cedula(k["cedula"])
                if owner:
                    owner_name = f"{owner.get('nombre', '')} "
            except Exception:
                pass
            return False, f"Esta llave NFC ya pertenece a {owner_name}(Cédula: {k['cedula']})"

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO member_nfc_keys (cedula, nfc_id, alias, created_at) VALUES (%s, %s, %s, NOW());",
                            (clean_cedula, clean_uid, clean_alias),
                        )
            except Exception as e:
                logger.error(f"[DB] Error guardando llave NFC en PostgreSQL: {e}")

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute(
                "INSERT INTO member_nfc_keys (cedula, nfc_id, alias) VALUES (?, ?, ?)",
                (clean_cedula, clean_uid, clean_alias),
            )
    except Exception as e:
        logger.error(f"[DB] Error guardando llave NFC en SQLite: {e}")
        return False, f"Error en base de datos: {e}"
    finally:
        conn.close()

    # Sync cache in mock_data
    try:
        from core import mock_data as md
        md.refresh_nfc_keys_cache()
    except Exception:
        pass

    return True, f"Llave '{clean_alias}' vinculada con éxito."


def update_member_nfc_key(key_id: int, new_nfc_id: str, new_alias: str) -> Tuple[bool, str]:
    """Edit an existing NFC key alias or overwrite its UID."""
    clean_uid = "".join(c for c in (new_nfc_id or "").upper() if c.isalnum())
    clean_alias = (new_alias or "Llavero").strip()

    if not clean_uid:
        return False, "El UID no puede estar vacío"

    # Check duplicate on other keys
    existing_keys = load_member_nfc_keys()
    for k in existing_keys:
        if k["id"] != key_id and k["nfc_id"] == clean_uid:
            owner_name = ""
            try:
                owner = find_member_by_cedula(k["cedula"])
                if owner:
                    owner_name = f"{owner.get('nombre', '')} "
            except Exception:
                pass
            return False, f"Esta llave NFC ya pertenece a {owner_name}(Cédula: {k['cedula']})"

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE member_nfc_keys SET nfc_id = %s, alias = %s WHERE id = %s;",
                            (clean_uid, clean_alias, key_id),
                        )
            except Exception as e:
                logger.error(f"[DB] Error actualizando llave NFC en PostgreSQL: {e}")

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute(
                "UPDATE member_nfc_keys SET nfc_id = ?, alias = ? WHERE id = ?",
                (clean_uid, clean_alias, key_id),
            )
    except Exception as e:
        logger.error(f"[DB] Error actualizando llave NFC en SQLite: {e}")
        return False, f"Error en base de datos: {e}"
    finally:
        conn.close()

    try:
        from core import mock_data as md
        md.refresh_nfc_keys_cache()
    except Exception:
        pass

    return True, f"Llave actualizada a '{clean_alias}'"


def delete_member_nfc_key(key_id: int) -> bool:
    """Delete an NFC key by ID."""
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM member_nfc_keys WHERE id = %s;", (key_id,))
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute("DELETE FROM member_nfc_keys WHERE id = ?", (key_id,))
        try:
            from core import mock_data as md
            md.refresh_nfc_keys_cache()
        except Exception:
            pass
        return True
    except Exception:
        return False
    finally:
        conn.close()


def sync_initial_nfc_keys() -> int:
    """Migrate legacy members.nfc_id to member_nfc_keys if not already present."""
    try:
        existing_keys = {k["nfc_id"]: k["cedula"] for k in load_member_nfc_keys()}
        members = load_members()
        migrated = 0
        for m in members:
            uid = "".join(c for c in (m.get("nfc_id") or "").upper() if c.isalnum())
            cedula = (m.get("cedula") or "").strip().upper()
            if uid and uid not in existing_keys:
                add_member_nfc_key(cedula, uid, alias="Llavero Principal")
                existing_keys[uid] = cedula
                migrated += 1
        return migrated
    except Exception as e:
        logger.debug(f"[DB] Error migrando llaves nfc iniciales: {e}")
        return 0


def load_access_log(cedula: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            with conn:
                with conn.cursor() as cur:
                    if cedula:
                        query = """
                        SELECT nombre, plan, status, cedula, event_time
                        FROM access_log
                        WHERE UPPER(cedula) = UPPER(%s)
                        ORDER BY event_time DESC LIMIT %s;
                        """
                        cur.execute(query, (cedula.strip(), limit))
                    else:
                        query = """
                        SELECT nombre, plan, status, cedula, event_time
                        FROM access_log ORDER BY event_time DESC LIMIT %s;
                        """
                        cur.execute(query, (limit,))
                    rows = cur.fetchall()
            return [
                {
                    "nombre": r[0],
                    "plan": r[1],
                    "status": r[2],
                    "cedula": r[3],
                    "hora": r[4].strftime("%H:%M") if r[4] else "",
                    "fecha": str(r[4].date()) if r[4] else "",
                }
                for r in rows
            ]

    conn = _connect_sqlite()
    cur = conn.cursor()
    if cedula:
        cur.execute(
            "SELECT nombre, plan, status, cedula, event_time FROM access_log WHERE UPPER(cedula) = UPPER(?) ORDER BY id DESC LIMIT ?",
            (cedula.strip(), limit),
        )
    else:
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
            fecha_part = time_str.split(" ")[0]
        else:
            time_part = time_str[:5]
            fecha_part = ""
        events.append(
            {
                "nombre": r["nombre"],
                "plan": r["plan"],
                "status": r["status"],
                "cedula": r["cedula"],
                "hora": time_part,
                "fecha": fecha_part,
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
                    "fecha": str(r[2].date()) if r[2] else "",
                    "sold_at": str(r[2]) if r[2] else "",
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
        fecha_part = time_str.split(" ")[0] if " " in time_str else (time_str[:10] if len(time_str) >= 10 else "")
        sales.append({
            "producto": r["producto"],
            "monto": float(r["monto"]),
            "hora": time_part,
            "fecha": fecha_part,
            "sold_at": time_str,
        })
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


def rename_product(old_nombre: str, product: Dict[str, Any]) -> bool:
    """Update a product, allowing change of product name."""
    old_clean = (old_nombre or "").strip()
    new_nombre = (product.get("nombre") or "").strip()
    if not new_nombre:
        return False
    if not old_clean or old_clean.lower() == new_nombre.lower():
        return save_product(product)

    precio = float(product.get("precio", 0.0))
    stock = max(0, int(product.get("stock", 0)))
    categoria = (product.get("categoria") or "General").strip()
    icono = (product.get("icono") or "INVENTORY").strip()

    engine = get_active_engine()
    if engine == "postgresql":
        conn = _connect_pg()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE products
                            SET nombre = %s, precio = %s, stock = %s, categoria = %s, icono = %s
                            WHERE LOWER(nombre) = LOWER(%s);
                            """,
                            (new_nombre, precio, stock, categoria, icono, old_clean),
                        )
                return True
            except Exception:
                pass

    conn = _connect_sqlite()
    try:
        with conn:
            conn.execute(
                """
                UPDATE products
                SET nombre = ?, precio = ?, stock = ?, categoria = ?, icono = ?
                WHERE LOWER(nombre) = LOWER(?);
                """,
                (new_nombre, precio, stock, categoria, icono, old_clean),
            )
        return True
    finally:
        conn.close()


def deduct_product_stock(nombre: str, qty: int = 1) -> bool:
    """Subtract sold quantity from product stock (clamped at 0)."""
    clean_nombre = (nombre or "").strip()
    if not clean_nombre or qty <= 0:
        return False

    try:
        decrement_stock_product(clean_nombre, qty)
    except Exception:
        pass

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


def load_membership_payments_between(start_time_str: str, end_time_str: str) -> List[Dict[str, Any]]:
    """Load membership payments between start and end timestamps directly via SQL."""
    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, cedula, nombre, plan, monto, monto_bs, tasa_bcv, dias, metodo, nota, fecha_pago
            FROM membership_payments
            WHERE substr(fecha_pago, 1, 16) >= ? AND substr(fecha_pago, 1, 16) <= ?
            ORDER BY fecha_pago ASC
            """,
            (start_time_str[:16], end_time_str[:16]),
        )
        return [
            {
                "id": r["id"],
                "cedula": r["cedula"],
                "nombre": r["nombre"] if "nombre" in r.keys() else "",
                "plan": r["plan"],
                "monto": float(r["monto"]),
                "monto_bs": float(r["monto_bs"]) if "monto_bs" in r.keys() else 0.0,
                "tasa_bcv": float(r["tasa_bcv"]) if "tasa_bcv" in r.keys() else 0.0,
                "dias": r["dias"],
                "metodo": r["metodo"],
                "nota": r["nota"],
                "fecha_pago": str(r["fecha_pago"]),
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def load_sales_between(start_time_str: str, end_time_str: str) -> List[Dict[str, Any]]:
    """Load sales between start and end timestamps directly via SQL."""
    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, producto, monto, sold_at
            FROM sales
            WHERE substr(sold_at, 1, 16) >= ? AND substr(sold_at, 1, 16) <= ?
            ORDER BY sold_at ASC
            """,
            (start_time_str[:16], end_time_str[:16]),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            st = str(r["sold_at"]) if r["sold_at"] else ""
            hora = st[11:16] if len(st) >= 16 else ""
            fecha = st[:10] if len(st) >= 10 else ""
            result.append({
                "id": r["id"],
                "producto": r["producto"],
                "monto": float(r["monto"]),
                "sold_at": st,
                "hora": hora,
                "fecha": fecha,
            })
        return result
    finally:
        conn.close()


def load_access_log_between(start_time_str: str, end_time_str: str) -> List[Dict[str, Any]]:
    """Load access logs between start and end timestamps directly via SQL."""
    conn = _connect_sqlite()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, cedula, nombre, plan, status, event_time
            FROM access_log
            WHERE substr(event_time, 1, 16) >= ? AND substr(event_time, 1, 16) <= ?
            ORDER BY event_time ASC
            """,
            (start_time_str[:16], end_time_str[:16]),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            et = str(r["event_time"]) if r["event_time"] else ""
            hora = et[11:16] if len(et) >= 16 else ""
            fecha = et[:10] if len(et) >= 10 else ""
            result.append({
                "id": r["id"],
                "cedula": r["cedula"],
                "nombre": r["nombre"] if "nombre" in r.keys() else "",
                "plan": r["plan"] if "plan" in r.keys() else "",
                "status": r["status"] if "status" in r.keys() else "",
                "event_time": et,
                "hora": hora,
                "fecha": fecha,
            })
        return result
    finally:
        conn.close()


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
        clean_src = source.strip()
        if clean_src.startswith("{") or clean_src.startswith("["):
            data = json.loads(clean_src)
        else:
            from core.paths import get_app_dir, get_backups_dir

            app_dir = os.path.realpath(get_app_dir())
            backups_dir = os.path.realpath(get_backups_dir())

            if not os.path.isabs(clean_src):
                candidate = os.path.realpath(os.path.join(backups_dir, clean_src))
                if not os.path.isfile(candidate):
                    candidate = os.path.realpath(os.path.join(app_dir, clean_src))
            else:
                candidate = os.path.realpath(clean_src)

            if not os.path.isfile(candidate):
                raise FileNotFoundError(f"Archivo de respaldo no encontrado: {os.path.basename(clean_src)}")

            if not (candidate.startswith(backups_dir) or candidate.startswith(app_dir)):
                raise PermissionError("Acceso denegado: solo se permite importar archivos desde el directorio de respaldos.")

            if not candidate.lower().endswith(".json"):
                raise ValueError("Formato de archivo no admitido: debe ser un archivo .json")

            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
    elif isinstance(source, (dict, list)):
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


# ---------------------------------------------------------------------------
# Functions added for complete parity with Sistema final release
# ---------------------------------------------------------------------------

def authenticate_user(username: str, password: str) -> Optional[dict]:
    from core import local_db
    return local_db.authenticate_user(username, password)


def get_user_permissions(username: str) -> set:
    from core import local_db
    return local_db.get_user_permissions(username)


def list_roles() -> List[str]:
    from core import local_db
    return local_db.list_roles()


def list_users() -> List[dict]:
    from core import local_db
    return local_db.list_users()


def create_user(username: str, password: str, role: str) -> Tuple[bool, str]:
    from core import local_db
    return local_db.create_user(username, password, role)


def update_user(username: str, role: str, password: Optional[str] = None) -> Tuple[bool, str]:
    from core import local_db
    return local_db.update_user(username, role, password)


def set_user_active(username: str, is_active: bool) -> Tuple[bool, str]:
    from core import local_db
    return local_db.set_user_active(username, is_active)


def delete_user(username: str) -> Tuple[bool, str]:
    from core import local_db
    return local_db.delete_user(username)


def load_pos_products(active_only: bool = False) -> List[dict]:
    from core import local_db
    return local_db.load_pos_products(active_only)


def save_pos_product(product: dict) -> Tuple[bool, str]:
    from core import local_db
    return local_db.save_pos_product(product)


def rename_pos_product(old_nombre: str, product: dict) -> Tuple[bool, str]:
    from core import local_db
    ok, msg = local_db.rename_pos_product(old_nombre, product)
    try:
        rename_product(old_nombre, product)
    except Exception:
        pass
    return ok, msg


def delete_pos_product(nombre: str) -> Tuple[bool, str]:
    from core import local_db
    return local_db.delete_pos_product(nombre)


def set_product_active(nombre: str, is_active: bool) -> Tuple[bool, str]:
    from core import local_db
    return local_db.set_product_active(nombre, is_active)


def decrement_stock_product(nombre: str, qty: int = 1) -> bool:
    from core import local_db
    return local_db.decrement_stock(nombre, qty)


def set_plan_active(nombre: str, is_active: bool) -> Tuple[bool, str]:
    from core import local_db
    return local_db.set_plan_active(nombre, is_active)


def save_audit_log(log_entry: dict) -> bool:
    from core import local_db
    return local_db.save_audit_log(log_entry)


def load_audit_logs(
    limit: int = 100,
    action_filter: Optional[str] = None,
    user_filter: Optional[str] = None,
    query_search: Optional[str] = None,
) -> List[dict]:
    from core import local_db
    return local_db.load_audit_logs(limit, action_filter, user_filter, query_search)


def load_audit_actions() -> List[str]:
    from core import local_db
    return local_db.load_audit_actions()


def load_audit_users() -> List[str]:
    from core import local_db
    return local_db.load_audit_users()


def get_last_checkin(cedula: str) -> Optional[dict]:
    from core import local_db
    return local_db.get_last_checkin(cedula)


def get_last_checkins_for_cedulas(cedulas: List[str]) -> Dict[str, dict]:
    from core import local_db
    return local_db.get_last_checkins_for_cedulas(cedulas)


def list_members_low_attendance(
    min_days: int = 7, estados: Tuple[str, ...] = ("Activo", "Vigente")
) -> List[dict]:
    from core import local_db
    return local_db.list_members_low_attendance(min_days, estados)

