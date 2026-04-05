"""Settings view — configuration and admin panel."""

import flet as ft
from core.repositories import SettingsRepository, UserRepository, POSProductRepository
from core.theme import (
    ACCENT_PRIMARY, BG_INPUT, BORDER, RADIUS_SM,
    TEXT_MUTED, TEXT_PRIMARY, FONT_SIZE_MD,
    card_style, heading_text,
)


def _snack(page, msg, ok=True):
    try:
        sb = ft.SnackBar(
            content=ft.Text(msg, color=TEXT_PRIMARY),
            bgcolor="#0f766e" if ok else "#7f1d1d",
        )
        page.overlay.append(sb)
        sb.open = True
        page.update()
    except Exception:
        pass


class SettingsView(ft.Column):
    def __init__(self, current_user="invitado", current_role="guest", current_permissions=None):
        settings = SettingsRepository.get_all()
        self.current_user = current_user
        self.current_role = current_role
        self.current_permissions = current_permissions or set()

        self.gym_name = ft.TextField(
            label="Nombre del Gym", value=settings.get("gym_name", "Gymsis"),
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
        )
        self.currency = ft.Dropdown(
            label="Moneda", value=settings.get("currency", "USD"),
            options=[ft.dropdown.Option("USD"), ft.dropdown.Option("VES"), ft.dropdown.Option("EUR")],
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
        )
        self.expiry_days = ft.TextField(
            label="Dias alerta vencimiento", value=str(settings.get("expiry_alert_days", 7)),
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.grace_days = ft.TextField(
            label="Dias de gracia moroso", value=str(settings.get("moroso_grace_days", 0)),
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.allow_inactive = ft.Switch(
            label="Permitir acceso a inactivos", value=bool(settings.get("allow_inactive_access", False)),
            active_color=ACCENT_PRIMARY,
        )
        self.enable_nfc = ft.Switch(
            label="Simulacion NFC", value=bool(settings.get("enable_nfc_simulation", True)),
            active_color=ACCENT_PRIMARY,
        )

        # ── User management ──
        self.new_username = ft.TextField(
            label="Username", hint_text="nuevo.usuario",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
        )
        self.new_password = ft.TextField(
            label="Password", password=True, can_reveal_password=True,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
        )
        roles = UserRepository.list_roles()
        self.new_role = ft.Dropdown(
            label="Rol", value=roles[0] if roles else "viewer",
            options=[ft.dropdown.Option(r) for r in roles] or [ft.dropdown.Option("viewer")],
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
        )
        self.user_list = ft.Column(spacing=6)
        self._refresh_users()

        # ── POS products ──
        self.pos_name = ft.TextField(
            label="Producto", hint_text="Agua 500ml",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
        )
        self.pos_price = ft.TextField(
            label="Precio", hint_text="1.50",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
        )
        self.pos_stock = ft.TextField(
            label="Stock", hint_text="100",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, border_radius=RADIUS_SM,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.pos_is_active = ft.Switch(label="Activo", value=True, active_color=ACCENT_PRIMARY)
        self.pos_list = ft.Column(spacing=6)
        self._refresh_pos()

        super().__init__(
            controls=[
                heading_text("Configuracion"),
                ft.Container(height=8),
                ft.Container(content=ft.Column(controls=[
                    heading_text("General", size=FONT_SIZE_MD),
                    self.gym_name, self.currency,
                ], spacing=12), **card_style()),
                ft.Container(height=12),
                ft.Container(content=ft.Column(controls=[
                    heading_text("Reglas de Negocio", size=FONT_SIZE_MD),
                    self.expiry_days, self.grace_days,
                    self.allow_inactive, self.enable_nfc,
                    ft.ElevatedButton("Guardar Configuracion", on_click=self._save, bgcolor=ACCENT_PRIMARY, color=TEXT_PRIMARY),
                ], spacing=12), **card_style()),
                ft.Container(height=12),
                self._build_admin_section(),
            ],
            spacing=8, expand=True, scroll=ft.ScrollMode.AUTO,
        )

    def _build_admin_section(self):
        can_users = "manage_users" in self.current_permissions
        can_pos = "manage_pos" in self.current_permissions

        if not can_users and not can_pos:
            return ft.Container(content=ft.Column(controls=[
                heading_text("Admin", size=FONT_SIZE_MD),
                ft.Text(f"Usuario: {self.current_user} ({self.current_role})", color=TEXT_MUTED, size=12),
                ft.Text("Sin permisos de administracion.", color=TEXT_MUTED, size=12),
            ], spacing=8), **card_style())

        controls = [
            heading_text("Administracion", size=FONT_SIZE_MD),
            ft.Text(f"Sesion: {self.current_user} ({self.current_role})", color=TEXT_MUTED, size=12),
        ]

        if can_users:
            controls.extend([
                ft.Container(height=8),
                heading_text("Crear / Editar Usuario", size=FONT_SIZE_MD),
                self.new_username, self.new_password, self.new_role,
                ft.ElevatedButton("Crear / Actualizar Usuario", on_click=self._create_user, bgcolor=ACCENT_PRIMARY, color=TEXT_PRIMARY),
                ft.Container(height=8),
                heading_text("Usuarios Registrados", size=FONT_SIZE_MD),
                self.user_list,
            ])

        if can_pos:
            controls.extend([
                ft.Container(height=12),
                heading_text("POS - Productos", size=FONT_SIZE_MD),
                self.pos_name, self.pos_price, self.pos_stock, self.pos_is_active,
                ft.Row(controls=[
                    ft.ElevatedButton("Guardar producto", on_click=self._save_pos, bgcolor=ACCENT_PRIMARY, color=TEXT_PRIMARY),
                    ft.OutlinedButton("Desactivar producto", on_click=self._disable_pos),
                ]),
                self.pos_list,
            ])

        return ft.Container(content=ft.Column(controls=controls, spacing=10), **card_style())

    def _refresh_users(self):
        try:
            users = UserRepository.list_users()
            if not users:
                self.user_list.controls = [ft.Text("Sin usuarios", color=TEXT_MUTED, size=12)]
                return
            self.user_list.controls = [
                ft.Row(controls=[
                    ft.Text(u["username"], color=TEXT_PRIMARY, size=13, width=120),
                    ft.Container(expand=True),
                    ft.Text(u["role"], color=TEXT_MUTED, size=12),
                    ft.Text("activo" if u["is_active"] else "inactivo", color=TEXT_MUTED, size=12),
                    ft.TextButton(
                        "Desactivar" if u["is_active"] else "Activar",
                        on_click=self._mk_toggle_user(u["username"], not u["is_active"]),
                    ),
                    ft.TextButton("Eliminar", on_click=self._mk_del_user(u["username"])),
                ])
                for u in users
            ]
        except Exception:
            self.user_list.controls = [ft.Text("Error cargando usuarios", color=TEXT_MUTED, size=12)]

    def _mk_toggle_user(self, username, new_active):
        def handler(e):
            try:
                ok, msg = UserRepository.set_user_active(username, new_active)
                _snack(self.page, msg, ok)
                if ok:
                    self._refresh_users()
                    self.user_list.update()
            except Exception as ex:
                _snack(self.page, f"Error: {ex}", False)
        return handler

    def _mk_del_user(self, username):
        def handler(e):
            try:
                ok, msg = UserRepository.delete_user(username)
                _snack(self.page, msg, ok)
                if ok:
                    self._refresh_users()
                    self.user_list.update()
            except Exception as ex:
                _snack(self.page, f"Error: {ex}", False)
        return handler

    def _refresh_pos(self):
        try:
            products = POSProductRepository.list_products(active_only=False)
            if not products:
                self.pos_list.controls = [ft.Text("Sin productos", color=TEXT_MUTED, size=12)]
                return
            self.pos_list.controls = [
                ft.Row(controls=[
                    ft.Text(p["nombre"], color=TEXT_PRIMARY, size=13),
                    ft.Container(expand=True),
                    ft.Text(f"${float(p['precio']):.2f}", color=TEXT_MUTED, size=12),
                    ft.Text(f"stock: {int(p['stock'])}", color=TEXT_MUTED, size=12),
                    ft.Text("activo" if p.get("is_active", True) else "inactivo", color=TEXT_MUTED, size=12),
                ])
                for p in products
            ]
        except Exception:
            self.pos_list.controls = [ft.Text("Error cargando productos", color=TEXT_MUTED, size=12)]

    def _create_user(self, e):
        try:
            username = (self.new_username.value or "").strip()
            password = (self.new_password.value or "").strip()
            role = (self.new_role.value or "viewer").strip()

            if not username:
                _snack(self.page, "Username es obligatorio", False)
                return
            if len(username) < 3:
                _snack(self.page, "Username muy corto (min 3 caracteres)", False)
                return
            if not password:
                _snack(self.page, "Password es obligatorio", False)
                return
            if len(password) < 4:
                _snack(self.page, "Password muy corto (min 4 caracteres)", False)
                return

            ok, msg = UserRepository.create_user(username=username, password=password, role=role)
            _snack(self.page, msg, ok)

            if ok:
                self.new_username.value = ""
                self.new_password.value = ""
                self.new_username.update()
                self.new_password.update()
                self._refresh_users()
                self.user_list.update()
        except Exception as ex:
            _snack(self.page, f"Error: {ex}", False)

    def _save_pos(self, e):
        try:
            name = (self.pos_name.value or "").strip()
            if not name:
                _snack(self.page, "Nombre del producto es obligatorio", False)
                return
            try:
                price = float((self.pos_price.value or "0").strip())
                stock = int((self.pos_stock.value or "0").strip())
            except ValueError:
                _snack(self.page, "Precio o stock invalido", False)
                return
            if price < 0:
                _snack(self.page, "Precio no puede ser negativo", False)
                return
            ok, msg = POSProductRepository.save_product(
                nombre=name, precio=price, stock=stock, is_active=bool(self.pos_is_active.value),
            )
            _snack(self.page, msg, ok)
            if ok:
                self._refresh_pos()
                self.pos_list.update()
        except Exception as ex:
            _snack(self.page, f"Error: {ex}", False)

    def _disable_pos(self, e):
        try:
            name = (self.pos_name.value or "").strip()
            if not name:
                _snack(self.page, "Escribe el nombre del producto", False)
                return
            ok, msg = POSProductRepository.delete_product(name)
            _snack(self.page, msg, ok)
            if ok:
                self._refresh_pos()
                self.pos_list.update()
        except Exception as ex:
            _snack(self.page, f"Error: {ex}", False)

    def _save(self, e):
        try:
            settings = SettingsRepository.get_all()
            settings["gym_name"] = (self.gym_name.value or "Gymsis").strip() or "Gymsis"
            settings["currency"] = self.currency.value or "USD"
            try:
                settings["expiry_alert_days"] = max(0, int(self.expiry_days.value or "7"))
            except ValueError:
                settings["expiry_alert_days"] = 7
            try:
                settings["moroso_grace_days"] = max(0, int(self.grace_days.value or "0"))
            except ValueError:
                settings["moroso_grace_days"] = 0
            settings["allow_inactive_access"] = bool(self.allow_inactive.value)
            settings["enable_nfc_simulation"] = bool(self.enable_nfc.value)
            SettingsRepository.save_all(settings)
            _snack(self.page, "Configuracion guardada")
        except Exception as ex:
            _snack(self.page, f"Error: {ex}", False)
