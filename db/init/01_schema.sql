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
    PRIMARY KEY (role_id, permission_id)
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

CREATE INDEX IF NOT EXISTS idx_access_log_event_time ON access_log (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales (sold_at DESC);
CREATE INDEX IF NOT EXISTS idx_pos_products_active ON pos_products (is_active);
CREATE INDEX IF NOT EXISTS idx_membership_payments_cedula ON membership_payments (cedula);
CREATE INDEX IF NOT EXISTS idx_membership_payments_fecha ON membership_payments (fecha_pago DESC);
