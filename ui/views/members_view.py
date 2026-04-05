"""Members management view with data table and add dialog."""

import flet as ft
from core.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_DANGER,
    RADIUS_SM, RADIUS_MD, PADDING_MD,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    card_style, heading_text, button_primary,
)
from core.mock_data import MEMBERS, PLANS, register_member


class MembersView(ft.Column):
    """Members table with add member modal."""

    def __init__(self):
        self._members = MEMBERS.copy()

        self.cedula_field = ft.TextField(
            label="Cedula",
            hint_text="V-00000000",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.nombre_field = ft.TextField(
            label="Nombre Completo",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.plan_field = ft.Dropdown(
            label="Plan",
            options=[ft.dropdown.Option(k) for k in PLANS.keys()],
            value="Basico",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.nfc_field = ft.TextField(
            label="ID de Tarjeta NFC",
            hint_text="NFC-XXXX",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )

        self.table_body = ft.Column(
            controls=self._build_rows(),
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )

        self.new_member_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Nuevo Miembro", size=FONT_SIZE_LG),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.cedula_field,
                        self.nombre_field,
                        self.plan_field,
                        self.nfc_field,
                    ],
                    spacing=12,
                ),
                padding=PADDING_MD,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._close_dialog),
                ft.ElevatedButton(
                    "Registrar",
                    bgcolor=ACCENT_PRIMARY, color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_member,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        super().__init__(
            controls=[
                ft.Row(
                    controls=[
                        heading_text("Gestion de Miembros"),
                        ft.Container(expand=True),
                        button_primary("+ Nuevo Ingreso", on_click=self._open_dialog),
                    ],
                ),
                ft.Container(height=12),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            self._build_header(),
                            ft.Container(height=1, bgcolor=BORDER),
                            self.table_body,
                        ],
                        spacing=0,
                    ),
                    **card_style(),
                    expand=True,
                ),
            ],
            spacing=8,
            expand=True,
        )

    def _build_header(self):
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text("Cedula", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=120),
                    ft.Text("Nombre", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", expand=True),
                    ft.Text("Plan", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=80),
                    ft.Text("Vencimiento", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=110),
                    ft.Text("Estado", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=90),
                    ft.Text("NFC", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=90),
                ],
            ),
            padding=PADDING_MD,
        )

    def _build_rows(self):
        rows = []
        for m in self._members:
            status_color = ACCENT_SUCCESS if m["estado"] == "Activo" else (
                ACCENT_DANGER if m["estado"] == "Moroso" else TEXT_MUTED
            )
            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(m["cedula"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=120),
                            ft.Text(m["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500", expand=True),
                            ft.Text(m["plan"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=80),
                            ft.Text(m["vencimiento"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=110),
                            ft.Container(
                                content=ft.Text(m["estado"], size=FONT_SIZE_XS, color=TEXT_PRIMARY, weight="w600"),
                                bgcolor=status_color,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=RADIUS_SM,
                                width=90,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Text(m["nfc_id"], size=FONT_SIZE_SM, color=TEXT_MUTED, width=90),
                        ],
                    ),
                    padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=10),
                    border=ft.border.all(1, BORDER),
                    border_radius=0,
                )
            )
        return rows

    def _open_dialog(self, e):
        self.page.dialog = self.new_member_dialog
        self.page.open(self.new_member_dialog)

    def _close_dialog(self, e):
        self.page.close(self.new_member_dialog)

    def _save_member(self, e):
        cedula = (self.cedula_field.value or "").strip()
        nombre = (self.nombre_field.value or "").strip()
        plan = (self.plan_field.value or "Basico").strip()
        nfc_id = (self.nfc_field.value or "").strip()

        if not cedula or not nombre:
            self._show_notification("Cedula y nombre son obligatorios", "#7f1d1d")
            return

        try:
            member = register_member(cedula=cedula, nombre=nombre, plan=plan, nfc_id=nfc_id)
        except ValueError as exc:
            self._show_notification(str(exc), "#7f1d1d")
            return

        self._members.append(member)
        self.table_body.controls = self._build_rows()
        self.table_body.update()

        self.cedula_field.value = ""
        self.nombre_field.value = ""
        self.plan_field.value = "Basico"
        self.nfc_field.value = ""
        self.cedula_field.update()
        self.nombre_field.update()
        self.plan_field.update()
        self.nfc_field.update()

        self.page.close(self.new_member_dialog)
        self._show_notification("Miembro registrado correctamente", "#0f766e")

    def _show_notification(self, message, color):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=TEXT_PRIMARY),
            bgcolor=color,
        )
        self.page.snack_bar.open = True
        self.page.update()
