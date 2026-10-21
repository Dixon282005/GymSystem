"""Main app orchestrator — handles routing between the Public Entrance Kiosk
and the Authenticated Admin Backoffice.
"""

from __future__ import annotations

import flet as ft

from core.mock_data import find_member_by_cedula, search_members_by_name_or_cedula
from core.nfc_service import nfc_reader
from core.theme import (
    ACCENT_DANGER,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    BG_BASE,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FONT_SIZE_LG,
    FONT_SIZE_SM,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from ui.components.widgets import GlobalSearch, LiveClock, SidebarItem
from ui.views.access_view import AccessView
from ui.views.audit_logs_view import AuditLogsView
from ui.views.dashboard_view import DashboardView
from ui.views.kiosk_view import KioskView
from ui.views.login_view import LoginView
from ui.views.members_view import MembersView
from ui.views.plans_view import PlansView
from ui.views.pos_view import POSView
from ui.views.products_view import ProductsView
from ui.views.reports_view import ReportsView
from ui.views.settings_view import SettingsView
from core.cash_closure import run_pending_daily_closures



_SERVER_SESSION = {
    "authenticated": False,
    "user": None,
    "active_view": "dashboard",
    "route": "/admin",
}


_ALL_VIEWS_CONFIG = [
    {
        "id": "dashboard",
        "icon": ft.Icons.DASHBOARD_ROUNDED,
        "label": "Dashboard",
        "view": DashboardView,
        "permission": "view_dashboard",
    },
    {
        "id": "access",
        "icon": ft.Icons.NFC_ROUNDED,
        "label": "Control Accesos",
        "view": AccessView,
        "permission": "view_access",
    },
    {
        "id": "members",
        "icon": ft.Icons.PEOPLE_ROUNDED,
        "label": "Socios y Clientes",
        "view": MembersView,
        "permission": "view_members",
    },
    {
        "id": "plans",
        "icon": ft.Icons.CARD_MEMBERSHIP_ROUNDED,
        "label": "Planes de Gimnasio",
        "view": PlansView,
        "permission": "view_plans",
    },
    {
        "id": "pos",
        "icon": ft.Icons.POINT_OF_SALE_ROUNDED,
        "label": "Punto de Venta",
        "view": POSView,
        "permission": "view_pos",
    },
    {
        "id": "inventory",
        "icon": ft.Icons.INVENTORY_2_ROUNDED,
        "label": "Inventario POS",
        "view": ProductsView,
        "permission": "manage_pos",
    },
    {
        "id": "reports",
        "icon": ft.Icons.ASSESSMENT_ROUNDED,
        "label": "Reportes del Turno",
        "view": ReportsView,
        "permission": "view_reports",
    },
    {
        "id": "audit",
        "icon": ft.Icons.SECURITY_ROUNDED,
        "label": "Auditoría / Logs",
        "view": AuditLogsView,
        "permission": "view_audit",
    },
    {
        "id": "settings",
        "icon": ft.Icons.SETTINGS_ROUNDED,
        "label": "Configuración",
        "view": SettingsView,
        "permission": "view_settings",
    },
]


class GymsisApp:
    """Main application controller managing client entrance and admin modes."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.is_admin_authenticated = False
        self.current_user = None
        self.current_user_permissions = set()
        self.allowed_views = list(_ALL_VIEWS_CONFIG)
        self.current_admin_view_index = 0
        self.sidebar_items = []
        self.view_container = ft.Container(expand=True)
        self.kiosk_view = None
        self._login_attempts = 0
        self._lockout_until = 0.0

        self._configure_page()
        self._setup_nfc()

        # Set up route change listener
        self.page.on_route_change = self._on_route_change

    def _configure_page(self):
        self.page.title = "Gymsis • Control de Acceso"
        self.page.bgcolor = BG_BASE
        self.page.window_width = 1280
        self.page.window_height = 800
        self.page.window_min_width = 900
        self.page.window_min_height = 600
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.fonts = {"default": "Segoe UI, system-ui, sans-serif"}

    def _setup_nfc(self):
        """Initialize the background NFC reader thread."""
        nfc_reader.start()

    def start(self):
        """Entry point — navigates to the initial route and runs any pending daily closures."""
        try:
            run_pending_daily_closures()
        except Exception as ex:
            print(f"[app] Error running pending daily closures: {ex}")

        # Check client_storage for existing authenticated cryptographic session token
        session_token = None
        saved_view = None
        try:
            if hasattr(self.page, "client_storage") and self.page.client_storage:
                session_token = self.page.client_storage.get("gymsis_session_token")
                saved_view = self.page.client_storage.get("gymsis_active_view")
        except Exception as cs_err:
            print(f"[app] Error reading client_storage: {cs_err}")

        initial_route = (self.page.route or "/").strip().lower()

        # If opening explicitly /kiosk, show entrance kiosk
        if initial_route.startswith("/kiosk"):
            self.page.route = "/kiosk"
            self._show_kiosk_view()
            return

        # Restore authenticated backoffice session (from token or server session)
        authenticated_user = None
        if session_token:
            from core.security import verify_session_token
            session_info = verify_session_token(session_token)
            if session_info:
                authenticated_user = {"username": session_info["username"], "role": session_info.get("role", "admin")}
        elif _SERVER_SESSION.get("authenticated") and _SERVER_SESSION.get("user"):
            authenticated_user = _SERVER_SESSION["user"]

        if authenticated_user:
            from core.repositories import UserRepository
            from core.business import set_active_user
            saved_user = authenticated_user["username"]
            saved_role = authenticated_user.get("role", "admin")

            self.is_admin_authenticated = True
            self.current_user = {"username": saved_user, "role": saved_role}
            self.current_user_permissions = UserRepository.permissions(saved_user)
            set_active_user(saved_user)

            # Compute accessible views for restored user
            if saved_role == "admin":
                self.allowed_views = list(_ALL_VIEWS_CONFIG)
            else:
                self.allowed_views = [
                    cfg for cfg in _ALL_VIEWS_CONFIG
                    if cfg["permission"] in self.current_user_permissions
                ]
            if not self.allowed_views:
                self.allowed_views = [_ALL_VIEWS_CONFIG[0]]

            target_view_id = saved_view or _SERVER_SESSION.get("active_view", "dashboard")
            view_idx = 0
            if target_view_id:
                for idx, cfg in enumerate(self.allowed_views):
                    if cfg["id"] == target_view_id:
                        view_idx = idx
                        break
            self.current_admin_view_index = view_idx

            self.page.route = "/admin"
            self._show_admin_layout()
            return

        # If not authenticated, always show LoginView on default routes (/ or /admin)
        self._route_to(initial_route)

    def show_login(self):
        """Backward-compatible entry point for main.py."""
        self.start()

    def _on_route_change(self, e):
        self._route_to(self.page.route)

    def _route_to(self, route: str):
        clean_route = (route or "/").strip().lower()

        if clean_route.startswith("/kiosk"):
            self._show_kiosk_view()
        elif clean_route.startswith("/admin") or clean_route in ("/", ""):
            if not self.is_admin_authenticated:
                self._show_login_view()
            else:
                self._show_admin_layout()
        else:
            if not self.is_admin_authenticated:
                self._show_login_view()
            else:
                self._show_admin_layout()

    # -----------------------------------------------------------------------
    # Route 1: Public Client Entrance Kiosk
    # -----------------------------------------------------------------------

    def _show_kiosk_view(self):
        self.page.clean()
        self.kiosk_view = KioskView(on_admin_click=self._handle_go_to_admin)
        self.page.add(self.kiosk_view)
        nfc_reader.access_callback = self.kiosk_view._on_nfc_scan
        nfc_reader.status_callback = self.kiosk_view._on_nfc_status_change
        if nfc_reader.is_connected:
            self.kiosk_view._on_nfc_status_change(True, "ACR122U Activo")
        self.page.update()

    def _handle_go_to_admin(self, e=None):
        self.page.route = "/admin"
        self._route_to("/admin")

    def _handle_go_to_kiosk(self, e=None):
        self.page.route = "/kiosk"
        self._route_to("/kiosk")

    def _handle_open_kiosk_new_window(self, e=None):
        try:
            self.page.route = "/kiosk"
            self._show_kiosk_view()
        except Exception as ex:
            print(f"[app] Error launching kiosk: {ex}")

    # -----------------------------------------------------------------------
    # Route 2: Admin Login & Backoffice
    # -----------------------------------------------------------------------

    def _show_login_view(self):
        self.page.clean()
        login_view = LoginView(
            on_login=self._handle_admin_login,
            on_back_to_kiosk=self._handle_go_to_kiosk,
        )
        self.page.add(login_view)
        self.page.update()

    def _handle_admin_login(self, username_or_token: str, password: Optional[str] = None):
        import time
        import hashlib
        import os
        import secrets
        from core.repositories import UserRepository
        from core.business import set_active_user, log_action
        from core.security import create_session_token

        now = time.time()
        if now < self._lockout_until:
            wait_sec = max(1, int(self._lockout_until - now))
            self._show_notification(
                f"Acceso bloqueado por intentos fallidos. Espera {wait_sec}s.",
                ACCENT_DANGER,
            )
            return

        # 1. Attempt credentials authentication
        authenticated_user = None
        if password is not None:
            uname_clean = (username_or_token or "admin").strip()
            pwd_clean = (password or "").strip()
            authenticated_user = UserRepository.authenticate(uname_clean, pwd_clean)
        else:
            clean_token = (username_or_token or "").strip()
            if not clean_token:
                self._show_notification("Por favor ingresa tu clave de acceso", ACCENT_DANGER)
                return

            if ":" in clean_token:
                u, p = clean_token.split(":", 1)
                authenticated_user = UserRepository.authenticate(u.strip(), p.strip())
            else:
                authenticated_user = UserRepository.authenticate("admin", clean_token)
                if not authenticated_user:
                    authenticated_user = UserRepository.authenticate("gerente", clean_token)

            # 2. Check token fallback ONLY if explicitly configured with a custom secret
            configured_token = os.getenv("GYMSIS_ADMIN_TOKEN", "").strip()
            if configured_token and configured_token.upper() != "ADMIN":
                token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
                expected_hash = hashlib.sha256(configured_token.encode("utf-8")).hexdigest()
                if secrets.compare_digest(token_hash, expected_hash):
                    authenticated_user = {"username": "admin", "role": "admin"}

        if authenticated_user:
            self._login_attempts = 0
            self.current_user = authenticated_user
            uname = authenticated_user["username"]
            role = authenticated_user.get("role", "admin")
            self.current_user_permissions = UserRepository.permissions(uname)

            set_active_user(uname)
            log_action("INICIO_SESION", {"usuario": uname, "rol": role})
            self.is_admin_authenticated = True
            _SERVER_SESSION["authenticated"] = True
            _SERVER_SESSION["user"] = authenticated_user
            _SERVER_SESSION["route"] = "/admin"
            self.page.route = "/admin"

            # Persist tamper-proof session token in client_storage
            try:
                if hasattr(self.page, "client_storage") and self.page.client_storage:
                    signed_token = create_session_token(uname, role)
                    self.page.client_storage.set("gymsis_session_token", signed_token)
                    self.page.client_storage.remove("gymsis_auth_user")
                    self.page.client_storage.remove("gymsis_auth_role")
            except Exception:
                pass

            self._show_admin_layout()
            self._show_notification(f"Bienvenido, {uname.title()} ({role.upper()})", ACCENT_SUCCESS)
        else:
            self._login_attempts += 1
            if self._login_attempts >= 5:
                self._lockout_until = time.time() + 30.0
                self._login_attempts = 0
                self._show_notification(
                    "Demasiados intentos erróneos. Acceso bloqueado por 30 segundos por seguridad.",
                    ACCENT_DANGER,
                )
            else:
                remaining = 5 - self._login_attempts
                self._show_notification(
                    f"Credenciales de acceso incorrectas ({remaining} intentos restantes)",
                    ACCENT_DANGER,
                )

    def _handle_admin_logout(self, e=None):
        from core.business import get_active_user, log_action, set_active_user
        log_action("CIERRE_SESION", {"usuario": get_active_user()})
        set_active_user("sistema")
        self.is_admin_authenticated = False
        self.current_user = None
        self.current_user_permissions.clear()
        _SERVER_SESSION["authenticated"] = False
        _SERVER_SESSION["user"] = None
        _SERVER_SESSION["active_view"] = "dashboard"
        try:
            if hasattr(self.page, "client_storage") and self.page.client_storage:
                self.page.client_storage.remove("gymsis_session_token")
                self.page.client_storage.remove("gymsis_auth_user")
                self.page.client_storage.remove("gymsis_auth_role")
                self.page.client_storage.remove("gymsis_active_view")
        except Exception:
            pass
        self.page.route = "/"
        self._show_notification("Sesión cerrada.", TEXT_SECONDARY)
        self._show_login_view()

    def _show_admin_layout(self):
        self.page.clean()

        # RBAC: compute accessible views according to user permissions
        role = (self.current_user or {}).get("role", "viewer")
        if role == "admin":
            self.allowed_views = list(_ALL_VIEWS_CONFIG)
        else:
            self.allowed_views = [
                cfg for cfg in _ALL_VIEWS_CONFIG
                if cfg["permission"] in self.current_user_permissions
            ]
        if not self.allowed_views:
            self.allowed_views = [_ALL_VIEWS_CONFIG[0]]

        if self.current_admin_view_index >= len(self.allowed_views):
            self.current_admin_view_index = 0

        sidebar = self._build_sidebar()
        header = self._build_header()
        self.view_container = self._build_view_container()

        main_content = ft.Column(
            controls=[header, self.view_container],
            expand=True,
            spacing=0,
        )

        self.page.add(
            ft.Row(
                controls=[
                    sidebar,
                    ft.VerticalDivider(width=1, color=BORDER),
                    main_content,
                ],
                expand=True,
                spacing=0,
            )
        )

        self._navigate_admin_to(self.current_admin_view_index)
        self.page.update()

    def _build_sidebar(self):
        self.sidebar_items = []
        sidebar_controls = []

        sidebar_controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FITNESS_CENTER, color=ACCENT_PRIMARY, size=24),
                        ft.Text("Gymsis Admin", size=FONT_SIZE_LG, color=TEXT_PRIMARY, weight="w700"),
                    ],
                    spacing=10,
                ),
                padding=20,
            )
        )

        sidebar_controls.append(
            ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.symmetric(horizontal=16))
        )

        for i, cfg in enumerate(self.allowed_views):
            item = SidebarItem(
                icon=cfg["icon"],
                label=cfg["label"],
                on_click=self._make_nav_handler(i),
                active=(i == self.current_admin_view_index),
            )
            self.sidebar_items.append(item)
            sidebar_controls.append(item)

        sidebar_controls.append(ft.Container(expand=True))

        # Bottom open kiosk in new window button
        sidebar_controls.append(
            ft.Container(
                content=ft.ElevatedButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.OPEN_IN_NEW, size=16, color=TEXT_PRIMARY),
                            ft.Text("Entrada Socios (Pantalla)", size=12, color=TEXT_PRIMARY, weight="w600"),
                        ],
                        spacing=6,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    bgcolor=BG_INPUT,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                        side=ft.BorderSide(1, BORDER),
                    ),
                    tooltip="Abrir pantalla de acceso de clientes",
                    on_click=self._handle_open_kiosk_new_window,
                ),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
            )
        )

        from core.db_store import get_active_engine
        engine_label = "PostgreSQL" if get_active_engine() == "postgresql" else "SQLite"
        sidebar_controls.append(
            ft.Container(
                content=ft.Text(f"Base de Datos: {engine_label}", size=10, color=TEXT_MUTED),
                padding=ft.padding.only(left=20, bottom=12),
            )
        )

        return ft.Container(
            content=ft.Column(controls=sidebar_controls, spacing=4),
            width=240,
            bgcolor=BG_CARD,
            padding=ft.padding.only(top=8, bottom=8),
        )

    def _build_header(self):
        search = GlobalSearch(on_search=self._handle_global_search)
        clock = LiveClock()

        user_name = (self.current_user or {}).get("username", "admin").title()
        user_role = (self.current_user or {}).get("role", "admin").upper()

        user_badge = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ACCOUNT_CIRCLE_ROUNDED, size=18, color=ACCENT_PRIMARY),
                    ft.Text(f"{user_name} • {user_role}", size=12, color=TEXT_PRIMARY, weight="w600"),
                ],
                spacing=6,
            ),
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            bgcolor=BG_INPUT,
            border_radius=RADIUS_SM,
            border=ft.Border.all(1, BORDER),
        )

        return ft.Container(
            content=ft.Row(
                controls=[
                    search,
                    ft.Container(expand=True),
                    clock,
                    ft.Container(width=10),
                    ft.ElevatedButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.FITNESS_CENTER, size=15, color=ft.Colors.WHITE),
                                ft.Text("Pantalla Acceso", size=12, color=ft.Colors.WHITE, weight="w700"),
                            ],
                            spacing=6,
                        ),
                        bgcolor=ACCENT_PRIMARY,
                        tooltip="Ir a Pantalla de Entrada de Socios (Kiosco)",
                        on_click=self._handle_open_kiosk_new_window,
                    ),
                    ft.Container(width=6),
                    user_badge,
                    ft.Container(width=4),
                    ft.IconButton(
                        icon=ft.Icons.LOGOUT,
                        tooltip="Cerrar Sesión",
                        icon_color=TEXT_MUTED,
                        on_click=self._handle_admin_logout,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=16,
            bgcolor=BG_CARD,
            border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)) if hasattr(ft, "Border") else ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        )

    def _build_view_container(self):
        return ft.Container(
            padding=20,
            expand=True,
            bgcolor=BG_BASE,
        )

    def _make_nav_handler(self, index):
        def handler(e):
            self._navigate_admin_to(index)
        return handler

    def _navigate_admin_to(self, index: int):
        if not self.allowed_views or index >= len(self.allowed_views):
            index = 0

        self.current_admin_view_index = index

        # Persist active view ID in both server session and client_storage for page reloads
        if self.allowed_views and index < len(self.allowed_views):
            active_view_id = self.allowed_views[index]["id"]
            _SERVER_SESSION["active_view"] = active_view_id
            try:
                if hasattr(self.page, "client_storage") and self.page.client_storage:
                    self.page.client_storage.set("gymsis_active_view", active_view_id)
            except Exception:
                pass

        for i, item in enumerate(self.sidebar_items):
            item.set_active(i == index)

        view_class = self.allowed_views[index]["view"]
        new_view = view_class()
        self.view_container.content = new_view

        nfc_reader.set_access_mode()
        if isinstance(new_view, AccessView):
            nfc_reader.access_callback = new_view._on_nfc_scan
            nfc_reader.status_callback = new_view._on_nfc_status_change
        else:
            nfc_reader.access_callback = self._handle_background_admin_nfc_scan

        try:
            self.view_container.update()
        except Exception:
            pass

    def _handle_background_admin_nfc_scan(self, uid: str):
        """Record NFC tap when admin is working elsewhere and show real-time notification."""
        from core.business import process_nfc_scan
        result = process_nfc_scan(uid, min_interval=3.0)
        if result.get("cooldown"):
            return

        action = result.get("action", "ENTRADA" if result.get("allowed") else "DENEGADO")
        member = result.get("member")
        name = member["nombre"] if member else "Llavero Desconocido"

        if action == "SALIDA":
            status_msg = f"Salida registrada: {name}"
            color = "#0891b2"
        elif action == "ENTRADA":
            status_msg = f"¡Bienvenido, {name}!"
            color = ACCENT_SUCCESS
        else:
            status_msg = f"Acceso Denegado ({result.get('reason', '')}): {name}"
            color = ACCENT_DANGER

        self._show_notification(status_msg, color)

    def _handle_global_search(self, e):
        query = (e.control.value or "").strip()
        if not query:
            return

        members_idx = next((i for i, v in enumerate(self.allowed_views) if v["id"] == "members"), None)
        if members_idx is None:
            self._show_notification("No tienes permisos para consultar socios", ACCENT_DANGER)
            return

        exact_member = find_member_by_cedula(query)
        if exact_member:
            self._navigate_admin_to(members_idx)
            self._show_notification(f"Socio encontrado: {exact_member['nombre']}", ACCENT_SUCCESS)
            return

        matches = search_members_by_name_or_cedula(query)
        if matches:
            self._navigate_admin_to(members_idx)
            self._show_notification(f"{len(matches)} socios coinciden con '{query}'", ACCENT_SUCCESS)
        else:
            self._show_notification(f"Sin resultados para '{query}'", ACCENT_DANGER)

    def _show_notification(self, message: str, color: str):
        if hasattr(self, "page") and self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=TEXT_PRIMARY, weight="w500"),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            try:
                self.page.update()
            except Exception:
                pass
