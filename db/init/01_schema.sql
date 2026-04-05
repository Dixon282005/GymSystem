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

CREATE INDEX IF NOT EXISTS idx_access_log_event_time ON access_log (event_time DESC);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales (sold_at DESC);
