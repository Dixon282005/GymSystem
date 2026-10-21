"""Members management view with full CRUD, Venezuelan Cédula validation,
bimonetary membership payment/renewal dialog at BCV rate, and live NFC enrollment.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
import flet as ft

from core.theme import (
    BG_CARD,
    BG_INPUT,
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    ACCENT_WARNING,
    ACCENT_DANGER,
    RADIUS_SM,
    RADIUS_MD,
    PADDING_MD,
    FONT_SIZE_XS,
    FONT_SIZE_SM,
    FONT_SIZE_MD,
    FONT_SIZE_LG,
    card_style,
    heading_text,
    button_primary,
)
from core.mock_data import (
    MEMBERS,
    PLANS,
    register_member,
    update_member,
    remove_member,
    update_member_nfc,
)
from core.db_store import load_plans
from core.bcv_service import bcv_service
from core.business import process_membership_payment
from core.event_bus import event_bus
from core.nfc_service import nfc_reader


# Default plan prices in USD for automatic filling in renewals
PLAN_PRICES = {
    "Basico": 25.0,
    "Mensual": 30.0,
    "Trimestral": 75.0,
    "Semestral": 140.0,
    "Anual": 260.0,
    "Estudiante": 20.0,
    "VIP": 50.0,
    "Diario": 3.0,
    "Semanal": 10.0,
}


class MembersView(ft.Column):
    """Full CRUD Members view with live NFC enrollment, Venezuelan Cédula validation and BCV payments."""

    def __init__(self):
        super().__init__(spacing=8, expand=True)

        self._target_member_for_linking = None
        self._target_member_for_deletion = None
        self._target_member_for_payment = None

        # Search and Filter state
        self.search_field = ft.TextField(
            hint_text="Buscar por nombre o cédula...",
            prefix_icon=ft.Icons.SEARCH,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=13,
            height=38,
            width=230,
            on_change=self._on_search_or_filter_change,
        )

        self.status_filter = ft.Dropdown(
            label="Filtrar",
            value="ACTIVOS Y MOROSOS",
            options=[
                ft.dropdown.Option("ACTIVOS Y MOROSOS", text="ACTIVOS Y MOROSOS"),
                ft.dropdown.Option("SOLO ACTIVOS", text="SOLO ACTIVOS"),
                ft.dropdown.Option("SOLO MOROSOS", text="SOLO MOROSOS"),
                ft.dropdown.Option("EN EL GYM", text="EN EL GYM"),
                ft.dropdown.Option("DESACTIVADOS", text="DESACTIVADOS / INACTIVOS"),
                ft.dropdown.Option("TODOS", text="TODOS (INCLUIR DESACTIVADOS)"),
            ],
            width=230,
            height=38,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=13,
            on_change=self._on_search_or_filter_change,
        )

        # -------------------------------------------------------------------
        # Fields for NEW Member Dialog
        # -------------------------------------------------------------------
        self.new_member_error_text = ft.Text("", size=12, color=ACCENT_DANGER, weight="w600", expand=True)
        self.new_member_error_banner = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ACCENT_DANGER, size=20),
                    self.new_member_error_text,
                ],
                spacing=8,
            ),
            bgcolor=ft.Colors.with_opacity(0.12, ACCENT_DANGER),
            border=ft.Border.all(1, ACCENT_DANGER),
            border_radius=RADIUS_SM,
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
            visible=False,
        )

        self.cedula_prefix = ft.Dropdown(
            options=[
                ft.dropdown.Option("V"),
                ft.dropdown.Option("E"),
                ft.dropdown.Option("J"),
                ft.dropdown.Option("G"),
                ft.dropdown.Option("P"),
            ],
            value="V",
            width=85,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.cedula_number = ft.TextField(
            label="Cédula",
            hint_text="Ej: 12345678",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            expand=1,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.nombre_field = ft.TextField(
            label="Nombre Completo",
            hint_text="Ej: Carlos Pérez",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.telefono_field = ft.TextField(
            label="Teléfono (Opcional)",
            hint_text="Ej: 04141234567",
            keyboard_type=ft.KeyboardType.PHONE,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^[0-9+\s\-]*$", replacement_string=""),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        initial_plan_opts = self._get_plan_options()
        default_plan_val = initial_plan_opts[0].key if initial_plan_opts else "Basico"

        self.plan_field = ft.Dropdown(
            label="Plan",
            options=list(initial_plan_opts),
            value=default_plan_val,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            on_change=self._on_new_member_plan_change,
        )
        self.new_pay_amount_usd = ft.TextField(
            label="Monto Inicial a Pagar ($)",
            value="25.00",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^\d*\.?\d{0,2}$", replacement_string=""),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
            on_change=self._on_new_member_amount_change,
        )
        self.new_pay_bcv_rate_label = ft.Text(f"Tasa BCV: {bcv_service.get_rate():.2f}", size=11, color=TEXT_MUTED)
        self.new_pay_amount_bs = ft.Text("Bs. 0,00", size=13, color=ACCENT_PRIMARY, weight="w700")

        self.new_pay_method = ft.Dropdown(
            label="Método de Pago",
            options=[
                ft.dropdown.Option("Efectivo USD"),
                ft.dropdown.Option("Efectivo Bs."),
                ft.dropdown.Option("Pago Móvil"),
                ft.dropdown.Option("Punto de Venta"),
                ft.dropdown.Option("Transferencia Bancaria"),
                ft.dropdown.Option("Zelle"),
            ],
            value="Efectivo USD",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )

        self.new_pay_ref = ft.TextField(
            label="Referencia / Comprobante de Pago",
            hint_text="Ej: PM-481920 o Efectivo en Caja",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )

        self.nfc_field = ft.TextField(
            label="ID / UID Llavero NFC (Opcional - Puede saltarse)",
            hint_text="Opcional: acerque el llavero o deje vacío",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.nfc_scan_status = ft.Text(
            "Opcional: Si el socio no tiene llavero, déjalo vacío o presiona el botón para escanear en ACR122U.",
            size=11,
            color=TEXT_MUTED,
        )

        # -------------------------------------------------------------------
        # Fields for EDIT Member Dialog
        # -------------------------------------------------------------------
        self.edit_cedula_field = ft.TextField(
            label="Cédula (Identificador)",
            read_only=True,
            bgcolor=BG_INPUT,
            color=TEXT_MUTED,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.edit_nombre_field = ft.TextField(
            label="Nombre Completo",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.edit_telefono_field = ft.TextField(
            label="Teléfono (Opcional)",
            hint_text="Ej: 04141234567",
            keyboard_type=ft.KeyboardType.PHONE,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^[0-9+\s\-]*$", replacement_string=""),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.edit_plan_field = ft.Dropdown(
            label="Plan",
            options=list(initial_plan_opts),
            value=default_plan_val,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.edit_estado_field = ft.Dropdown(
            label="Estado",
            options=[
                ft.dropdown.Option("Activo"),
                ft.dropdown.Option("Moroso"),
                ft.dropdown.Option("Inactivo"),
            ],
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.edit_venc_field = ft.TextField(
            label="Fecha Vencimiento (YYYY-MM-DD)",
            hint_text="YYYY-MM-DD",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.edit_nfc_field = ft.TextField(
            label="Llavero / UID NFC",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.edit_nfc_status = ft.Text("", size=11, color=TEXT_MUTED)

        # -------------------------------------------------------------------
        # Fields for PAYMENT & RENEWAL Dialog (Bimonetary at BCV Rate)
        # -------------------------------------------------------------------
        self.pay_member_info = ft.Text("", size=14, weight="w600", color=TEXT_PRIMARY)
        self.pay_plan_field = ft.Dropdown(
            label="Plan a Renovar",
            options=list(initial_plan_opts),
            value=default_plan_val,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            on_change=self._on_pay_plan_change,
            expand=1,
        )
        self.pay_days_field = ft.TextField(
            label="Días de Membresía",
            value="30",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.pay_amount_usd = ft.TextField(
            label="Monto USD ($)",
            value="25.00",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^\d*\.?\d{0,2}$", replacement_string=""),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            expand=1,
            on_change=self._on_pay_amount_change,
        )
        self.pay_bcv_rate_label = ft.Text("Tasa BCV: 0.00 Bs/$", size=12, color=TEXT_MUTED)
        self.pay_amount_bs = ft.Text("Total Bs: 0,00", size=15, color=ACCENT_PRIMARY, weight="w700")
        self.pay_method_field = ft.Dropdown(
            label="Método de Pago",
            options=[
                ft.dropdown.Option("Pago Móvil"),
                ft.dropdown.Option("Punto de Venta"),
                ft.dropdown.Option("Efectivo USD ($)"),
                ft.dropdown.Option("Efectivo Bs."),
                ft.dropdown.Option("Transferencia"),
                ft.dropdown.Option("Zelle"),
            ],
            value="Pago Móvil",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.pay_note_field = ft.TextField(
            label="Referencia / Nota",
            hint_text="Ej: Ref 482910 banco Mercantil",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )

        # Table body with full bounded vertical scroll
        self.table_body = ft.Column(
            controls=self._build_rows(),
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # -------------------------------------------------------------------
        # Build Dialogs
        # -------------------------------------------------------------------
        # 1. Dialog for adding new member
        self.new_member_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Nuevo Socio", size=FONT_SIZE_LG),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.new_member_error_banner,
                        ft.Row(
                            controls=[self.cedula_prefix, self.cedula_number],
                            spacing=8,
                        ),
                        self.nombre_field,
                        self.telefono_field,
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
                        ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=4, bottom=4)),
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.PAYMENTS_OUTLINED, size=18, color=ACCENT_SUCCESS),
                                heading_text("Pago Inicial de Inscripción", size=FONT_SIZE_SM),
                            ],
                            spacing=6,
                        ),
                        ft.Row(
                            controls=[
                                self.new_pay_amount_usd,
                                ft.Container(
                                    content=ft.Column(
                                        controls=[
                                            self.new_pay_bcv_rate_label,
                                            self.new_pay_amount_bs,
                                        ],
                                        spacing=2,
                                    ),
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                    bgcolor=BG_INPUT,
                                    border_radius=RADIUS_SM,
                                    alignment=ft.Alignment(-1, 0),
                                    expand=1,
                                ),
                            ],
                            spacing=10,
                        ),
                        ft.Row(
                            controls=[
                                self.new_pay_method,
                                self.new_pay_ref,
                            ],
                            spacing=10,
                        ),
                    ],
                    spacing=10,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=PADDING_MD,
                width=480,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.new_member_dialog)),
                ft.ElevatedButton(
                    "Registrar Socio y Cobro",
                    bgcolor=ACCENT_PRIMARY,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_new_member,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # 2. Dialog for EDITING existing member
        self.edit_member_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Editar Socio", size=FONT_SIZE_LG),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.edit_cedula_field,
                        self.edit_nombre_field,
                        self.edit_telefono_field,
                        ft.Row(
                            controls=[self.edit_plan_field, self.edit_estado_field],
                            spacing=10,
                        ),
                        self.edit_venc_field,
                        ft.Row(
                            controls=[
                                self.edit_nfc_field,
                                ft.IconButton(
                                    icon=ft.Icons.CONTACTLESS,
                                    icon_color=ACCENT_PRIMARY,
                                    tooltip="Escanear nuevo llavero en ACR122U",
                                    on_click=self._start_scan_for_edit_member,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        self.edit_nfc_status,
                    ],
                    spacing=12,
                    tight=True,
                ),
                padding=PADDING_MD,
                width=460,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.edit_member_dialog)),
                ft.ElevatedButton(
                    "Guardar Cambios",
                    bgcolor=ACCENT_PRIMARY,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_edited_member,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # 3. Dialog for PAYMENT & RENEWAL (BCV rate calculation)
        self.payment_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PAYMENTS, color=ACCENT_SUCCESS, size=24),
                    heading_text("Cobro y Renovación de Membresía", size=FONT_SIZE_MD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=self.pay_member_info,
                            bgcolor=BG_INPUT,
                            padding=10,
                            border_radius=RADIUS_SM,
                        ),
                        ft.Row(
                            controls=[self.pay_plan_field, self.pay_days_field],
                            spacing=10,
                        ),
                        ft.Row(
                            controls=[
                                self.pay_amount_usd,
                                ft.Container(
                                    content=ft.Column(
                                        controls=[
                                            self.pay_bcv_rate_label,
                                            self.pay_amount_bs,
                                        ],
                                        spacing=2,
                                    ),
                                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                    bgcolor=BG_INPUT,
                                    border_radius=RADIUS_SM,
                                    expand=1,
                                ),
                            ],
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        self.pay_method_field,
                        self.pay_note_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                padding=PADDING_MD,
                width=480,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.payment_dialog)),
                ft.ElevatedButton(
                    "Procesar Pago",
                    bgcolor=ACCENT_SUCCESS,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._process_payment_submit,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # 4. Multi-NFC Keys Management Dialog (Phone, Smartwatch, Fobs, Cards)
        self._target_member_for_nfc = None
        self._editing_nfc_key_id = None

        self.nfc_keys_member_info = ft.Text("", size=14, weight="w600", color=TEXT_PRIMARY)
        self.nfc_keys_list_container = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)

        self.nfc_key_alias_field = ft.TextField(
            label="Alias del Dispositivo",
            hint_text="Ej: Teléfono Móvil, Smartwatch, Tarjeta",
            value="Teléfono / Llavero Extra",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=13,
            expand=1,
        )
        self.nfc_key_uid_field = ft.TextField(
            label="UID NFC (Hex)",
            hint_text="Ej: 04A1B2C3D4",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=13,
            expand=1,
        )
        self.nfc_key_status_label = ft.Text(
            "Puede escribir el UID o tocar 'Leer ACR122U' para escanear",
            size=11,
            color=TEXT_MUTED,
        )
        self.nfc_key_submit_btn = ft.ElevatedButton(
            "Vincular Llave",
            bgcolor=ACCENT_PRIMARY,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
            on_click=self._submit_add_or_update_nfc_key,
        )
        self.nfc_key_cancel_edit_btn = ft.TextButton(
            "Cancelar Edición",
            visible=False,
            on_click=self._cancel_nfc_key_edit,
        )

        self.multi_nfc_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CONTACTLESS_ROUNDED, color=ACCENT_PRIMARY, size=24),
                    heading_text("Gestión de Llaves NFC (Múltiples Dispositivos)", size=FONT_SIZE_MD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.nfc_keys_member_info,
                        ft.Container(height=1, bgcolor=BORDER),
                        ft.Text("Llaves y dispositivos registrados para este socio:", size=12, color=TEXT_MUTED, weight="w600"),
                        ft.Container(
                            content=self.nfc_keys_list_container,
                            bgcolor=BG_INPUT,
                            border=ft.Border.all(1, BORDER),
                            border_radius=RADIUS_SM,
                            padding=8,
                            height=170,
                        ),
                        ft.Container(height=6),
                        ft.Text("Vincular nuevo dispositivo o sobre-escribir existente:", size=12, color=TEXT_PRIMARY, weight="w600"),
                        ft.Row(
                            controls=[
                                self.nfc_key_alias_field,
                                self.nfc_key_uid_field,
                            ],
                            spacing=8,
                        ),
                        ft.Row(
                            controls=[
                                ft.ElevatedButton(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.SENSORS, size=16),
                                        ft.Text("Leer ACR122U", size=12),
                                    ], spacing=6),
                                    bgcolor=BG_CARD,
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                        side=ft.BorderSide(1, BORDER),
                                    ),
                                    on_click=self._start_scan_for_multi_key,
                                ),
                                ft.Container(expand=True),
                                self.nfc_key_cancel_edit_btn,
                                self.nfc_key_submit_btn,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        self.nfc_key_status_label,
                    ],
                    spacing=6,
                    tight=True,
                ),
                padding=PADDING_MD,
                width=520,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: self._close_modal(self.multi_nfc_dialog)),
            ],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # Legacy dialog kept for compatibility
        self.link_fob_label = ft.Text("Acerque el llavero o tarjeta al lector ACS ACR122U...", size=13, color=TEXT_SECONDARY)
        self.link_fob_dialog = self.multi_nfc_dialog

        # 5. Delete / Deactivate confirmation dialog (Soft Delete)
        self.delete_confirm_text = ft.Text("", size=13, color=TEXT_PRIMARY)
        self.delete_confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PERSON_OFF_OUTLINED, color=ACCENT_DANGER, size=24),
                    heading_text("Desactivar Socio (Soft Delete)", size=FONT_SIZE_MD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=self.delete_confirm_text,
                padding=PADDING_MD,
                width=450,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.delete_confirm_dialog)),
                ft.ElevatedButton(
                    "Desactivar Socio",
                    bgcolor=ACCENT_DANGER,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._confirm_delete_member,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # 6. Customer 360 / Expediente del Socio Dialog
        self.member_detail_content = ft.Column(spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
        self.member_detail_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.BADGE_OUTLINED, color=ACCENT_PRIMARY, size=24),
                    heading_text("Expediente 360 del Socio", size=FONT_SIZE_LG),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=self.member_detail_content,
                padding=PADDING_MD,
                width=680,
                height=560,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: self._close_modal(self.member_detail_dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # Assemble Main View
        self.controls = [
            heading_text("Gestión de Socios"),
            ft.Container(height=4),
            ft.Row(
                controls=[
                    self.search_field,
                    self.status_filter,
                    ft.Container(expand=True),
                    button_primary(
                        "Nuevo Socio",
                        icon=ft.Icons.PERSON_ADD,
                        on_click=self._open_new_member_dialog,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(height=8),
            ft.Container(
                content=ft.Column(
                    controls=[
                        self._build_header(),
                        ft.Container(height=1, bgcolor=BORDER),
                        ft.Container(content=self.table_body, expand=True),
                    ],
                    spacing=0,
                    expand=True,
                ),
                **card_style(),
                expand=True,
            ),
        ]

    def _get_plan_options(self):
        try:
            plans = load_plans(active_only=True)
            if plans:
                return [ft.dropdown.Option(p["nombre"]) for p in plans]
        except Exception:
            pass
        return [ft.dropdown.Option(k) for k in PLANS.keys()]

    def _reload_plan_dropdowns(self):
        opts = self._get_plan_options()
        self.plan_field.options = list(opts)
        self.edit_plan_field.options = list(opts)
        self.pay_plan_field.options = list(opts)
        if hasattr(self, "page") and self.page:
            try:
                self.plan_field.update()
                self.edit_plan_field.update()
                self.pay_plan_field.update()
            except Exception:
                pass

    def _on_plans_event(self, data=None):
        self._reload_plan_dropdowns()

    def did_mount(self):
        """Subscribe to live EventBus updates."""
        event_bus.subscribe("access_scan", self._on_event_refresh)
        event_bus.subscribe("members_changed", self._on_event_refresh)
        event_bus.subscribe("plans_changed", self._on_plans_event)

    def will_unmount(self):
        """Unsubscribe from live EventBus updates."""
        event_bus.unsubscribe("access_scan", self._on_event_refresh)
        event_bus.unsubscribe("members_changed", self._on_event_refresh)
        event_bus.unsubscribe("plans_changed", self._on_plans_event)

    def _on_event_refresh(self, data=None):
        self.table_body.controls = self._build_rows()
        if hasattr(self, "page") and self.page:
            try:
                self.table_body.update()
            except Exception:
                pass

    def _open_modal(self, dialog):
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "show_dialog"):
                try:
                    self.page.show_dialog(dialog)
                    return
                except Exception:
                    pass
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()

    def _close_modal(self, dialog):
        nfc_reader.set_access_mode()
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "pop_dialog"):
                try:
                    self.page.pop_dialog()
                    return
                except Exception:
                    pass
            dialog.open = False
            self.page.update()

    def _get_filtered_members(self):
        query = (self.search_field.value or "").strip().upper()
        status_sel = (self.status_filter.value or "ACTIVOS Y MOROSOS").upper()

        results = []
        for m in MEMBERS:
            m_status = (m.get("estado") or "Activo").strip()
            if status_sel == "ACTIVOS Y MOROSOS":
                if m_status == "Inactivo":
                    continue
            elif "SOLO ACTIVOS" in status_sel or status_sel == "ACTIVOS":
                if m_status != "Activo":
                    continue
            elif "SOLO MOROSOS" in status_sel or status_sel == "MOROSOS":
                if m_status != "Moroso":
                    continue
            elif "GYM" in status_sel:
                if not m.get("entrenando"):
                    continue
            elif "DESACTIVADOS" in status_sel or "INACTIVOS" in status_sel:
                if m_status != "Inactivo":
                    continue
            elif "TODOS" in status_sel:
                pass

            if query:
                haystack = f"{m.get('cedula', '')} {m.get('nombre', '')}".upper()
                if query not in haystack:
                    continue

            results.append(m)
        return results

    def _on_search_or_filter_change(self, e):
        self.table_body.controls = self._build_rows()
        if hasattr(self, "page") and self.page:
            try:
                self.table_body.update()
            except Exception:
                pass

    def _build_header(self):
        """Fixed width column headers guarantees Cédula and Nombre are always visible."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text("Cédula", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=110),
                    ft.Text("Nombre y Contacto", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", expand=1),
                    ft.Text("Plan", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=85),
                    ft.Text("Vencimiento", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=100),
                    ft.Text("Estado", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=90),
                    ft.Text("En Gym", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=70),
                    ft.Text("Llavero NFC", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=120),
                    ft.Text("Acciones", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=220),
                ],
            ),
            padding=PADDING_MD,
        )

    def _build_rows(self):
        filtered = self._get_filtered_members()
        rows = []
        for m in filtered:
            status_color = ACCENT_SUCCESS if m["estado"] == "Activo" else (
                ACCENT_DANGER if m["estado"] == "Moroso" else TEXT_MUTED
            )

            in_gym = bool(m.get("entrenando", False))

            from core.mock_data import get_member_nfc_keys
            member_keys = get_member_nfc_keys(m.get("cedula", ""))
            if len(member_keys) > 1:
                nfc_label = f"📱 {len(member_keys)} llaves"
                nfc_color = ft.Colors.CYAN_ACCENT
            elif len(member_keys) == 1:
                nfc_label = member_keys[0].get("nfc_id", "")
                nfc_color = TEXT_PRIMARY
            else:
                nfc_label = m.get("nfc_id") or "Sin asignar"
                nfc_color = TEXT_PRIMARY if nfc_label != "Sin asignar" else TEXT_MUTED

            phone_str = (m.get("telefono") or "").strip()
            name_column_controls = [
                ft.Text(m["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600"),
            ]
            if phone_str:
                name_column_controls.append(
                    ft.Text(f"📞 {phone_str}", size=11, color=TEXT_MUTED)
                )

            from core.whatsapp_service import get_whatsapp_url
            wa_url = get_whatsapp_url(m)

            action_buttons = [
                ft.IconButton(
                    icon=ft.Icons.PAYMENTS_OUTLINED,
                    icon_size=18,
                    icon_color=ACCENT_SUCCESS,
                    tooltip="Pagar / Renovar membresía (BCV)",
                    on_click=lambda e, mem=m: self._open_payment_dialog(mem),
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED,
                    icon_size=18,
                    icon_color=ACCENT_PRIMARY,
                    tooltip="Editar socio",
                    on_click=lambda e, mem=m: self._open_edit_dialog(mem),
                ),
                ft.IconButton(
                    icon=ft.Icons.CONTACTLESS_ROUNDED,
                    icon_size=18,
                    icon_color=ft.Colors.CYAN_ACCENT,
                    tooltip="Gestionar llaves NFC (Teléfono, llaveros, tarjetas)",
                    on_click=lambda e, mem=m: self._open_nfc_keys_dialog(mem),
                ),
            ]
            if wa_url:
                action_buttons.append(
                    ft.IconButton(
                        icon=ft.Icons.CHAT,
                        icon_size=18,
                        icon_color="#25D366",
                        tooltip=f"Enviar recordatorio por WhatsApp ({phone_str})",
                        url=wa_url,
                        on_click=lambda e, mem=m: self._launch_whatsapp(mem),
                    )
                )
            if m.get("estado") == "Inactivo":
                action_buttons.append(
                    ft.IconButton(
                        icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                        icon_size=18,
                        icon_color=ACCENT_SUCCESS,
                        tooltip="Reactivar socio",
                        on_click=lambda e, mem=m: self._reactivate_member_handler(mem),
                    )
                )
            else:
                action_buttons.append(
                    ft.IconButton(
                        icon=ft.Icons.PERSON_OFF_OUTLINED,
                        icon_size=18,
                        icon_color=ACCENT_DANGER,
                        tooltip="Desactivar socio (Soft Delete)",
                        on_click=lambda e, mem=m: self._open_delete_dialog(mem),
                    )
                )

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(m["cedula"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=110),
                            ft.Column(controls=name_column_controls, spacing=1, expand=1),
                            ft.Text(m["plan"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=85),
                            ft.Text(m["vencimiento"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=100),
                            ft.Container(
                                content=ft.Text(m["estado"], size=FONT_SIZE_XS, color=TEXT_PRIMARY, weight="w600"),
                                bgcolor=status_color,
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                border_radius=RADIUS_SM,
                                width=85,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Container(
                                content=ft.Text("SÍ" if in_gym else "NO", size=10, color=TEXT_PRIMARY, weight="w700"),
                                bgcolor=ft.Colors.CYAN_900 if in_gym else BG_INPUT,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                border_radius=4,
                                width=60,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Text(
                                nfc_label,
                                size=FONT_SIZE_XS,
                                color=nfc_color,
                                width=120,
                            ),
                            # Action buttons
                            ft.Row(
                                controls=action_buttons,
                                spacing=0,
                                width=220,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=6),
                    border=ft.Border(bottom=ft.BorderSide(1, BORDER)),
                    ink=True,
                    on_click=lambda e, mem=m: self._open_member_detail_modal(mem),
                    tooltip=f"Ver expediente 360 y métricas de {m['nombre']}",
                )
            )

        if not rows:
            rows.append(
                ft.Container(
                    content=ft.Text("No se encontraron socios con los criterios de búsqueda.", color=TEXT_MUTED, size=13),
                    padding=PADDING_MD,
                )
            )
        return rows

    def _launch_whatsapp(self, member: dict):
        from core.whatsapp_service import get_whatsapp_url
        url = get_whatsapp_url(member)
        if url and self.page:
            try:
                if hasattr(self.page, "launch_url"):
                    self.page.launch_url(url, web_popup_window_name="_blank")
            except Exception as ex:
                print(f"[MembersView] Error launching WhatsApp: {ex}")

    def _open_member_detail_modal(self, member: dict):
        from core.business import get_member_full_profile
        from core.whatsapp_service import get_whatsapp_url

        ced = member.get("cedula", "")
        profile = get_member_full_profile(ced)
        if "error" in profile:
            self._show_notification("No se pudo cargar el expediente del socio.", ACCENT_DANGER)
            return

        m_data = profile["member"]
        stats = profile["stats"]
        payments = profile["payments"]
        access_logs = profile["access_logs"]

        dias_left = stats["dias_restantes"]
        if dias_left > 12:
            exp_color = ACCENT_SUCCESS
            exp_text = f"Quedan {dias_left} días de vigencia"
        elif 3 <= dias_left <= 12:
            exp_color = ACCENT_WARNING
            exp_text = f"Próximo a vencer ({dias_left} días)"
        elif 0 <= dias_left < 3:
            exp_color = ACCENT_DANGER
            exp_text = f"Vence hoy / {dias_left} días"
        else:
            exp_color = ACCENT_DANGER
            exp_text = f"Venció hace {abs(dias_left)} días (Moroso)"

        # Header with initials
        initials = "".join([part[0] for part in m_data.get("nombre", "S").split()][:2]).upper()
        avatar = ft.Container(
            content=ft.Text(initials, size=18, weight="w700", color=TEXT_PRIMARY),
            bgcolor=ACCENT_PRIMARY,
            width=48,
            height=48,
            border_radius=24,
            alignment=ft.Alignment(0, 0),
        )

        phone_val = m_data.get("telefono", "")
        wa_url = get_whatsapp_url(m_data) if phone_val else None

        header_card = ft.Container(
            content=ft.Row(
                controls=[
                    avatar,
                    ft.Column(
                        controls=[
                            ft.Text(m_data.get("nombre", ""), size=17, weight="w700", color=TEXT_PRIMARY),
                            ft.Row(
                                controls=[
                                    ft.Text(f"Cédula: {m_data.get('cedula', '')}", size=12, color=TEXT_SECONDARY),
                                    ft.Text("·", size=12, color=TEXT_MUTED),
                                    ft.Text(f"Plan: {m_data.get('plan', '-')}", size=12, color=ACCENT_PRIMARY, weight="w600"),
                                    ft.Text("·", size=12, color=TEXT_MUTED),
                                    ft.Text(f"📞 {phone_val}" if phone_val else "Sin teléfono", size=12, color=TEXT_MUTED),
                                ],
                                spacing=6,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Container(
                                        content=ft.Text(m_data.get("estado", "Activo"), size=11, color=TEXT_PRIMARY, weight="w600"),
                                        bgcolor=ACCENT_SUCCESS if m_data.get("estado") == "Activo" else (
                                            ACCENT_DANGER if m_data.get("estado") == "Moroso" else ft.Colors.GREY_700
                                        ),
                                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=RADIUS_SM,
                                    ),
                                    ft.Container(
                                        content=ft.Text("🏃 Entrenando Ahora" if stats["in_gym"] else "Fuera del Gym", size=11, color=TEXT_PRIMARY, weight="w600"),
                                        bgcolor=ft.Colors.CYAN_800 if stats["in_gym"] else BG_INPUT,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=RADIUS_SM,
                                    ),
                                    ft.Container(
                                        content=ft.Text(f"Vence: {m_data.get('vencimiento', '')} ({exp_text})", size=11, color=exp_color, weight="w600"),
                                        bgcolor=ft.Colors.with_opacity(0.12, exp_color),
                                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                        border_radius=RADIUS_SM,
                                    ),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                ],
                spacing=14,
            ),
            bgcolor=BG_INPUT,
            padding=14,
            border_radius=RADIUS_MD,
        )

        # Quick action buttons row
        actions_row = ft.Row(
            controls=[
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.PAYMENTS, size=16), ft.Text("Cobrar / Renovar", size=12)], spacing=6),
                    bgcolor=ACCENT_SUCCESS,
                    color=TEXT_PRIMARY,
                    on_click=lambda e: (self._close_modal(self.member_detail_dialog), self._open_payment_dialog(m_data)),
                ),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.EDIT, size=16), ft.Text("Editar Datos", size=12)], spacing=6),
                    bgcolor=BG_CARD,
                    color=TEXT_PRIMARY,
                    on_click=lambda e: (self._close_modal(self.member_detail_dialog), self._open_edit_dialog(m_data)),
                ),
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.CONTACTLESS, size=16), ft.Text("Llaves NFC", size=12)], spacing=6),
                    bgcolor=BG_CARD,
                    color=TEXT_PRIMARY,
                    on_click=lambda e: (self._close_modal(self.member_detail_dialog), self._open_nfc_keys_dialog(m_data)),
                ),
            ],
            spacing=8,
        )
        if wa_url:
            actions_row.controls.append(
                ft.ElevatedButton(
                    content=ft.Row([ft.Icon(ft.Icons.CHAT, size=16), ft.Text("Enviar WhatsApp", size=12)], spacing=6),
                    bgcolor="#25D366",
                    color=TEXT_PRIMARY,
                    url=wa_url,
                    on_click=lambda e: self._launch_whatsapp(m_data),
                )
            )

        # Attendance Metrics Cards
        metrics_row = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Visitas Únicas", size=11, color=TEXT_MUTED),
                            ft.Text(f"{stats['total_visits']} días", size=16, weight="w700", color=ACCENT_PRIMARY),
                        ],
                        spacing=2,
                    ),
                    bgcolor=BG_INPUT,
                    padding=10,
                    border_radius=RADIUS_SM,
                    expand=1,
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Toques / Entradas", size=11, color=TEXT_MUTED),
                            ft.Text(f"{stats['total_entries']} toques", size=16, weight="w700", color=TEXT_PRIMARY),
                        ],
                        spacing=2,
                    ),
                    bgcolor=BG_INPUT,
                    padding=10,
                    border_radius=RADIUS_SM,
                    expand=1,
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Horario Habitual", size=11, color=TEXT_MUTED),
                            ft.Text(f"{stats['usual_hour']}", size=13, weight="w700", color=ACCENT_WARNING),
                        ],
                        spacing=2,
                    ),
                    bgcolor=BG_INPUT,
                    padding=10,
                    border_radius=RADIUS_SM,
                    expand=1,
                ),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text("Días Más Asiduos", size=11, color=TEXT_MUTED),
                            ft.Text(f"{stats['usual_days']}", size=13, weight="w700", color=ACCENT_SUCCESS),
                        ],
                        spacing=2,
                    ),
                    bgcolor=BG_INPUT,
                    padding=10,
                    border_radius=RADIUS_SM,
                    expand=1,
                ),
            ],
            spacing=8,
        )

        # Access Logs Table
        access_rows = []
        for log in access_logs[:15]:
            is_granted = log.get("status") in ("ENTRADA", "CONCEDIDO", "PERMITIDO")
            access_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CHECK_CIRCLE if is_granted else ft.Icons.CANCEL, size=15, color=ACCENT_SUCCESS if is_granted else ACCENT_DANGER),
                            ft.Text(log.get("fecha", ""), size=12, color=TEXT_PRIMARY, width=100),
                            ft.Text(log.get("hora", ""), size=12, color=TEXT_SECONDARY, width=70),
                            ft.Text(f"Plan: {log.get('plan', '-')}", size=12, color=TEXT_MUTED, expand=1),
                            ft.Container(
                                content=ft.Text(log.get("status", ""), size=10, color=TEXT_PRIMARY, weight="w600"),
                                bgcolor=ACCENT_SUCCESS if is_granted else ACCENT_DANGER,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                border_radius=4,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(vertical=3),
                )
            )

        access_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.HISTORY, size=18, color=ACCENT_PRIMARY),
                            heading_text("Historial Reciente de Asistencias", size=FONT_SIZE_SM),
                        ],
                        spacing=6,
                    ),
                    ft.Column(controls=access_rows if access_rows else [ft.Text("Sin asistencias registradas", size=12, color=TEXT_MUTED)], spacing=2),
                ],
                spacing=8,
            ),
            bgcolor=BG_INPUT,
            padding=12,
            border_radius=RADIUS_MD,
        )

        # Payments History Table
        payment_rows = []
        for p in payments[:15]:
            payment_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.RECEIPT_LONG, size=15, color=ACCENT_SUCCESS),
                            ft.Text(str(p.get("fecha_pago", ""))[:16], size=12, color=TEXT_PRIMARY, width=130),
                            ft.Text(f"{p.get('plan', '')} ({p.get('dias', 0)}d)", size=12, color=TEXT_SECONDARY, width=130),
                            ft.Text(f"${p.get('monto', 0.0):.2f}", size=12, color=ACCENT_PRIMARY, weight="w700", width=70),
                            ft.Text(f"Bs. {p.get('monto_bs', 0.0):,.2f}", size=11, color=TEXT_MUTED, width=110),
                            ft.Text(p.get("metodo", ""), size=11, color=TEXT_SECONDARY, expand=1),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(vertical=3),
                )
            )

        payments_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, size=18, color=ACCENT_SUCCESS),
                            heading_text("Historial de Pagos y Facturación", size=FONT_SIZE_SM),
                            ft.Container(expand=True),
                            ft.Text(f"Total: ${stats['total_paid_usd']:.2f} (Bs. {stats['total_paid_bs']:,.2f})", size=12, color=ACCENT_SUCCESS, weight="w700"),
                        ],
                        spacing=6,
                    ),
                    ft.Column(controls=payment_rows if payment_rows else [ft.Text("Sin pagos registrados", size=12, color=TEXT_MUTED)], spacing=2),
                ],
                spacing=8,
            ),
            bgcolor=BG_INPUT,
            padding=12,
            border_radius=RADIUS_MD,
        )

        self.member_detail_content.controls = [
            header_card,
            actions_row,
            metrics_row,
            access_section,
            payments_section,
        ]

        self._open_modal(self.member_detail_dialog)

    # -----------------------------------------------------------------------
    # NEW Member Handlers (With Venezuelan Cédula Validation & Initial Payment)
    # -----------------------------------------------------------------------
    def _open_new_member_dialog(self, e=None):
        self.new_member_error_banner.visible = False
        self.new_member_error_text.value = ""
        self.cedula_number.value = ""
        self.cedula_number.error_text = None
        self.nombre_field.value = ""
        self.nombre_field.error_text = None
        self.telefono_field.value = ""
        self.telefono_field.error_text = None
        self.nfc_field.value = ""
        self.nfc_field.error_text = None
        self.nfc_scan_status.value = "Opcional: Si el socio no tiene llavero, déjalo vacío o presiona el botón para escanear en ACR122U."
        self.nfc_scan_status.color = TEXT_MUTED
        self.new_pay_ref.value = ""
        self.new_pay_ref.error_text = None
        self.new_pay_amount_usd.error_text = None
        self._reload_plan_dropdowns()
        self._update_new_member_amounts()
        self._open_modal(self.new_member_dialog)

    def _update_new_member_amounts(self):
        plan_name = self.plan_field.value or "Basico"
        plan_info = PLANS.get(plan_name, {})
        price = float(plan_info.get("precio", 25.0))
        self.new_pay_amount_usd.value = f"{price:.2f}"
        rate = bcv_service.get_rate()
        bs_amount = bcv_service.to_bs(price)
        self.new_pay_bcv_rate_label.value = f"Tasa BCV: {rate:.2f}"
        self.new_pay_amount_bs.value = bcv_service.format_bs(bs_amount)
        if hasattr(self, "page") and self.page:
            try:
                self.new_pay_amount_usd.update()
                self.new_pay_bcv_rate_label.update()
                self.new_pay_amount_bs.update()
            except Exception:
                pass

    def _on_new_member_plan_change(self, e):
        self._update_new_member_amounts()

    def _on_new_member_amount_change(self, e):
        raw = (self.new_pay_amount_usd.value or "").strip()
        try:
            usd_val = float(raw or 0.0)
            bs_val = bcv_service.to_bs(usd_val)
            self.new_pay_amount_bs.value = bcv_service.format_bs(bs_val)
            if hasattr(self, "page") and self.page:
                try:
                    self.new_pay_amount_bs.update()
                except Exception:
                    pass
        except Exception:
            pass

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
        if hasattr(self, "page") and self.page:
            try:
                self.nfc_field.update()
                self.nfc_scan_status.update()
            except Exception:
                pass

    def _save_new_member(self, e):
        self.new_member_error_banner.visible = False
        self.new_member_error_text.value = ""
        self.cedula_number.error_text = None
        self.nombre_field.error_text = None
        self.telefono_field.error_text = None
        self.nfc_field.error_text = None
        self.new_pay_amount_usd.error_text = None
        self.new_pay_ref.error_text = None

        prefix = (self.cedula_prefix.value or "V").strip().upper()
        raw_number = (self.cedula_number.value or "").strip()
        nombre = (self.nombre_field.value or "").strip()
        telefono = (self.telefono_field.value or "").strip()
        plan = (self.plan_field.value or "Basico").strip()
        nfc_id = (self.nfc_field.value or "").strip()

        has_error = False
        digits = "".join(ch for ch in raw_number if ch.isdigit())
        if len(digits) < 6 or len(digits) > 10:
            self.cedula_number.error_text = "Debe ingresar entre 6 y 10 dígitos numéricos"
            has_error = True

        if len(nombre) < 3 or not re.search(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]", nombre):
            self.nombre_field.error_text = "El nombre debe tener al menos 3 letras"
            has_error = True

        # Pre-validate duplicate NFC key if provided (NFC is optional)
        from core.mock_data import find_member_by_nfc_id, normalize_nfc_id, normalize_cedula
        clean_nfc = normalize_nfc_id(nfc_id)
        if clean_nfc:
            existing_owner = find_member_by_nfc_id(clean_nfc)
            if existing_owner:
                self.nfc_field.error_text = f"Esta llave NFC ya pertenece a {existing_owner['nombre']} (Cédula: {existing_owner['cedula']})"
                has_error = True

        # Validate initial payment
        raw_amt = (self.new_pay_amount_usd.value or "").strip()
        pay_amt = 0.0
        try:
            pay_amt = float(raw_amt or 0.0)
            if pay_amt <= 0:
                self.new_pay_amount_usd.error_text = "El monto a pagar debe ser mayor a 0"
                has_error = True
        except ValueError:
            self.new_pay_amount_usd.error_text = "Monto numérico inválido"
            has_error = True

        pay_method = (self.new_pay_method.value or "Efectivo USD").strip()
        pay_ref = (self.new_pay_ref.value or "").strip()
        if not pay_ref and pay_method in ("Pago Móvil", "Transferencia Bancaria", "Punto de Venta", "Zelle"):
            self.new_pay_ref.error_text = "Ingrese la referencia bancaria o comprobante"
            has_error = True

        if has_error:
            self.new_member_error_text.value = "Por favor verifique los campos marcados en rojo."
            self.new_member_error_banner.visible = True
            try:
                self.new_member_error_banner.update()
                self.cedula_number.update()
                self.nombre_field.update()
                self.telefono_field.update()
                self.nfc_field.update()
                self.new_pay_amount_usd.update()
                self.new_pay_ref.update()
            except Exception:
                pass
            self._show_notification("Revise los campos requeridos marcados en rojo.", ACCENT_DANGER)
            return

        cedula = f"{prefix}-{digits}"
        try:
            register_member(cedula=cedula, nombre=nombre, plan=plan, nfc_id=clean_nfc, telefono=telefono)
        except (ValueError, Exception) as exc:
            err_msg = str(exc)
            self.new_member_error_text.value = f"⚠️ {err_msg}"
            self.new_member_error_banner.visible = True
            try:
                self.new_member_error_banner.update()
                if "NFC" in err_msg:
                    self.nfc_field.error_text = err_msg
                    self.nfc_field.update()
                else:
                    self.cedula_number.error_text = err_msg
                    self.cedula_number.update()
            except Exception:
                pass
            self._show_notification(f"Error: {err_msg}", ACCENT_DANGER)
            return

        # Record initial payment in accounting records
        plan_info = PLANS.get(plan, {})
        plan_days = int(plan_info.get("dias", 30))
        try:
            process_membership_payment(
                cedula=cedula,
                plan=plan,
                amount=pay_amt,
                days=plan_days,
                method=pay_method,
                note=pay_ref or "Pago inicial de inscripción",
                is_initial=True,
            )
        except Exception as p_exc:
            print(f"[MembersView] Error registrando pago inicial: {p_exc}")

        self.table_body.controls = self._build_rows()
        self.table_body.update()

        self._close_modal(self.new_member_dialog)
        self._show_notification(
            f"Socio {nombre} ({cedula}) registrado y pago inicial de ${pay_amt:.2f} ({pay_method}) procesado con éxito.",
            ACCENT_SUCCESS,
        )

    # -----------------------------------------------------------------------
    # EDIT Member Handlers
    # -----------------------------------------------------------------------
    def _open_edit_dialog(self, member: dict):
        self.edit_cedula_field.value = member.get("cedula", "")
        self.edit_nombre_field.value = member.get("nombre", "")
        self.edit_nombre_field.error_text = None
        self.edit_telefono_field.value = member.get("telefono", "") or ""
        self.edit_telefono_field.error_text = None
        self.edit_plan_field.value = member.get("plan", "Basico")
        self.edit_venc_field.value = member.get("vencimiento", "")
        self.edit_venc_field.error_text = None
        self.edit_estado_field.value = member.get("estado", "Activo")
        self.edit_nfc_field.value = member.get("nfc_id", "")
        self.edit_nfc_field.error_text = None
        self.edit_nfc_status.value = ""
        self._open_modal(self.edit_member_dialog)

    def _start_scan_for_edit_member(self, e):
        self.edit_nfc_status.value = "📡 ACERQUE EL NUEVO LLAVERO AL LECTOR ACR122U..."
        self.edit_nfc_status.color = ACCENT_PRIMARY
        try:
            self.edit_nfc_status.update()
        except Exception:
            pass
        nfc_reader.set_enroll_mode(self._on_enrolled_edit_member_tag)

    def _on_enrolled_edit_member_tag(self, uid: str):
        self.edit_nfc_field.value = uid
        self.edit_nfc_status.value = f"✅ Llavero detectado: {uid}"
        self.edit_nfc_status.color = ACCENT_SUCCESS
        if hasattr(self, "page") and self.page:
            try:
                self.edit_nfc_field.update()
                self.edit_nfc_status.update()
            except Exception:
                pass

    def _save_edited_member(self, e):
        self.edit_nombre_field.error_text = None
        self.edit_telefono_field.error_text = None
        self.edit_venc_field.error_text = None
        self.edit_nfc_field.error_text = None

        cedula = (self.edit_cedula_field.value or "").strip()
        nombre = (self.edit_nombre_field.value or "").strip()
        telefono = (self.edit_telefono_field.value or "").strip()
        plan = (self.edit_plan_field.value or "Basico").strip()
        venc = (self.edit_venc_field.value or "").strip()
        estado = (self.edit_estado_field.value or "Activo").strip()
        nfc_id = (self.edit_nfc_field.value or "").strip()

        has_error = False
        if len(nombre) < 3:
            self.edit_nombre_field.error_text = "El nombre debe tener al menos 3 letras"
            has_error = True

        from datetime import datetime
        try:
            datetime.strptime(venc, "%Y-%m-%d")
        except Exception:
            self.edit_venc_field.error_text = "Fecha inválida (Use formato YYYY-MM-DD)"
            has_error = True

        # Check duplicate NFC key before updating
        from core.mock_data import find_member_by_nfc_id, normalize_nfc_id, normalize_cedula
        clean_nfc = normalize_nfc_id(nfc_id)
        if clean_nfc:
            existing_owner = find_member_by_nfc_id(clean_nfc)
            if existing_owner and normalize_cedula(existing_owner.get("cedula")) != normalize_cedula(cedula):
                self.edit_nfc_field.error_text = f"Esta llave NFC ya pertenece a {existing_owner['nombre']} (Cédula: {existing_owner['cedula']})"
                has_error = True

        if has_error:
            self.edit_nombre_field.update()
            self.edit_venc_field.update()
            self.edit_nfc_field.update()
            return

        try:
            update_member(
                cedula=cedula,
                updates={
                    "nombre": nombre,
                    "plan": plan,
                    "telefono": telefono,
                    "vencimiento": venc,
                    "estado": estado,
                    "nfc_id": clean_nfc,
                },
            )
        except Exception as exc:
            err_msg = str(exc)
            if "NFC" in err_msg:
                self.edit_nfc_field.error_text = err_msg
                self.edit_nfc_field.update()
            else:
                self.edit_nombre_field.error_text = f"Error al actualizar: {exc}"
                self.edit_nombre_field.update()
            return

        self.table_body.controls = self._build_rows()
        self.table_body.update()
        self._close_modal(self.edit_member_dialog)
        self._show_notification(f"Socio {nombre} actualizado correctamente.", ACCENT_SUCCESS)

    # -----------------------------------------------------------------------
    # PAYMENT & RENEWAL (BCV Rate Calculation)
    # -----------------------------------------------------------------------
    def _open_payment_dialog(self, member: dict):
        self._target_member_for_payment = member
        self.pay_amount_usd.error_text = None
        self.pay_days_field.error_text = None
        plan_name = member.get("plan", "Basico")
        self.pay_member_info.value = f"Socio: {member.get('nombre')} • Cédula: {member.get('cedula')}"
        self._reload_plan_dropdowns()

        opts_keys = [o.key for o in self.pay_plan_field.options]
        if plan_name in opts_keys:
            self.pay_plan_field.value = plan_name
        elif opts_keys:
            self.pay_plan_field.value = opts_keys[0]
        else:
            self.pay_plan_field.value = "Basico"

        self._update_pay_plan_details(self.pay_plan_field.value)
        self._open_modal(self.payment_dialog)

    def _on_pay_plan_change(self, e):
        self._update_pay_plan_details(self.pay_plan_field.value)

    def _update_pay_plan_details(self, plan_name: str):
        price = 25.0
        days = 30
        try:
            plans = load_plans(active_only=True)
            matched = next((p for p in plans if p["nombre"] == plan_name), None)
            if matched:
                price = float(matched.get("precio", 25.0))
                days = int(matched.get("dias", 30))
            elif plan_name in PLANS:
                price = float(PLANS[plan_name].get("precio", 25.0))
                days = int(PLANS[plan_name].get("dias", 30))
            elif plan_name in PLAN_PRICES:
                price = float(PLAN_PRICES[plan_name])
        except Exception:
            pass

        self.pay_amount_usd.value = f"{price:.2f}"
        self.pay_days_field.value = str(days)
        self._update_bcv_payment_preview()
        if hasattr(self, "page") and self.page:
            try:
                self.pay_amount_usd.update()
                self.pay_days_field.update()
            except Exception:
                pass

    def _on_pay_amount_change(self, e):
        self._update_bcv_payment_preview()

    def _update_bcv_payment_preview(self):
        try:
            amount = float(self.pay_amount_usd.value or 0.0)
        except Exception:
            amount = 0.0

        rate = bcv_service.get_rate()
        amount_bs = bcv_service.to_bs(amount)
        self.pay_bcv_rate_label.value = f"Tasa BCV: {rate:.2f} Bs/$"
        self.pay_amount_bs.value = f"Total Bs: {amount_bs:,.2f}"
        if hasattr(self, "page") and self.page:
            try:
                self.pay_bcv_rate_label.update()
                self.pay_amount_bs.update()
            except Exception:
                pass

    def _process_payment_submit(self, e):
        member = self._target_member_for_payment
        if not member:
            return

        self.pay_amount_usd.error_text = None
        self.pay_days_field.error_text = None

        has_error = False
        try:
            amount = float(self.pay_amount_usd.value or 0.0)
            if amount <= 0:
                self.pay_amount_usd.error_text = "El monto debe ser mayor a 0"
                has_error = True
        except ValueError:
            self.pay_amount_usd.error_text = "Monto numérico inválido (ej: 25.00)"
            has_error = True

        try:
            days = int(self.pay_days_field.value or 30)
            if days <= 0:
                self.pay_days_field.error_text = "Días debe ser mayor a 0"
                has_error = True
        except ValueError:
            self.pay_days_field.error_text = "Días numéricos enteros inválidos"
            has_error = True

        if has_error:
            self.pay_amount_usd.update()
            self.pay_days_field.update()
            return

        plan = self.pay_plan_field.value
        method = self.pay_method_field.value
        note = (self.pay_note_field.value or "").strip()

        result = process_membership_payment(
            cedula=member["cedula"],
            plan=plan,
            amount=amount,
            days=days,
            method=method,
            note=note,
        )

        if not result.get("success"):
            self.pay_amount_usd.error_text = str(result.get("error"))
            self.pay_amount_usd.update()
            return

        self._close_modal(self.payment_dialog)
        self.table_body.controls = self._build_rows()
        self.table_body.update()
        self._show_notification(
            f"Pago registrado (${amount:.2f} / {bcv_service.format_bs(bcv_service.to_bs(amount))}). Membresía renovada hasta {result['new_vencimiento']}",
            ACCENT_SUCCESS,
        )

    # -----------------------------------------------------------------------
    # DEACTIVATE / SOFT-DELETE & REACTIVATE Member Handlers
    # -----------------------------------------------------------------------
    def _open_delete_dialog(self, member: dict):
        self._target_member_for_deletion = member
        self.delete_confirm_text.value = (
            f"¿Está seguro de desactivar a {member.get('nombre')} (Cédula: {member.get('cedula')})?\n\n"
            "ℹ️ SOFT DELETE ACTIVO:\n"
            "El socio NO será borrado de la base de datos ni se perderá su historial de pagos, asistencias o ventas. "
            "Su estado pasará a 'Inactivo', su acceso al gimnasio quedará bloqueado y podrá consultarlo o reactivarlo "
            "en cualquier momento filtrando por 'DESACTIVADOS / INACTIVOS'."
        )
        self._open_modal(self.delete_confirm_dialog)

    def _confirm_delete_member(self, e):
        member = self._target_member_for_deletion
        if not member:
            return

        cedula = member.get("cedula")
        nombre = member.get("nombre")
        from core.mock_data import deactivate_member
        success = deactivate_member(cedula)
        self._close_modal(self.delete_confirm_dialog)

        if success:
            self.table_body.controls = self._build_rows()
            self.table_body.update()
            self._show_notification(
                f"Socio {nombre} desactivado (Inactivo). Lo encontrará en el filtro 'DESACTIVADOS'.",
                "#b91c1c",
            )
        else:
            self._show_notification("No se pudo desactivar el socio", ACCENT_DANGER)

    def _reactivate_member_handler(self, member: dict):
        if not member:
            return
        cedula = member.get("cedula")
        nombre = member.get("nombre")
        from core.mock_data import reactivate_member
        success = reactivate_member(cedula)
        if success:
            self.table_body.controls = self._build_rows()
            self.table_body.update()
            self._show_notification(
                f"✅ Socio {nombre} ({cedula}) reactivado exitosamente (Estado: {member.get('estado')}).",
                ACCENT_SUCCESS,
            )
        else:
            self._show_notification("No se pudo reactivar el socio", ACCENT_DANGER)

    # -----------------------------------------------------------------------
    # LINK Tag Handlers
    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # Multi-NFC Keys Management Handlers (Phone, Cards, Smartwatches, Fobs)
    # -----------------------------------------------------------------------
    def _open_nfc_keys_dialog(self, member: dict):
        self._target_member_for_nfc = member
        self._editing_nfc_key_id = None
        self.nfc_keys_member_info.value = f"Socio: {member.get('nombre')} • Cédula: {member.get('cedula')}"
        self._cancel_nfc_key_edit()
        self._refresh_nfc_keys_list()
        self._open_modal(self.multi_nfc_dialog)

    def _refresh_nfc_keys_list(self):
        from core.mock_data import get_member_nfc_keys
        member = self._target_member_for_nfc
        if not member:
            return

        keys = get_member_nfc_keys(member.get("cedula", ""))
        cards = []
        for k in keys:
            key_id = k.get("id")
            uid = k.get("nfc_id", "")
            alias = k.get("alias", "Llavero")
            created = str(k.get("created_at", ""))[:10]

            alias_lower = alias.lower()
            if any(w in alias_lower for w in ("tel", "phone", "movil", "cel", "iphone", "android")):
                icon_type = ft.Icons.SMARTPHONE
                icon_color = ft.Colors.CYAN_ACCENT
            elif any(w in alias_lower for w in ("reloj", "watch", "band", "pulsera")):
                icon_type = ft.Icons.WATCH
                icon_color = ft.Colors.AMBER_ACCENT
            else:
                icon_type = ft.Icons.KEY_ROUNDED
                icon_color = ACCENT_PRIMARY

            cards.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(icon_type, size=18, color=icon_color),
                            ft.Column(
                                controls=[
                                    ft.Text(alias, size=13, weight="w600", color=TEXT_PRIMARY),
                                    ft.Text(f"UID: {uid} • Reg: {created}", size=11, color=TEXT_MUTED),
                                ],
                                spacing=1,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT_NOTE,
                                icon_size=18,
                                icon_color=ACCENT_PRIMARY,
                                tooltip="Editar alias o sobre-escribir UID",
                                on_click=lambda e, key_item=k: self._edit_nfc_key_item(key_item),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=18,
                                icon_color=ACCENT_DANGER,
                                tooltip="Eliminar llave",
                                on_click=lambda e, kid=key_id: self._delete_nfc_key_item(kid),
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=BG_CARD,
                    border_radius=RADIUS_SM,
                    border=ft.Border.all(1, BORDER),
                )
            )

        if not cards:
            cards.append(
                ft.Container(
                    content=ft.Text("No hay llaves registradas. Agregue una abajo.", size=12, color=TEXT_MUTED),
                    padding=10,
                    alignment=ft.Alignment(0, 0),
                )
            )

        self.nfc_keys_list_container.controls = cards
        if hasattr(self, "page") and self.page:
            try:
                self.nfc_keys_list_container.update()
            except Exception:
                pass

    def _start_scan_for_multi_key(self, e):
        self.nfc_key_status_label.value = "Acerque el dispositivo (llavero, tarjeta, teléfono) al ACR122U..."
        self.nfc_key_status_label.color = ACCENT_PRIMARY
        try:
            self.nfc_key_status_label.update()
        except Exception:
            pass
        nfc_reader.set_enroll_mode(self._on_multi_key_scanned)

    def _on_multi_key_scanned(self, uid: str):
        clean_uid = "".join(c for c in (uid or "").upper() if c.isalnum())
        self.nfc_key_uid_field.value = clean_uid
        self.nfc_key_uid_field.error_text = None
        self.nfc_key_status_label.value = f"¡Dispositivo detectado! UID: {clean_uid}"
        self.nfc_key_status_label.color = ACCENT_SUCCESS
        if hasattr(self, "page") and self.page:
            try:
                self.nfc_key_uid_field.update()
                self.nfc_key_status_label.update()
            except Exception:
                pass

    def _edit_nfc_key_item(self, key_item: dict):
        self._editing_nfc_key_id = key_item.get("id")
        self.nfc_key_alias_field.value = key_item.get("alias", "")
        self.nfc_key_alias_field.error_text = None
        self.nfc_key_uid_field.value = key_item.get("nfc_id", "")
        self.nfc_key_uid_field.error_text = None
        self.nfc_key_submit_btn.text = "Guardar Cambios"
        self.nfc_key_cancel_edit_btn.visible = True
        self.nfc_key_status_label.value = f"Modificando llave ID #{self._editing_nfc_key_id}. Puede sobre-escribir UID o alias."
        self.nfc_key_status_label.color = ACCENT_PRIMARY
        if hasattr(self, "page") and self.page:
            try:
                self.nfc_key_alias_field.update()
                self.nfc_key_uid_field.update()
                self.nfc_key_submit_btn.update()
                self.nfc_key_cancel_edit_btn.update()
                self.nfc_key_status_label.update()
            except Exception:
                pass

    def _cancel_nfc_key_edit(self, e=None):
        self._editing_nfc_key_id = None
        self.nfc_key_alias_field.value = "Teléfono / Llavero"
        self.nfc_key_alias_field.error_text = None
        self.nfc_key_uid_field.value = ""
        self.nfc_key_uid_field.error_text = None
        self.nfc_key_submit_btn.text = "Vincular Llave"
        self.nfc_key_cancel_edit_btn.visible = False
        self.nfc_key_status_label.value = "Puede escribir el UID manualmente o presionar 'Leer ACR122U'"
        self.nfc_key_status_label.color = TEXT_MUTED
        if hasattr(self, "page") and self.page:
            try:
                self.nfc_key_alias_field.update()
                self.nfc_key_uid_field.update()
                self.nfc_key_submit_btn.update()
                self.nfc_key_cancel_edit_btn.update()
                self.nfc_key_status_label.update()
            except Exception:
                pass

    def _submit_add_or_update_nfc_key(self, e):
        member = self._target_member_for_nfc
        if not member:
            return

        self.nfc_key_alias_field.error_text = None
        self.nfc_key_uid_field.error_text = None

        alias = (self.nfc_key_alias_field.value or "").strip()
        raw_uid = (self.nfc_key_uid_field.value or "").strip().upper()
        clean_uid = "".join(c for c in raw_uid if c.isalnum())

        has_error = False
        if not alias:
            self.nfc_key_alias_field.error_text = "El alias es obligatorio"
            has_error = True

        if not clean_uid or len(clean_uid) < 4:
            self.nfc_key_uid_field.error_text = "UID NFC inválido (mínimo 4 caracteres alfanuméricos)"
            has_error = True

        if has_error:
            self.nfc_key_alias_field.update()
            self.nfc_key_uid_field.update()
            return

        from core.mock_data import register_member_nfc_key, update_member_nfc_key_entry

        if self._editing_nfc_key_id:
            # Overwrite or update existing key
            ok, msg = update_member_nfc_key_entry(self._editing_nfc_key_id, clean_uid, alias)
            if not ok:
                self.nfc_key_uid_field.error_text = msg
                self.nfc_key_uid_field.update()
                return
            self._show_notification(f"Llave actualizada: {msg}", ACCENT_SUCCESS)
        else:
            # Add new key
            ok, msg = register_member_nfc_key(member["cedula"], clean_uid, alias)
            if not ok:
                self.nfc_key_uid_field.error_text = msg
                self.nfc_key_uid_field.update()
                return
            self._show_notification(f"Llave vinculada: {msg}", ACCENT_SUCCESS)

        self._cancel_nfc_key_edit()
        self._refresh_nfc_keys_list()
        self.table_body.controls = self._build_rows()
        if hasattr(self, "page") and self.page:
            try:
                self.table_body.update()
            except Exception:
                pass

    def _delete_nfc_key_item(self, key_id: int):
        from core.mock_data import delete_member_nfc_key_entry
        ok = delete_member_nfc_key_entry(key_id)
        if ok:
            self._show_notification("Llave NFC eliminada con éxito", ACCENT_SUCCESS)
            self._refresh_nfc_keys_list()
            self.table_body.controls = self._build_rows()
            if hasattr(self, "page") and self.page:
                try:
                    self.table_body.update()
                except Exception:
                    pass
        else:
            self._show_notification("No se pudo eliminar la llave", ACCENT_DANGER)

    def _open_link_fob_dialog(self, member: dict):
        self._open_nfc_keys_dialog(member)

    def _cancel_link_fob(self, e):
        self._close_modal(self.multi_nfc_dialog)

    def _show_notification(self, message: str, color: str):
        if hasattr(self, "page") and self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=TEXT_PRIMARY),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            self.page.update()
