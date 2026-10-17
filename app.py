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
from ui.views.dashboard_view import DashboardView
from ui.views.kiosk_view import KioskView
from ui.views.login_view import LoginView
from ui.views.members_view import MembersView
from ui.views.plans_view import PlansView
from ui.views.pos_view import POSView
from ui.views.settings_view import SettingsView


class GymsisApp:
    """Main application controller managing client entrance and admin modes."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.is_admin_authenticated = False
        self.current_admin_view_index = 0
        self.sidebar_items = []
        self.view_container = ft.Container(expand=True)
        self.kiosk_view = None

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
        """Entry point — navigates to the initial route."""
        initial_route = self.page.route or "/"
        self._route_to(initial_route)

    def show_login(self):
        """Backward-compatible entry point for main.py."""
        self.start()

    def _on_route_change(self, e):
        self._route_to(self.page.route)

    def _route_to(self, route: str):
        clean_route = (route or "/").strip().lower()

        if clean_route.startswith("/admin"):
            if not self.is_admin_authenticated:
                self._show_login_view()
            else:
                self._show_admin_layout()
        else:
            # Default route: Public Entrance Kiosk
            self._show_kiosk_view()

    # -----------------------------------------------------------------------
    # Route 1: Public Client Entrance Kiosk
    # -----------------------------------------------------------------------

    def _show_kiosk_view(self):
        self.page.clean()
        self.kiosk_view = KioskView(on_admin_click=self._handle_go_to_admin)
        self.page.add(self.kiosk_view)
        nfc_reader.access_callback = self.kiosk_view._on_nfc_scan
        nfc_reader.status_callback = self.kiosk_view._on_nfc_status_change
        self.page.update()

    def _handle_go_to_admin(self, e=None):
        self.page.route = "/admin"
        self._route_to("/admin")

    def _handle_go_to_kiosk(self, e=None):
        self.page.route = "/"
        self._route_to("/")

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

    def _handle_admin_login(self, token: str):
        clean_token = (token or "").strip().upper()
        valid_tokens = {"ADMIN", "DEMO", "TEST", "GYMSIS"}

        if clean_token in valid_tokens:
            self.is_admin_authenticated = True
            self.page.route = "/admin"
            self._show_admin_layout()
            self._show_notification("Acceso administrativo concedido", ACCENT_SUCCESS)
        else:
            self._show_notification("Token incorrecto. Escribe ADMIN para acceder", ACCENT_DANGER)

    def _handle_admin_logout(self, e=None):
        self.is_admin_authenticated = False
        self.page.route = "/"
        self._show_notification("Sesión cerrada. Regresando a pantalla de entrada.", TEXT_SECONDARY)
        self._show_kiosk_view()

    def _show_admin_layout(self):
        self.page.clean()
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
        items_data = [
            (ft.Icons.DASHBOARD_ROUNDED, "Dashboard"),
            (ft.Icons.NFC_ROUNDED, "Control Accesos"),
            (ft.Icons.PEOPLE_ROUNDED, "Socios y Clientes"),
            (ft.Icons.CARD_MEMBERSHIP_ROUNDED, "Planes de Gimnasio"),
            (ft.Icons.POINT_OF_SALE_ROUNDED, "Punto de Venta"),
            (ft.Icons.SETTINGS_ROUNDED, "Configuración"),
        ]

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

        for i, (icon, label) in enumerate(items_data):
            item = SidebarItem(
                icon=icon,
                label=label,
                on_click=self._make_nav_handler(i),
                active=(i == self.current_admin_view_index),
            )
            self.sidebar_items.append(item)
            sidebar_controls.append(item)

        sidebar_controls.append(ft.Container(expand=True))

        # Bottom return to kiosk button
        sidebar_controls.append(
            ft.Container(
                content=ft.ElevatedButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LOGIN, size=16, color=TEXT_PRIMARY),
                            ft.Text("Entrada Socios", size=12, color=TEXT_PRIMARY, weight="w600"),
                        ],
                        spacing=6,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    bgcolor=BG_INPUT,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                        side=ft.BorderSide(1, BORDER),
                    ),
                    on_click=self._handle_go_to_kiosk,
                ),
                padding=ft.padding.symmetric(horizontal=16, vertical=8),
            )
        )

        sidebar_controls.append(
            ft.Container(
                content=ft.Text("Base de Datos Activa: SQLite", size=10, color=TEXT_MUTED),
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

        return ft.Container(
            content=ft.Row(
                controls=[
                    search,
                    ft.Container(expand=True),
                    clock,
                    ft.Container(width=8),
                    ft.IconButton(
                        icon=ft.Icons.LOGOUT,
                        tooltip="Cerrar Sesión de Administrador",
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
        self.current_admin_view_index = index

        for i, item in enumerate(self.sidebar_items):
            item.set_active(i == index)

        views = [
            DashboardView,
            AccessView,
            MembersView,
            PlansView,
            POSView,
            SettingsView,
        ]

        view_class = views[index]
        new_view = view_class()
        self.view_container.content = new_view

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
        result = process_nfc_scan(uid)
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

        exact_member = find_member_by_cedula(query)
        if exact_member:
            self._navigate_admin_to(2)
            self._show_notification(f"Socio encontrado: {exact_member['nombre']}", ACCENT_SUCCESS)
            return

        matches = search_members_by_name_or_cedula(query)
        if matches:
            self._navigate_admin_to(2)
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
