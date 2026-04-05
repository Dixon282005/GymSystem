"""Main app orchestrator — handles navigation between views."""

import flet as ft
from core.theme import (
    BG_BASE, BG_CARD, BORDER, TEXT_PRIMARY, TEXT_MUTED,
    ACCENT_PRIMARY, FONT_SIZE_LG,
)
from core.db_store import hydrate_mock_data_from_db
from core.repositories import MemberRepository, UserRepository
from ui.components.widgets import SidebarItem, LiveClock, GlobalSearch
from ui.views.login_view import LoginView
from ui.views.dashboard_view import DashboardView
from ui.views.access_view import AccessView
from ui.views.members_view import MembersView
from ui.views.pos_view import POSView
from ui.views.settings_view import SettingsView


ROLE_DEFAULT_PERMISSIONS = {
    "admin": {"view_dashboard", "view_access", "view_members", "view_pos", "view_settings", "manage_users", "manage_pos"},
    "staff": {"view_dashboard", "view_access", "view_members", "view_pos"},
    "viewer": {"view_dashboard", "view_access"},
    "member": {"view_dashboard", "view_access"},
    "guest": set(),
}


def show_snack(page: ft.Page, message: str, color: str = "#334155"):
    """Show a snackbar using overlay API (Flet 0.84+)."""
    sb = ft.SnackBar(content=ft.Text(message, color=TEXT_PRIMARY), bgcolor=color)
    page.overlay.append(sb)
    sb.open = True
    page.update()


class GymsisApp:
    """Main application controller."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.current_view_index = 0
        self.sidebar_items = []
        self.nav_items = []
        self.view_container = ft.Container(expand=True)
        self.sidebar_container = ft.Container(width=240)
        self.current_user = "invitado"
        self.current_role = "guest"
        self.current_permissions = set()

        self._configure_page()

    def _configure_page(self):
        self.page.title = "Gymsis"
        self.page.bgcolor = BG_BASE
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.fonts = {"default": "Segoe UI, system-ui, sans-serif"}
        self.page.padding = 0
        self.page.spacing = 0

    def _build_layout(self):
        self.sidebar_container = self._build_sidebar()
        header = self._build_header()
        self.view_container = ft.Container(
            padding=20,
            expand=True,
            bgcolor=BG_BASE,
        )

        self.page.add(
            ft.Row(
                controls=[
                    self.sidebar_container,
                    ft.VerticalDivider(width=1, color=BORDER),
                    ft.Column(
                        controls=[header, self.view_container],
                        expand=True,
                        spacing=0,
                    ),
                ],
                expand=True,
                spacing=0,
            )
        )

        self._navigate_to(0)

    def _build_sidebar(self):
        items_data = [
            (ft.Icons.DASHBOARD, "Dashboard", DashboardView, "view_dashboard"),
            (ft.Icons.NFC, "Check-in", AccessView, "view_access"),
            (ft.Icons.PEOPLE, "Miembros", MembersView, "view_members"),
            (ft.Icons.POINT_OF_SALE, "Finanzas / POS", POSView, "view_pos"),
            (ft.Icons.SETTINGS, "Configuracion", SettingsView, "view_settings"),
        ]

        self.sidebar_items = []
        self.nav_items = []
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

        for icon, label, view_class, permission in items_data:
            if permission not in self.current_permissions:
                continue

            index = len(self.nav_items)
            self.nav_items.append((view_class, permission))
            item = SidebarItem(
                icon=icon,
                label=label,
                on_click=self._make_nav_handler(index),
                active=(index == 0),
            )
            self.sidebar_items.append(item)
            sidebar_controls.append(item)

        sidebar_controls.append(ft.Container(expand=True))
        sidebar_controls.append(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(f"{self.current_user} ({self.current_role})", size=11, color=TEXT_MUTED),
                        ft.Text("v0.2.0", size=11, color=TEXT_MUTED),
                    ],
                    spacing=2,
                ),
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
                    ft.IconButton(
                        icon=ft.Icons.SYNC,
                        icon_color=TEXT_MUTED,
                        tooltip="Refrescar datos",
                        on_click=self._refresh_data,
                    ),
                    clock,
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=20,
            bgcolor=BG_CARD,
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        )

    def _make_nav_handler(self, index):
        def handler(e):
            self._navigate_to(index)
        return handler

    def _navigate_to(self, index):
        if not self.nav_items:
            self.view_container.content = ft.Text("Sin vistas permitidas", color=TEXT_MUTED)
            self.view_container.update()
            return

        if index >= len(self.nav_items):
            index = 0

        hydrate_mock_data_from_db()
        self.current_view_index = index

        for i, item in enumerate(self.sidebar_items):
            item.set_active(i == index)

        view_class, _permission = self.nav_items[index]
        if view_class is SettingsView:
            self.view_container.content = view_class(
                current_user=self.current_user,
                current_role=self.current_role,
                current_permissions=self.current_permissions,
            )
        else:
            self.view_container.content = view_class()

        if hasattr(self.view_container, "update"):
            self.view_container.update()

    def _handle_global_search(self, e):
        query = (e.control.value or "").strip()
        if not query:
            return

        exact_member = MemberRepository.find_by_cedula(query)
        if exact_member:
            self._navigate_to(2)
            show_snack(self.page, f"Miembro encontrado: {exact_member['nombre']}", "#0f766e")
            return

        matches = MemberRepository.search(query)
        if matches:
            self._navigate_to(2)
            show_snack(self.page, f"{len(matches)} coincidencias para '{query}'", "#0f766e")
        else:
            show_snack(self.page, f"Sin resultados para '{query}'", "#7f1d1d")

    def show_login(self):
        """Show login overlay before accessing the app."""
        login_view = LoginView(on_login=self._handle_login)
        overlay = ft.Container(content=login_view, expand=True, bgcolor=BG_BASE)
        self.page.add(overlay)

    def _handle_login(self, username, password):
        """Validate admin/staff credentials and transition to main app."""
        username = (username or "").strip().lower()
        password = (password or "").strip()

        if not username or not password:
            show_snack(self.page, "Usuario y clave requeridos", "#7f1d1d")
            return

        auth = UserRepository.authenticate(username, password)
        if not auth:
            show_snack(self.page, "Credenciales invalidas", "#7f1d1d")
            return

        self.current_user = auth["username"]
        self.current_role = auth["role"]
        self.current_permissions = UserRepository.permissions(auth["username"]) or set(
            ROLE_DEFAULT_PERMISSIONS.get(auth["role"], set())
        )

        self.page.clean()
        self._build_layout()
        show_snack(self.page, f"Sesion iniciada como {self.current_role}", "#0f766e")

    def _refresh_data(self, e=None):
        hydrate_mock_data_from_db()
        self._navigate_to(self.current_view_index)
