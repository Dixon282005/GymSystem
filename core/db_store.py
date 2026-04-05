"""PostgreSQL persistence helpers with graceful fallback for local mock mode."""

from __future__ import annotations

import json
import os


def is_db_enabled() -> bool:
    return os.getenv("GYMSIS_USE_DB", "false").strip().lower() in {"1", "true", "yes", "on"}


def _get_database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql://gymsis:gymsis_dev@localhost:5433/gymsis")


def _connect():
    try:
        import psycopg
    except Exception:
        return None

    try:
        return psycopg.connect(_get_database_url(), autocommit=True)
    except Exception:
        return None


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

    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)


def _table_has_rows(conn, table_name: str) -> bool:
    with conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1);")
            row = cur.fetchone()
    return bool(row and row[0])


def bootstrap_database() -> bool:
    """Create core tables and seed from in-memory mock data if DB is enabled."""
    if not is_db_enabled():
        return False

    conn = _connect()
    if not conn:
        return False

    _ensure_schema(conn)

    try:
        from core.mock_data import ACCESS_LOG, APP_SETTINGS, DAILY_SALES, MEMBERS
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

    if not _table_has_rows(conn, "app_settings"):
        save_settings(APP_SETTINGS)
    return True


def load_members() -> list[dict]:
    if not is_db_enabled():
        return []
    conn = _connect()
    if not conn:
        return []

    query = """
    SELECT cedula, nombre, plan, vencimiento, estado, nfc_id, entrenando
    FROM members
    ORDER BY nombre ASC;
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    members = []
    for row in rows:
        members.append(
            {
                "cedula": row[0],
                "nombre": row[1],
                "plan": row[2],
                "vencimiento": row[3].strftime("%Y-%m-%d") if row[3] else "",
                "estado": row[4],
                "nfc_id": row[5],
                "entrenando": bool(row[6]),
            }
        )
    return members


def load_access_log(limit: int = 300) -> list[dict]:
    if not is_db_enabled():
        return []
    conn = _connect()
    if not conn:
        return []

    query = """
    SELECT nombre, plan, status, cedula, event_time
    FROM access_log
    ORDER BY event_time DESC
    LIMIT %s;
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

    events = []
    for row in rows:
        events.append(
            {
                "nombre": row[0],
                "plan": row[1],
                "status": row[2],
                "cedula": row[3],
                "hora": row[4].strftime("%H:%M") if row[4] else "",
            }
        )
    return events


def load_sales(limit: int = 500) -> list[dict]:
    if not is_db_enabled():
        return []
    conn = _connect()
    if not conn:
        return []

    query = """
    SELECT producto, monto, sold_at
    FROM sales
    ORDER BY sold_at DESC
    LIMIT %s;
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

    sales = []
    for row in rows:
        sales.append(
            {
                "producto": row[0],
                "monto": float(row[1]),
                "hora": row[2].strftime("%H:%M") if row[2] else "",
            }
        )
    return sales


def load_settings() -> dict:
    if not is_db_enabled():
        return {}
    conn = _connect()
    if not conn:
        return {}

    query = """
    SELECT key, value
    FROM app_settings;
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    settings = {}
    for key, value in rows:
        settings[key] = value
    return settings


def hydrate_mock_data_from_db() -> bool:
    """Load DB data into in-memory lists so current UI modules consume persisted state."""
    if not is_db_enabled():
        return False

    members = load_members()
    access_log = load_access_log()
    sales = load_sales()
    settings = load_settings()

    if not (members or access_log or sales or settings):
        return False

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

    return True


def save_member(member: dict) -> bool:
    if not is_db_enabled():
        return False
    conn = _connect()
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
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
        return True
    except Exception:
        return False


def save_access_event(event: dict) -> bool:
    if not is_db_enabled():
        return False
    conn = _connect()
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
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
        return True
    except Exception:
        return False


def save_sale_row(row: dict) -> bool:
    if not is_db_enabled():
        return False
    conn = _connect()
    if not conn:
        return False

    query = """
    INSERT INTO sales (producto, monto, sold_at)
    VALUES (%s, %s, NOW());
    """
    values = (
        row.get("producto", ""),
        float(row.get("monto", 0)),
    )

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
        return True
    except Exception:
        return False


def save_settings(settings: dict) -> bool:
    if not is_db_enabled():
        return False
    conn = _connect()
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
        with conn:
            with conn.cursor() as cur:
                for key, value in settings.items():
                    payload = json.dumps(value)
                    cur.execute(query, (key, payload))
        return True
    except Exception:
        return False


def get_db_health() -> dict:
    if not is_db_enabled():
        return {"enabled": False, "connected": False}

    conn = _connect()
    if not conn:
        return {"enabled": True, "connected": False}

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT NOW();")
                _ = cur.fetchone()
        return {"enabled": True, "connected": True}
    except Exception:
        return {"enabled": True, "connected": False}
