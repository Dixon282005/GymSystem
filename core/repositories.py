"""Repositories layer for Gymsis.
Centralizes data access, business caching, audit trail triggers, and state synchronization.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core import db_store
from core import mock_data as md


def _sync_member_cache(members: Optional[List[dict]] = None) -> None:
    """Synchronize the in-memory cache with the database records."""
    if members is None:
        members = db_store.load_members()
    md.MEMBERS.clear()
    md.MEMBERS.extend(members)
    md.rebuild_member_index()


class MemberRepository:
    @staticmethod
    def list_all() -> List[dict]:
        members = db_store.load_members()
        _sync_member_cache(members)
        return members

    @staticmethod
    def find_by_cedula(cedula: str) -> Optional[dict]:
        return db_store.find_member_by_cedula(cedula)

    @staticmethod
    def find_by_nfc(nfc_id: str) -> Optional[dict]:
        return db_store.find_member_by_nfc_id(nfc_id)

    @staticmethod
    def search(query: str) -> List[dict]:
        return db_store.search_members(query)

    @staticmethod
    def create_member(
        cedula: str,
        nombre: str,
        plan: str,
        nfc_id: str = "",
        estado: str = "Activo",
        telefono: str = "",
    ) -> Tuple[bool, str]:
        from core.business import get_active_user, log_action

        active_user = get_active_user()
        new_member = md.register_member(
            cedula=cedula,
            nombre=nombre,
            plan=plan,
            nfc_id=nfc_id,
            estado=estado,
            telefono=md.normalize_telefono(telefono),
            creado_por=active_user,
        )
        db_store.save_member(new_member)
        _sync_member_cache()
        log_action(
            "CREAR_SOCIO",
            {
                "cedula": new_member["cedula"],
                "nombre": new_member["nombre"],
                "plan": new_member["plan"],
                "nfc_id": new_member["nfc_id"],
                "estado": new_member["estado"],
                "telefono": new_member.get("telefono", ""),
            },
        )
        return True, "Socio registrado con éxito"

    @staticmethod
    def update_member(
        cedula: str,
        nombre: Optional[str] = None,
        nfc_id: Optional[str] = None,
        telefono: Optional[str] = None,
        plan: Optional[str] = None,
        estado: Optional[str] = None,
    ) -> Tuple[bool, str]:
        from core.business import log_action

        member = MemberRepository.find_by_cedula(cedula)
        if not member:
            return False, "Socio no encontrado"

        nombre = (nombre or "").strip()
        nfc_id = (nfc_id or "").strip()
        telefono_norm = md.normalize_telefono(telefono)

        cambios = {}
        if member.get("nombre") != nombre:
            cambios["nombre"] = {"anterior": member.get("nombre"), "nuevo": nombre}
            member["nombre"] = nombre

        if member.get("nfc_id") != nfc_id:
            cambios["nfc_id"] = {"anterior": member.get("nfc_id"), "nuevo": nfc_id}
            member["nfc_id"] = nfc_id

        if member.get("telefono", "") != telefono_norm:
            cambios["telefono"] = {"anterior": member.get("telefono", ""), "nuevo": telefono_norm}
            member["telefono"] = telefono_norm

        if plan is not None and member.get("plan") != plan:
            cambios["plan"] = {"anterior": member.get("plan"), "nuevo": plan}
            member["plan"] = plan

        if estado is not None and member.get("estado") != estado:
            cambios["estado"] = {"anterior": member.get("estado"), "nuevo": estado}
            member["estado"] = estado

        if not cambios:
            return True, "Sin cambios"

        db_store.save_member(member)
        _sync_member_cache()
        log_action("ACTUALIZAR_MIEMBRO", {"cedula": member["cedula"], "cambios": cambios})
        return True, "Miembro actualizado"

    @staticmethod
    def list_low_attendance(
        min_days: int = 7, estados: Tuple[str, ...] = ("Activo", "Vigente")
    ) -> List[dict]:
        return db_store.list_members_low_attendance(min_days=min_days, estados=estados)

    @staticmethod
    def set_training_status(cedula: str, is_training: bool) -> bool:
        normalized = md.normalize_cedula(cedula)
        for member in md.MEMBERS:
            if md.normalize_cedula(member.get("cedula", "")) == normalized:
                member["entrenando"] = bool(is_training)
                db_store.save_member(member)
                return True
        return False

    @staticmethod
    def update_status(cedula: str, new_status: str, force: bool = False) -> bool:
        from core.business import log_action

        normalized = md.normalize_cedula(cedula)
        for member in md.MEMBERS:
            if md.normalize_cedula(member.get("cedula", "")) == normalized:
                current = member.get("estado")
                if current != new_status or force:
                    member["estado"] = new_status
                    db_store.save_member(member)
                    log_action(
                        "CAMBIO_ESTADO_SOCIO",
                        {"cedula": cedula, "anterior": current, "nuevo": new_status},
                    )
                return True
        return False


class AccessRepository:
    @staticmethod
    def list_recent(limit: int = 50) -> List[dict]:
        events = db_store.load_access_log(limit=limit)
        return list(events)

    @staticmethod
    def add_event(event: dict) -> bool:
        md.ACCESS_LOG.insert(0, event)
        return db_store.save_access_event(event)

    @staticmethod
    def get_last_checkin(cedula: str) -> Optional[dict]:
        return db_store.get_last_checkin(cedula)

    @staticmethod
    def get_last_checkins_map(cedulas: List[str]) -> Dict[str, dict]:
        raw = db_store.get_last_checkins_for_cedulas(cedulas)
        result = {}
        for ced, val in raw.items():
            result[md.normalize_cedula(ced)] = val
        return result

    @staticmethod
    def format_last_checkin(cedula: str) -> str:
        last = AccessRepository.get_last_checkin(cedula)
        if not last:
            return "Sin registros"
        fecha = last.get("fecha", "")
        hora = last.get("hora", "")
        return f"{fecha} {hora}".strip()

    @staticmethod
    def format_last_checkin_short(cedula: str) -> str:
        event = AccessRepository.get_last_checkin(cedula)
        if not event:
            return "Nunca"
        fecha = event.get("fecha", "")
        hora = event.get("hora", "")
        if not fecha:
            return "Nunca"
        try:
            event_date = datetime.strptime(fecha, "%Y-%m-%d").date()
            days = (date.today() - event_date).days
            if days == 0:
                return f"Hoy {hora}"
            if days == 1:
                return f"Ayer {hora}"
            return f"Hace {days} d"
        except ValueError:
            return fecha

    @staticmethod
    def snapshot() -> dict:
        events = AccessRepository.list_recent(limit=100)
        members = MemberRepository.list_all()
        present = sum(1 for m in members if m.get("entrenando"))
        allowed_today = sum(1 for e in events if e.get("status") == "PERMITIDO")
        denied_today = sum(1 for e in events if e.get("status") != "PERMITIDO")
        return {
            "present_count": present,
            "allowed_today": allowed_today,
            "denied_today": denied_today,
            "recent_events": events[:20],
        }


class SalesRepository:
    @staticmethod
    def list_recent(limit: int = 100) -> List[dict]:
        sales = db_store.load_sales(limit=limit)
        return list(sales)

    @staticmethod
    def add_row(row: dict) -> bool:
        from core.business import log_action

        md.DAILY_SALES.append(row)
        ok = db_store.save_sale_row(row)
        log_action("VENTA_POS", {"producto": row.get("producto"), "monto": row.get("monto")})
        return ok

    @staticmethod
    def totals() -> dict:
        sales = SalesRepository.list_recent(limit=500)
        total = sum(float(s.get("monto", 0.0)) for s in sales)
        count = len(sales)
        avg = (total / count) if count else 0.0
        return {"total": total, "count": count, "avg": avg}


class SettingsRepository:
    @staticmethod
    def get_all() -> dict:
        settings = dict(md.APP_SETTINGS)
        if db_store.is_db_enabled():
            db_settings = db_store.load_settings()
            settings.update(db_settings)
        return settings

    @staticmethod
    def save_all(settings: dict) -> bool:
        from core.business import log_action

        md.APP_SETTINGS.update(settings)
        result = db_store.save_settings(settings)
        log_action("CONFIGURACION_MODIFICADA", {"keys": list(settings.keys())})
        return result


class UserRepository:
    @staticmethod
    def authenticate(username: str, password: str) -> Optional[dict]:
        return db_store.authenticate_user(username, password)

    @staticmethod
    def permissions(username: str) -> set:
        return db_store.get_user_permissions(username)

    @staticmethod
    def list_roles() -> List[str]:
        return db_store.list_roles()

    @staticmethod
    def list_users() -> List[dict]:
        return db_store.list_users()

    @staticmethod
    def create_user(username: str, password: str, role: str) -> Tuple[bool, str]:
        from core.business import log_action

        ok, msg = db_store.create_user(username, password, role)
        if ok:
            log_action("CREAR_USUARIO", {"username": username, "role": role})
        return ok, msg

    @staticmethod
    def update_user(username: str, role: str, password: Optional[str] = None) -> Tuple[bool, str]:
        from core.business import log_action

        ok, msg = db_store.update_user(username, role, password)
        if ok:
            log_action(
                "MODIFICAR_USUARIO",
                {"username": username, "role": role, "password_changed": bool(password)},
            )
        return ok, msg

    @staticmethod
    def set_user_active(username: str, is_active: bool) -> Tuple[bool, str]:
        from core.business import log_action

        ok, msg = db_store.set_user_active(username, is_active)
        if ok:
            log_action("ESTADO_USUARIO", {"username": username, "is_active": is_active})
        return ok, msg

    @staticmethod
    def delete_user(username: str) -> Tuple[bool, str]:
        from core.business import log_action

        ok, msg = db_store.delete_user(username)
        if ok:
            log_action("ELIMINAR_USUARIO", {"username": username})
        return ok, msg


class POSProductRepository:
    @staticmethod
    def list_products(active_only: bool = False) -> List[dict]:
        products = db_store.load_pos_products(active_only=active_only)
        if not products and not active_only:
            return list(md.POS_PRODUCTS)
        return products

    @staticmethod
    def save_product(
        nombre: str, precio: float, stock: int, is_active: bool = True, old_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        from core.business import log_action

        nombre = nombre.strip()
        product_dict = {
            "nombre": nombre,
            "precio": float(precio),
            "stock": int(stock),
            "is_active": bool(is_active),
        }

        if old_name and old_name.strip().lower() != nombre.lower():
            old_clean = old_name.strip()
            # Rename in memory
            for p in md.POS_PRODUCTS:
                if p.get("nombre", "").strip().lower() == old_clean.lower():
                    p.update(product_dict)
                    break
            else:
                md.POS_PRODUCTS.append(product_dict)

            ok, msg = db_store.rename_pos_product(old_clean, product_dict)
            if ok:
                log_action("GUARDAR_PRODUCTO_POS", {"accion": "renombrar", "anterior": old_clean, "nuevo": product_dict})
                return True, f"Producto '{old_clean}' renombrado a '{nombre}' y actualizado."
            return False, f"Error al renombrar producto: {msg}"

        existing = next((p for p in md.POS_PRODUCTS if p.get("nombre") == nombre), None)
        if existing:
            existing.update(product_dict)
        else:
            md.POS_PRODUCTS.append(product_dict)

        ok, msg = db_store.save_pos_product(product_dict)
        if ok:
            log_action("GUARDAR_PRODUCTO_POS", product_dict)
        return ok, msg

    @staticmethod
    def delete_product(nombre: str) -> Tuple[bool, str]:
        from core.business import log_action

        target = nombre.strip()
        for p in md.POS_PRODUCTS:
            if p.get("nombre") == target:
                p["is_active"] = False
        ok, msg = db_store.delete_pos_product(target)
        if ok:
            log_action("ELIMINAR_PRODUCTO_POS", {"nombre": target})
        return ok, msg

    @staticmethod
    def set_product_active(nombre: str, is_active: bool) -> Tuple[bool, str]:
        target = nombre.strip()
        for p in md.POS_PRODUCTS:
            if p.get("nombre") == target:
                p["is_active"] = bool(is_active)
        return db_store.set_product_active(target, is_active)

    @staticmethod
    def decrement_stock(nombre: str, qty: int = 1) -> bool:
        target = nombre.strip()
        for p in md.POS_PRODUCTS:
            if p.get("nombre") == target:
                p["stock"] = max(0, int(p.get("stock", 0)) - qty)
        return db_store.decrement_stock_product(target, qty)


class PlanRepository:
    @staticmethod
    def list_plans(active_only: bool = False) -> List[dict]:
        plans = db_store.load_plans(active_only=active_only)
        if not plans and not active_only:
            return list(md.PLANS)
        return plans

    @staticmethod
    def save_plan(
        nombre: str,
        precio: float,
        descripcion: str = "",
        dias: int = 30,
        is_active: bool = True,
    ) -> Tuple[bool, str]:
        from core.business import log_action

        nombre = nombre.strip()
        existing = next((p for p in md.PLANS if p.get("nombre") == nombre), None)
        plan_dict = {
            "nombre": nombre,
            "precio": float(precio),
            "descripcion": descripcion,
            "dias": int(dias),
            "is_active": bool(is_active),
        }
        if existing:
            existing.update(plan_dict)
        else:
            md.PLANS.append(plan_dict)

        ok, msg = db_store.save_plan(plan_dict)
        if ok:
            log_action("GUARDAR_PLAN", plan_dict)
        return ok, msg

    @staticmethod
    def delete_plan(nombre: str) -> Tuple[bool, str]:
        from core.business import log_action

        target = nombre.strip()
        members_with_plan = [m for m in MemberRepository.list_all() if m.get("plan") == target]
        if members_with_plan:
            return False, f"No se puede eliminar el plan '{target}' porque tiene clientes asignados."

        for p in md.PLANS:
            if p.get("nombre") == target:
                p["is_active"] = False

        ok, msg = db_store.delete_plan(target)
        if ok:
            log_action("ELIMINAR_PLAN", {"nombre": target})
        return ok, msg

    @staticmethod
    def set_plan_active(nombre: str, is_active: bool) -> Tuple[bool, str]:
        from core.business import log_action

        target = nombre.strip()
        if not is_active:
            members_with_plan = [m for m in MemberRepository.list_all() if m.get("plan") == target]
            if members_with_plan:
                return False, f"No se puede desactivar el plan '{target}' porque tiene clientes asignados."

        for p in md.PLANS:
            if p.get("nombre") == target:
                p["is_active"] = bool(is_active)

        ok, msg = db_store.set_plan_active(target, is_active)
        if ok:
            log_action("ESTADO_PLAN", {"nombre": target, "is_active": is_active})
        return ok, msg


class PaymentRepository:
    @staticmethod
    def register_payment(
        cedula: str,
        plan: str,
        monto: float,
        dias: int = 30,
        metodo: str = "efectivo",
        nota: str = "",
        referencia: str = "",
        tasa_tipo: str = "BCV",
        tasa_valor: float = 0.0,
    ) -> Tuple[bool, str]:
        from core.business import get_active_user, log_action

        payment = {
            "cedula": cedula,
            "plan": plan,
            "monto": monto,
            "dias": dias,
            "metodo": metodo,
            "nota": nota,
            "referencia": referencia,
            "tasa_tipo": tasa_tipo,
            "tasa_valor": tasa_valor,
            "registrado_por": get_active_user(),
        }
        ok, msg = db_store.save_membership_payment(payment)
        if ok:
            _sync_member_cache()
            log_action("PAGO_MEMBRESIA", payment)
        return ok, msg

    @staticmethod
    def list_payments(cedula: Optional[str] = None, limit: int = 100) -> List[dict]:
        return db_store.load_membership_payments(cedula=cedula, limit=limit)


class AuditLogRepository:
    @staticmethod
    def list_logs(
        limit: int = 100,
        action_filter: Optional[str] = None,
        user_filter: Optional[str] = None,
        query_search: Optional[str] = None,
    ) -> List[dict]:
        return db_store.load_audit_logs(
            limit=limit,
            action_filter=action_filter,
            user_filter=user_filter,
            query_search=query_search,
        )

    @staticmethod
    def list_actions() -> List[str]:
        return db_store.load_audit_actions()

    @staticmethod
    def list_users() -> List[str]:
        return db_store.load_audit_users()


def compute_plan_popularity(members: Optional[List[dict]] = None) -> str:
    """Return the name of the most popular plan across all members."""
    if members is None:
        members = MemberRepository.list_all()
    plans = [m.get("plan", "-") for m in members]
    if not plans:
        return "-"
    return Counter(plans).most_common(1)[0][0]
