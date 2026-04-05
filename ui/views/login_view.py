"""Login view — entry point."""

import flet as ft
from core.theme import (
    BG_BASE, BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, RADIUS_SM, RADIUS_MD, RADIUS_LG, PADDING_LG,
    FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG, FONT_SIZE_2XL,
    card_style,
)


class LoginView(ft.Row):
    """Perfectly centered login card with cedula input and NFC validation."""

    def __init__(self, on_login=None):
        self._on_login = on_login
        self.cedula_input = ft.TextField(
            label="Cedula de Identidad",
            hint_text="Ej: V-12345678",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=FONT_SIZE_MD,
            width=320,
            on_submit=self._handle_login,
        )

        self.status_text = ft.Text("", size=FONT_SIZE_SM, color="", visible=False)

        super().__init__(
            controls=[
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Icon(ft.Icons.SPORTS_GYMNASTICS, size=48, color=ACCENT_PRIMARY),
                            ft.Text("Gymsis", size=FONT_SIZE_2XL, color=TEXT_PRIMARY, weight="w700"),
                            ft.Text("Sistema de Gestion de Gimnasio", size=FONT_SIZE_SM, color=TEXT_SECONDARY),
                            ft.Container(height=24),
                            self.cedula_input,
                            ft.Container(height=8),
                            ft.ElevatedButton(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.NFC, size=18, color=TEXT_PRIMARY),
                                        ft.Text("Validar / Escanear NFC", size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                bgcolor=ACCENT_PRIMARY,
                                color=TEXT_PRIMARY,
                                on_click=self._handle_login,
                                width=320,
                                style=ft.ButtonStyle(
                                    padding=14,
                                    shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                ),
                            ),
                            ft.Container(height=8),
                            ft.OutlinedButton(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.VISIBILITY, size=18, color=TEXT_SECONDARY),
                                        ft.Text("Entrar en Modo Demo", size=FONT_SIZE_SM, weight="w600", color=TEXT_SECONDARY),
                                    ],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    spacing=8,
                                ),
                                width=320,
                                style=ft.ButtonStyle(
                                    side=ft.BorderSide(1, BORDER),
                                    shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                    padding=14,
                                ),
                                on_click=self._handle_demo_login,
                            ),
                            ft.Text(
                                "Tip: tambien puedes ingresar DEMO o TEST en la cedula.",
                                size=FONT_SIZE_SM,
                                color=TEXT_MUTED,
                            ),
                            ft.Container(height=12),
                            self.status_text,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    **card_style(radius=RADIUS_LG, padding=PADDING_LG),
                    width=420,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def _handle_login(self, e):
        cedula = self.cedula_input.value.strip()
        if not cedula:
            self.status_text.value = "Ingresa una cedula valida"
            self.status_text.color = "#f43f5e"
            self.status_text.visible = True
            self.status_text.update()
            return

        if self._on_login:
            self._on_login(cedula)

    def _handle_demo_login(self, e):
        if self._on_login:
            self._on_login("__DEMO__")
