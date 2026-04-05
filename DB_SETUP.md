# Gymsis PostgreSQL Setup (Docker)

## 1) Levantar solo la base de datos

```powershell
docker compose -f docker-compose.db.yml up -d
```

PostgreSQL queda disponible en:
- Host: `localhost`
- Puerto: `5433`
- DB: `gymsis`
- Usuario: `gymsis`
- Password: `gymsis_dev`

## 2) Variables para la app desktop

La app carga automaticamente `.env` al iniciar.

Archivo sugerido:

```env
GYMSIS_RUN_MODE=desktop
GYMSIS_USE_DB=true
DATABASE_URL=postgresql://gymsis:gymsis_dev@localhost:5433/gymsis
```

Luego ejecutar la app:

```powershell
c:/Users/cpustorevzla/Desktop/Gymsis/.venv/Scripts/python.exe main.py
```

## 3) Esquema de base de datos

El esquema inicial se crea automaticamente desde:
- `db/init/01_schema.sql`

Tablas creadas:
- `members`
- `access_log`
- `sales`
- `app_settings`

## 4) Integracion actual

Persistencia conectada desde:
- `core/db_store.py`
- `core/business.py` (accesos y ventas)
- `core/mock_data.py` (registro de miembro)
- `ui/views/settings_view.py` (configuracion)
- `main.py` (bootstrap de DB al iniciar)
- `core/env_loader.py` (carga de `.env` para desktop)

Si DB no esta disponible, la app sigue en modo memoria sin romperse.

## 5) Apagar DB

```powershell
docker compose -f docker-compose.db.yml down
```
