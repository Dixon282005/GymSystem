"""Initial database seed values for fresh Gymsis installs."""
from __future__ import annotations
import os

SEED_USERS = [
    {
        "username": os.getenv("GYMSIS_ADMIN_USER", "admin"),
        "password": os.getenv("GYMSIS_ADMIN_PASSWORD", "admin123"),
        "role": "admin",
    },
    {
        "username": "gerente",
        "password": os.getenv("GYMSIS_GERENTE_PASSWORD", "gerente123"),
        "role": "staff",
    },
]

SEED_PLANS = [
    {
        "nombre": "Pase Diario",
        "precio": 2.50,
        "descripcion": "Entrenamiento individual por el día",
        "dias": 1,
        "is_active": True,
    },
    {
        "nombre": "Semanal",
        "precio": 7.00,
        "descripcion": "Pase semanal completo",
        "dias": 7,
        "is_active": True,
    },
    {
        "nombre": "Mensual",
        "precio": 20.00,
        "descripcion": "Acceso ilimitado a sala de pesas y máquinas",
        "dias": 30,
        "is_active": True,
    },
]
