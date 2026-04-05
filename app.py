"""Main app orchestrator — handles navigation between views."""

import flet as ft
from core.theme import (
    BG_BASE, BG_CARD, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_PRIMARY, FONT_SIZE_LG,
)
from core.mock_data import find_member_by_cedula, search_members_by_name_or_cedula
from ui.components.widgets import SidebarItem, LiveClock, GlobalSearch
from ui.views.login_view import LoginView
from ui.views.dashboard_view import DashboardView
from ui.views.access_view import AccessView
from ui.views.members_view import MembersView
from ui.views.pos_view import POSView
from ui.views.settings_view import SettingsView


class GymsisApp:
    """Main application controller."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.current_view_index = 0
        self.sidebar_items = []
        self.view_container = ft.Container(expand=True)
        self.sidebar_container = ft.Container(width=240)

        self._configure_page()

    def _configure_page(self):
        self.page.title = "Gymsis"
        self.page.bgcolor = BG_BASE
        self.page.window_width = 1280
        self.page.window_height = 800
        self.page.window_min_width = 900
        self.page.window_min_height = 600
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.fonts = {"default": "Segoe UI, system-ui, sans-serif"}

    def _build_layout(self):
        self.sidebar_container = self._build_sidebar()
        header = self._build_header()
        self.view_container = self._build_view_container()

        self.main_content = ft.Column(
            controls=[header, self.view_container],
            expand=True,
            spacing=0,
        )

        self.page.add(
            ft.Row(
                controls=[
                    self.sidebar_container,
                    ft.VerticalDivider(width=1, color=BORDER),
                    self.main_content,
                ],
                expand=True,
                spacing=0,
            )
        )

        self._navigate_to(0)

    def _build_sidebar(self):
        items_data = [
            (ft.Icons.DASHBOARD, "Dashboard"),
            (ft.Icons.NFC, "Accesos"),
            (ft.Icons.PEOPLE, "Miembros"),
            (ft.Icons.POINT_OF_SALE, "Finanzas / POS"),
            (ft.Icons.SETTINGS, "Configuracion"),
        ]

        self.sidebar_items = []
        sidebar_controls = []

        sidebar_controls.append(
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SPORTS_GYMNASTICS, color=ACCENT_PRIMARY, size=24),
                        ft.Text("Gymsis", size=FONT_SIZE_LG, color=TEXT_PRIMARY, weight="w700"),
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
                active=(i == 0),
            )
            self.sidebar_items.append(item)
            sidebar_controls.append(item)

        sidebar_controls.append(ft.Container(expand=True))
        sidebar_controls.append(
            ft.Container(
                content=ft.Text("v0.1.0", size=11, color=TEXT_MUTED),
                padding=20,
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
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=20,
            bgcolor=BG_CARD,
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        )

    def _build_view_container(self):
        return ft.Container(
            padding=24,
            expand=True,
            bgcolor=BG_BASE,
        )

    def _show_message(self, message, color="#334155"):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=TEXT_PRIMARY),
            bgcolor=color,
        )
        self.page.snack_bar.open = True
        self.page.update()

    def _make_nav_handler(self, index):
        def handler(e):
            self._navigate_to(index)
        return handler

    def _navigate_to(self, index):
        self.current_view_index = index

        for i, item in enumerate(self.sidebar_items):
            item.set_active(i == index)

        views = [
            DashboardView,
            AccessView,
            MembersView,
            POSView,
            SettingsView,
        ]

        view_class = views[index]
        self.view_container.content = view_class()

        if hasattr(self.view_container, "update"):
            self.view_container.update()

    def _handle_global_search(self, e):
        query = (e.control.value or "").strip()
        if not query:
            return

        exact_member = find_member_by_cedula(query)
        if exact_member:
            self._navigate_to(2)
            self._show_message(f"Miembro encontrado: {exact_member['nombre']}", color="#0f766e")
            return

        matches = search_members_by_name_or_cedula(query)
        if matches:
            self._navigate_to(2)
            self._show_message(f"{len(matches)} coincidencias para '{query}'", color="#0f766e")
        else:
            self._show_message(f"Sin resultados para '{query}'", color="#7f1d1d")

    def show_login(self):
        """Show login overlay before accessing the app."""
        login_view = LoginView(on_login=self._handle_login)

        overlay = ft.Container(
            content=login_view,
            expand=True,
            bgcolor=BG_BASE,
        )

        self.page.add(overlay)

    def _handle_login(self, cedula):
        """Validate cedula and transition to main app."""
        raw_value = (cedula or "").strip()
        demo_tokens = {"DEMO", "TEST", "MOCK", "ADMIN", "GYMSIS"}

        if raw_value.upper() in demo_tokens or raw_value == "__DEMO__":
            self.page.clean()
            self._build_layout()
            self._show_message("Modo demo activado", color="#0f766e")
            return

        member = find_member_by_cedula(raw_value)

        if member:
            self.page.clean()
            self._build_layout()
        else:
            self._show_message("Cedula no registrada o inactiva", color="#7f1d1d")
