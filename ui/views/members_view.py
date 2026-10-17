"""Members management view with data table, NFC card enrollment and add dialog."""

from __future__ import annotations

import flet as ft
from core.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_DANGER,
    RADIUS_SM, RADIUS_MD, PADDING_MD,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    card_style, heading_text, button_primary,
)
from core.mock_data import MEMBERS, PLANS, register_member, update_member_nfc
from core.audio_service import audio
from core.nfc_service import nfc_reader


class MembersView(ft.Column):
    """Members table with NFC enrollment and add member modal."""

    def __init__(self):
        self._members = MEMBERS.copy()
        self._target_member_for_linking = None

        self.cedula_field = ft.TextField(
            label="Cédula",
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
            label="ID / UID de Tarjeta o Llavero NFC",
            hint_text="Presiona el botón para escanear...",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=True,
        )

        self.nfc_scan_status = ft.Text(
            "Puedes escribir el ID o presionar el botón para leer el llavero en el ACR122U",
            size=11,
            color=TEXT_MUTED,
        )

        self.table_body = ft.Column(
            controls=self._build_rows(),
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )

        # Dialog for adding new member
        self.new_member_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Nuevo Miembro", size=FONT_SIZE_LG),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.cedula_field,
                        self.nombre_field,
                        self.plan_field,
                        ft.Row(
                            controls=[
                                self.nfc_field,
                                ft.IconButton(
                                    icon=ft.Icons.CONTACTLESS,
                                    icon_color=ACCENT_PRIMARY,
                                    tooltip="Escanear llavero en lector ACR122U",
                                    on_click=self._start_scan_for_new_member,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        self.nfc_scan_status,
                    ],
                    spacing=12,
                    tight=True,
                ),
                padding=PADDING_MD,
                width=450,
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

        # Dialog for linking tag to existing member
        self.link_fob_label = ft.Text("Acerque el llavero o tarjeta al lector ACS ACR122U...", size=13, color=TEXT_SECONDARY)
        self.link_fob_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Vincular Llavero NFC", size=FONT_SIZE_MD),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.ProgressRing(width=24, height=24, stroke_width=2.5, color=ACCENT_PRIMARY),
                                ft.Container(width=8),
                                self.link_fob_label,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    tight=True,
                ),
                padding=PADDING_MD,
                width=400,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._cancel_link_fob),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        super().__init__(
            controls=[
                ft.Row(
                    controls=[
                        heading_text("Gestión de Miembros"),
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
                    ft.Text("Cédula", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=110),
                    ft.Text("Nombre", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", expand=True),
                    ft.Text("Plan", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=80),
                    ft.Text("Vencimiento", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=100),
                    ft.Text("Estado", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=90),
                    ft.Text("Llavero / NFC", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=120),
                    ft.Text("Acción", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=90),
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

            nfc_id = m.get("nfc_id") or "Sin asignar"
            cedula = m["cedula"]

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(m["cedula"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=110),
                            ft.Text(m["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500", expand=True),
                            ft.Text(m["plan"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=80),
                            ft.Text(m["vencimiento"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=100),
                            ft.Container(
                                content=ft.Text(m["estado"], size=FONT_SIZE_XS, color=TEXT_PRIMARY, weight="w600"),
                                bgcolor=status_color,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=RADIUS_SM,
                                width=90,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Text(nfc_id, size=FONT_SIZE_SM, color=TEXT_PRIMARY if nfc_id != "Sin asignar" else TEXT_MUTED, width=120),
                            ft.IconButton(
                                icon=ft.Icons.NFC,
                                icon_color=ACCENT_PRIMARY,
                                tooltip="Vincular llavero a este socio",
                                width=90,
                                on_click=lambda e, mem=m: self._open_link_fob_dialog(mem),
                            ),
                        ],
                    ),
                    padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=8),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                )
            )
        return rows

    def _open_dialog(self, e):
        self.nfc_scan_status.value = "Presiona el ícono NFC para escanear en vivo"
        self.nfc_scan_status.color = TEXT_MUTED
        self.page.dialog = self.new_member_dialog
        self.page.open(self.new_member_dialog)

    def _close_dialog(self, e):
        nfc_reader.set_access_mode()
        self.page.close(self.new_member_dialog)

    def _start_scan_for_new_member(self, e):
        self.nfc_scan_status.value = "📡 ACERQUE EL LLAVERO O TARJETA AL LECTOR ACR122U..."
        self.nfc_scan_status.color = ACCENT_PRIMARY
        try:
            self.nfc_scan_status.update()
        except Exception:
            pass

        nfc_reader.set_enroll_mode(self._on_enrolled_new_member_tag)

    def _on_enrolled_new_member_tag(self, uid: str):
        self.nfc_field.value = uid
        self.nfc_scan_status.value = f"✅ Llavero detectado: {uid}"
        self.nfc_scan_status.color = ACCENT_SUCCESS
        audio.announce_tag_scanned(uid)
        if hasattr(self, "page") and self.page:
            try:
                self.nfc_field.update()
                self.nfc_scan_status.update()
            except Exception:
                pass

    def _open_link_fob_dialog(self, member: dict):
        self._target_member_for_linking = member
        self.link_fob_label.value = f"Acerque el llavero para {member['nombre']} al lector ACR122U..."
        self.page.dialog = self.link_fob_dialog
        self.page.open(self.link_fob_dialog)

        nfc_reader.set_enroll_mode(self._on_fob_linked_to_existing_member)

    def _on_fob_linked_to_existing_member(self, uid: str):
        member = self._target_member_for_linking
        if not member:
            return

        update_member_nfc(member["cedula"], uid)
        self._members = MEMBERS.copy()
        self.table_body.controls = self._build_rows()

        first_name = member["nombre"].split()[0]
        audio.speak(f"Llavero vinculado exitosamente a {first_name}")

        if hasattr(self, "page") and self.page:
            try:
                self.table_body.update()
                self.page.close(self.link_fob_dialog)
                self._show_notification(f"Llavero {uid} vinculado a {member['nombre']}", "#0f766e")
            except Exception:
                pass

    def _cancel_link_fob(self, e):
        nfc_reader.set_access_mode()
        self.page.close(self.link_fob_dialog)

    def _save_member(self, e):
        cedula = (self.cedula_field.value or "").strip()
        nombre = (self.nombre_field.value or "").strip()
        plan = (self.plan_field.value or "Basico").strip()
        nfc_id = (self.nfc_field.value or "").strip()

        if not cedula or not nombre:
            self._show_notification("Cédula y nombre son obligatorios", "#7f1d1d")
            return

        try:
            member = register_member(cedula=cedula, nombre=nombre, plan=plan, nfc_id=nfc_id)
        except ValueError as exc:
            self._show_notification(str(exc), "#7f1d1d")
            return

        self._members = MEMBERS.copy()
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
        first_name = nombre.split()[0]
        audio.speak(f"Miembro {first_name} registrado exitosamente")
        self._show_notification("Miembro registrado correctamente", "#0f766e")

    def _show_notification(self, message, color):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=TEXT_PRIMARY),
            bgcolor=color,
        )
        self.page.snack_bar.open = True
        self.page.update()
