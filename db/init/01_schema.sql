-- Gymsis PostgreSQL Database Initialization Schema
-- Provides schema parity with SQLite local storage for multi-engine deployments.

CREATE TABLE IF NOT EXISTS members (
    cedula TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    plan TEXT NOT NULL,
    vencimiento DATE NOT NULL,
    estado TEXT NOT NULL,
    nfc_id TEXT NOT NULL DEFAULT '',
    entrenando BOOLEAN NOT NULL DEFAULT FALSE,
    creado_por TEXT DEFAULT 'sistema',
    telefono TEXT DEFAULT '',
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
    icono TEXT NOT NULL DEFAULT 'INVENTORY',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
    referencia TEXT DEFAULT '',
    tasa_tipo TEXT DEFAULT 'BCV',
    tasa_valor NUMERIC(10, 4) DEFAULT 0.0,
    registrado_por TEXT DEFAULT 'sistema',
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

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(128) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(64) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(128) NOT NULL,
    action VARCHAR(128) NOT NULL,
    details TEXT NOT NULL,
    ip_address VARCHAR(64) DEFAULT '127.0.0.1',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_access_log_event_time ON access_log (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_access_cedula ON access_log (cedula, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales (sold_at DESC);
CREATE INDEX IF NOT EXISTS idx_payments_cedula ON membership_payments (cedula);
CREATE INDEX IF NOT EXISTS idx_payments_fecha ON membership_payments (fecha_pago DESC);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs (username);

CREATE TABLE IF NOT EXISTS member_nfc_keys (
    id SERIAL PRIMARY KEY,
    cedula VARCHAR(20) NOT NULL REFERENCES members(cedula) ON DELETE CASCADE,
    nfc_id VARCHAR(64) NOT NULL UNIQUE,
    alias VARCHAR(100) NOT NULL DEFAULT 'Llavero',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_member_nfc_keys_uid ON member_nfc_keys(nfc_id);
CREATE INDEX IF NOT EXISTS idx_member_nfc_keys_cedula ON member_nfc_keys(cedula);

