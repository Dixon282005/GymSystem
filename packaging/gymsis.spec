# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Correctly resolve project root whether spec is invoked from root or packaging folder
ROOT_DIR = os.path.abspath(SPECPATH)
if not os.path.exists(os.path.join(ROOT_DIR, 'main.py')):
    ROOT_DIR = os.path.abspath(os.path.join(SPECPATH, '..'))

# Ensure data directory exists
data_dir = os.path.join(ROOT_DIR, 'data')
if not os.path.exists(data_dir):
    os.makedirs(data_dir, exist_ok=True)

added_files = [
    (os.path.join(ROOT_DIR, 'db'), 'db'),
    (os.path.join(ROOT_DIR, 'data'), 'data'),
    (os.path.join(ROOT_DIR, '.env.example'), '.'),
]

# Collect package data files (critical for Flet icons.json, Flutter runtime binaries, etc.)
for pkg in ['flet', 'flet_desktop', 'fastapi', 'starlette', 'uvicorn', 'edge_tts', 'psycopg']:
    try:
        added_files.extend(collect_data_files(pkg))
    except Exception as e:
        print(f"Warning: collect_data_files for {pkg}: {e}")

# Deduplicate added_files by (normpath(src), dst)
seen = set()
unique_added_files = []
for src, dst in added_files:
    if os.path.exists(src):
        key = (os.path.normpath(src), dst)
        if key not in seen:
            seen.add(key)
            unique_added_files.append((src, dst))

added_files = unique_added_files

hidden_imports = [
    'flet',
    'flet_desktop',
    'flet.fastapi',
    'fastapi',
    'starlette',
    'uvicorn',
    'psycopg',
    'psycopg_binary',
    'openpyxl',
    'dotenv',
    'sqlite3',
    'urllib.parse',
    'datetime',
    'edge_tts',
    'aiohttp',
    'core',
    'ui',
    'core.theme',
    'core.db_store',
    'core.mock_data',
    'core.business',
    'core.event_bus',
    'core.paths',
    'core.security',
    'core.audio_service',
    'core.bcv_service',
    'core.cash_closure',
    'core.reports_export',
    'core.repositories',
    'core.whatsapp_service',
    'ui.views.access_view',
    'ui.views.audit_logs_view',
    'ui.views.dashboard_view',
    'ui.views.kiosk_view',
    'ui.views.login_view',
    'ui.views.members_view',
    'ui.views.plans_view',
    'ui.views.pos_view',
    'ui.views.products_view',
    'ui.views.reports_view',
    'ui.views.settings_view',
]

try:
    for mod in collect_submodules('flet'):
        if not mod.startswith('flet.testing'):
            hidden_imports.append(mod)
except Exception:
    pass

hidden_imports = list(dict.fromkeys(hidden_imports))

a = Analysis(
    [os.path.join(ROOT_DIR, 'main.py')],
    pathex=[ROOT_DIR],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'flet.testing'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Gymsis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

