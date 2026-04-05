"""Repository layer to centralize data access for desktop modules."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from core import mock_data as md
from core import db_store


class MemberRepository:
    @staticmethod
    def list_all() -> list[dict]:
        if db_store.is_db_enabled():
            members = db_store.load_members()
            if members:
                return members
        return list(md.MEMBERS)

    @staticmethod
    def find_by_cedula(cedula: str) -> dict | None:
        normalized = md.normalize_cedula(cedula)
        if not normalized:
            return None
        for member in MemberRepository.list_all():
            if md.normalize_cedula(member.get("cedula")) == normalized:
                return member
        return None

    @staticmethod
    def search(query: str) -> list[dict]:
        q = md.normalize_cedula(query)
        if not q:
            return []

        results = []
        for member in MemberRepository.list_all():
            cedula = md.normalize_cedula(member.get("cedula"))
            nombre = (member.get("nombre") or "").upper()
            if q in cedula or q in nombre:
                results.append(member)
        return results

    @staticmethod
    def create_member(cedula: str, nombre: str, plan: str, nfc_id: str) -> dict:
        return md.register_member(cedula=cedula, nombre=nombre, plan=plan, nfc_id=nfc_id)

    @staticmethod
    def set_training_status(cedula: str, is_training: bool) -> bool:
        normalized = md.normalize_cedula(cedula)
        for member in md.MEMBERS:
            if md.normalize_cedula(member.get("cedula")) == normalized:
                member["entrenando"] = bool(is_training)
                db_store.save_member(member)
                return True
        return False

    @staticmethod
    def update_status(cedula: str, new_status: str) -> bool:
        normalized = md.normalize_cedula(cedula)
        for member in md.MEMBERS:
            if md.normalize_cedula(member.get("cedula")) == normalized:
                member["estado"] = new_status
                db_store.save_member(member)
                return True
        return False

    @staticmethod
    def renew_membership(cedula: str, plan: str, dias: int) -> bool:
        """Renew a member's membership and update expiry."""
        normalized = md.normalize_cedula(cedula)
        for member in md.MEMBERS:
            if md.normalize_cedula(member.get("cedula")) == normalized:
                member["plan"] = plan
                member["estado"] = "Activo"
                member["vencimiento"] = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d")
                db_store.save_member(member)
                md.rebuild_member_index()
                return True
        return False


class AccessRepository:
    @staticmethod
    def list_recent(limit: int = 300) -> list[dict]:
        if db_store.is_db_enabled():
            events = db_store.load_access_log(limit=limit)
            if events:
                return events
        return list(md.ACCESS_LOG)[:limit]

    @staticmethod
    def add_event(event: dict) -> bool:
        md.ACCESS_LOG.insert(0, event)
        db_store.save_access_event(event)
        return True

    @staticmethod
    def snapshot() -> dict:
        events = AccessRepository.list_recent(limit=1000)
        present = [m for m in MemberRepository.list_all() if m.get("entrenando")]
        allowed_today = sum(1 for e in events if e.get("status") == "PERMITIDO")
        denied_today = sum(1 for e in events if e.get("status") == "DENEGADO")
        return {
            "present": present,
            "allowed_today": allowed_today,
            "denied_today": denied_today,
            "total_events": len(events),
        }


class SalesRepository:
    @staticmethod
    def list_recent(limit: int = 500) -> list[dict]:
        if db_store.is_db_enabled():
            sales = db_store.load_sales(limit=limit)
            if sales:
                return sales
        return list(md.DAILY_SALES)[:limit]

    @staticmethod
    def add_row(row: dict) -> bool:
        md.DAILY_SALES.append(row)
        db_store.save_sale_row(row)
        return True

    @staticmethod
    def totals() -> dict:
        sales = SalesRepository.list_recent(limit=5000)
        total = sum(float(s.get("monto", 0)) for s in sales)
        count = len(sales)
        avg = (total / count) if count else 0.0
        return {"total": total, "count": count, "avg_ticket": avg}


class SettingsRepository:
    @staticmethod
    def get_all() -> dict:
        settings = dict(md.APP_SETTINGS)
        if db_store.is_db_enabled():
            db_settings = db_store.load_settings()
            if db_settings:
                settings.update(db_settings)
        return settings

    @staticmethod
    def save_all(settings: dict) -> bool:
        md.APP_SETTINGS.update(settings)
        return db_store.save_settings(md.APP_SETTINGS)


class UserRepository:
    @staticmethod
    def authenticate(username: str, password: str) -> dict | None:
        return db_store.authenticate_user(username, password)

    @staticmethod
    def permissions(username: str) -> set[str]:
        return db_store.get_user_permissions(username)

    @staticmethod
    def list_roles() -> list[str]:
        return db_store.list_roles()

    @staticmethod
    def list_users() -> list[dict]:
        return db_store.list_users()

    @staticmethod
    def create_user(username: str, password: str, role: str) -> tuple[bool, str]:
        return db_store.create_user(username, password, role)

    @staticmethod
    def set_user_active(username: str, is_active: bool) -> tuple[bool, str]:
        return db_store.set_user_active(username, is_active)

    @staticmethod
    def delete_user(username: str) -> tuple[bool, str]:
        return db_store.delete_user(username)


class POSProductRepository:
    @staticmethod
    def list_products(active_only: bool = True) -> list[dict]:
        if db_store.is_db_enabled():
            products = db_store.load_pos_products(active_only=active_only)
            if products:
                return products

        fallback = list(md.POS_PRODUCTS)
        if active_only:
            return [p for p in fallback if p.get("is_active", True)]
        return fallback

    @staticmethod
    def save_product(nombre: str, precio: float, stock: int, is_active: bool = True) -> tuple[bool, str]:
        product = {
            "nombre": (nombre or "").strip(),
            "precio": precio,
            "stock": stock,
            "is_active": bool(is_active),
        }

        existing = next((p for p in md.POS_PRODUCTS if p.get("nombre") == product["nombre"]), None)
        if existing:
            existing.update(product)
        else:
            md.POS_PRODUCTS.append(product)

        if db_store.is_db_enabled():
            return db_store.save_pos_product(product)
        return True, "Producto guardado en memoria"

    @staticmethod
    def delete_product(nombre: str) -> tuple[bool, str]:
        target = (nombre or "").strip()
        for p in md.POS_PRODUCTS:
            if (p.get("nombre") or "").strip() == target:
                p["is_active"] = False
                break

        if db_store.is_db_enabled():
            return db_store.delete_pos_product(target)
        return True, "Producto desactivado en memoria"


class PaymentRepository:
    """Membership payment operations."""

    @staticmethod
    def register_payment(
        cedula: str,
        plan: str,
        monto: float,
        dias: int = 30,
        metodo: str = "efectivo",
        nota: str = "",
    ) -> tuple[bool, str]:
        """Register a membership payment and renew the member."""
        payment = {
            "cedula": cedula,
            "plan": plan,
            "monto": monto,
            "dias": dias,
            "metodo": metodo,
            "nota": nota,
        }
        ok, msg = db_store.save_membership_payment(payment)
        if ok:
            # Also update in-memory member
            MemberRepository.renew_membership(cedula, plan, dias)
        return ok, msg

    @staticmethod
    def list_payments(cedula: str | None = None, limit: int = 200) -> list[dict]:
        return db_store.load_membership_payments(cedula=cedula, limit=limit)


def compute_plan_popularity() -> str:
    plans = [m.get("plan", "-") for m in MemberRepository.list_all()]
    if not plans:
        return "-"
    return Counter(plans).most_common(1)[0][0]
