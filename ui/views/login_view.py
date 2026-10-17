"""Login view — perfectly centered, compact admin access card."""

import flet as ft
from core.theme import (
    BG_BASE,
    BG_CARD,
    BG_INPUT,
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    ACCENT_PRIMARY,
    ACCENT_DANGER,
    RADIUS_SM,
    RADIUS_MD,
    RADIUS_LG,
    PADDING_LG,
    PADDING_MD,
    FONT_SIZE_SM,
    FONT_SIZE_MD,
    FONT_SIZE_LG,
    FONT_SIZE_XL,
)


class LoginView(ft.Container):
    """Elegantly centered admin login card (strictly non-stretching)."""

    def __init__(self, on_login=None, on_back_to_kiosk=None):
        self._on_login = on_login
        self._on_back_to_kiosk = on_back_to_kiosk

        self.token_input = ft.TextField(
            label="Token o Contraseña de Administrador",
            hint_text="Escribe: ADMIN o tu token",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=FONT_SIZE_MD,
            width=360,
            on_submit=self._handle_login,
        )

        self.status_text = ft.Text("", size=FONT_SIZE_SM, color=ACCENT_DANGER, visible=False)

        login_card = ft.Container(
            content=ft.Column(
                controls=[
                    # Header Icon & Badge
                    ft.Container(
                        content=ft.Icon(ft.Icons.SHIELD_ROUNDED, size=40, color=ACCENT_PRIMARY),
                        padding=14,
                        bgcolor=ft.Colors.with_opacity(0.12, ACCENT_PRIMARY),
                        border_radius=40,
                    ),
                    ft.Container(height=8),
                    ft.Text("Panel de Administración", size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w700"),
                    ft.Text(
                        "Ingresa tus credenciales para gestionar socios, finanzas y respaldos",
                        size=FONT_SIZE_SM,
                        color=TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=20),
                    self.token_input,
                    ft.Container(height=6),
                    self.status_text,
                    ft.Container(height=12),
                    ft.ElevatedButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.LOGIN, size=18, color=TEXT_PRIMARY),
                                ft.Text("Ingresar al Panel", size=FONT_SIZE_MD, weight="w600", color=TEXT_PRIMARY),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=8,
                        ),
                        bgcolor=ACCENT_PRIMARY,
                        color=TEXT_PRIMARY,
                        on_click=self._handle_login,
                        width=360,
                        style=ft.ButtonStyle(
                            padding=14,
                            shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                        ),
                    ),
                    ft.Container(height=12),
                    ft.TextButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.ARROW_BACK, size=16, color=TEXT_MUTED),
                                ft.Text("Volver a Pantalla de Entrada (Kiosco)", size=13, color=TEXT_MUTED),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=6,
                        ),
                        on_click=self._handle_back,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
                tight=True,
            ),
            width=420,
            padding=PADDING_LG,
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=RADIUS_LG,
        )

        super().__init__(
            content=login_card,
            alignment=ft.Alignment(0, 0),
            expand=True,
            bgcolor=BG_BASE,
        )

    def _handle_login(self, e):
        token = self.token_input.value.strip()
        if not token:
            self.status_text.value = "Por favor ingresa tu token de acceso"
            self.status_text.visible = True
            try:
                self.status_text.update()
            except Exception:
                pass
            return

        if self._on_login:
            self._on_login(token)

    def _handle_back(self, e):
        if self._on_back_to_kiosk:
            self._on_back_to_kiosk(e)

    def show_error(self, message: str):
        self.status_text.value = message
        self.status_text.visible = True
        try:
            self.status_text.update()
        except Exception:
            pass
