# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Correctly resolve project root whether spec is invoked from root or packaging folder
ROOT_DIR = os.path.abspath(SPECPATH)
if not os.path.exists(os.path.join(ROOT_DIR, 'main.py')):
    ROOT_DIR = os.path.abspath(os.path.join(SPECPATH, '..'))

added_files = [
    (os.path.join(ROOT_DIR, 'db'), 'db'),
    (os.path.join(ROOT_DIR, 'data'), 'data'),
    (os.path.join(ROOT_DIR, '.env.example'), '.'),
]

if os.path.exists(os.path.join(ROOT_DIR, '.cache')):
    added_files.append((os.path.join(ROOT_DIR, '.cache'), '.cache'))

# Ensure data directory exists
if not os.path.exists(os.path.join(ROOT_DIR, 'data')):
    os.makedirs(os.path.join(ROOT_DIR, 'data'), exist_ok=True)

hidden_imports = [
    'flet',
    'flet_desktop',
    'flet.fastapi',
    'fastapi',
    'starlette',
    'uvicorn',
    'psycopg',
    'openpyxl',
    'dotenv',
    'sqlite3',
    'urllib.parse',
    'datetime',
    'core',
    'ui',
    'core.theme',
    'core.db_store',
    'core.mock_data',
    'core.business',
    'core.paths',
    'core.security',
    'core.audio_service',
    'core.bcv_service',
    'core.cash_closure',
    'core.reports_export',
    'core.repositories',
    'core.whatsapp_service',
]

a = Analysis(
    [os.path.join(ROOT_DIR, 'main.py')],
    pathex=[ROOT_DIR],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
