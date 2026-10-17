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
            value="TODOS",
            options=[
                ft.dropdown.Option("TODOS"),
                ft.dropdown.Option("ACTIVOS"),
                ft.dropdown.Option("MOROSOS"),
                ft.dropdown.Option("EN GYM"),
            ],
            width=130,
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
        self.cedula_prefix = ft.Dropdown(
            options=[
                ft.dropdown.Option("V"),
                ft.dropdown.Option("E"),
                ft.dropdown.Option("J"),
                ft.dropdown.Option("G"),
                ft.dropdown.Option("P"),
            ],
            value="V",
            width=75,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.cedula_number = ft.TextField(
            label="Cédula",
            hint_text="Ej: 12345678",
            keyboard_type=ft.KeyboardType.NUMBER,
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
        )
        self.nfc_field = ft.TextField(
            label="ID / UID de Tarjeta o Llavero NFC",
            hint_text="Presiona el botón para escanear...",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.nfc_scan_status = ft.Text(
            "Puedes escribir el ID o presionar el botón para leer el llavero en el ACR122U",
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

        # Table body
        self.table_body = ft.Column(
            controls=self._build_rows(),
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
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
                        ft.Row(
                            controls=[self.cedula_prefix, self.cedula_number],
                            spacing=8,
                        ),
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
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.new_member_dialog)),
                ft.ElevatedButton(
                    "Registrar Socio",
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

        # 4. Dialog for linking tag to existing member
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
                        ft.Container(height=10),
                        ft.Text("Coloque el llavero o pulsera sobre la antena. Se guardará de inmediato.", size=11, color=TEXT_MUTED),
                    ],
                    tight=True,
                ),
                padding=PADDING_MD,
                width=420,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._cancel_link_fob),
            ],
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # 5. Delete confirmation dialog
        self.delete_confirm_text = ft.Text("", size=13, color=TEXT_PRIMARY)
        self.delete_confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ACCENT_DANGER, size=24),
                    heading_text("Confirmar Eliminación", size=FONT_SIZE_MD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=self.delete_confirm_text,
                padding=PADDING_MD,
                width=420,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.delete_confirm_dialog)),
                ft.ElevatedButton(
                    "Eliminar Definitivamente",
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
                        on_click=lambda e: self._open_modal(self.new_member_dialog),
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
                        self.table_body,
                    ],
                    spacing=0,
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
        status_sel = (self.status_filter.value or "TODOS").upper()

        results = []
        for m in MEMBERS:
            if status_sel == "ACTIVOS" and m.get("estado") != "Activo":
                continue
            elif status_sel == "MOROSOS" and m.get("estado") != "Moroso":
                continue
            elif status_sel == "EN GYM" and not m.get("entrenando"):
                continue

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
                    ft.Text("Nombre", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", expand=1),
                    ft.Text("Plan", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=85),
                    ft.Text("Vencimiento", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=100),
                    ft.Text("Estado", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=90),
                    ft.Text("En Gym", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=70),
                    ft.Text("Llavero NFC", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=120),
                    ft.Text("Acciones", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=180),
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

            nfc_id = m.get("nfc_id") or "Sin asignar"
            in_gym = bool(m.get("entrenando", False))

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(m["cedula"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=110),
                            ft.Text(m["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600", expand=1),
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
                                nfc_id,
                                size=FONT_SIZE_XS,
                                color=TEXT_PRIMARY if nfc_id != "Sin asignar" else TEXT_MUTED,
                                width=120,
                            ),
                            # Action buttons
                            ft.Row(
                                controls=[
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
                                        icon=ft.Icons.NFC,
                                        icon_size=18,
                                        icon_color=TEXT_SECONDARY,
                                        tooltip="Vincular llavero",
                                        on_click=lambda e, mem=m: self._open_link_fob_dialog(mem),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        icon_size=18,
                                        icon_color=ACCENT_DANGER,
                                        tooltip="Eliminar socio",
                                        on_click=lambda e, mem=m: self._open_delete_dialog(mem),
                                    ),
                                ],
                                spacing=0,
                                width=180,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=6),
                    border=ft.Border(bottom=ft.BorderSide(1, BORDER)),
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

    # -----------------------------------------------------------------------
    # NEW Member Handlers (With Venezuelan Cédula Validation)
    # -----------------------------------------------------------------------
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
        prefix = (self.cedula_prefix.value or "V").strip().upper()
        raw_number = (self.cedula_number.value or "").strip()
        nombre = (self.nombre_field.value or "").strip()
        plan = (self.plan_field.value or "Basico").strip()
        nfc_id = (self.nfc_field.value or "").strip()

        # Strict Cédula validation
        digits = "".join(ch for ch in raw_number if ch.isdigit())
        if len(digits) < 6 or len(digits) > 10:
            self._show_notification("Cédula inválida. Debe ingresar entre 6 y 10 dígitos numéricos.", ACCENT_DANGER)
            return

        cedula = f"{prefix}-{digits}"

        # Strict Name validation
        if len(nombre) < 3 or not re.search(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]", nombre):
            self._show_notification("El nombre debe tener al menos 3 letras.", ACCENT_DANGER)
            return

        try:
            register_member(cedula=cedula, nombre=nombre, plan=plan, nfc_id=nfc_id)
        except ValueError as exc:
            self._show_notification(str(exc), ACCENT_DANGER)
            return

        self.table_body.controls = self._build_rows()
        self.table_body.update()

        self.cedula_number.value = ""
        self.nombre_field.value = ""
        self.plan_field.value = "Basico"
        self.nfc_field.value = ""
        self._close_modal(self.new_member_dialog)
        self._show_notification(f"Socio {nombre} ({cedula}) registrado exitosamente.", ACCENT_SUCCESS)

    # -----------------------------------------------------------------------
    # EDIT Member Handlers
    # -----------------------------------------------------------------------
    def _open_edit_dialog(self, member: dict):
        self.edit_cedula_field.value = member.get("cedula", "")
        self.edit_nombre_field.value = member.get("nombre", "")
        self.edit_plan_field.value = member.get("plan", "Basico")
        self.edit_venc_field.value = member.get("vencimiento", "")
        self.edit_estado_field.value = member.get("estado", "Activo")
        self.edit_nfc_field.value = member.get("nfc_id", "")
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
        cedula = (self.edit_cedula_field.value or "").strip()
        nombre = (self.edit_nombre_field.value or "").strip()
        plan = (self.edit_plan_field.value or "Basico").strip()
        venc = (self.edit_venc_field.value or "").strip()
        estado = (self.edit_estado_field.value or "Activo").strip()
        nfc_id = (self.edit_nfc_field.value or "").strip()

        if len(nombre) < 3:
            self._show_notification("El nombre debe tener al menos 3 letras.", ACCENT_DANGER)
            return

        try:
            update_member(
                cedula=cedula,
                updates={
                    "nombre": nombre,
                    "plan": plan,
                    "vencimiento": venc,
                    "estado": estado,
                    "nfc_id": nfc_id,
                },
            )
        except Exception as exc:
            self._show_notification(f"Error al actualizar: {exc}", ACCENT_DANGER)
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

        try:
            amount = float(self.pay_amount_usd.value or 0.0)
            if amount <= 0:
                self._show_notification("El monto debe ser mayor a 0", ACCENT_DANGER)
                return
        except ValueError:
            self._show_notification("Monto inválido", ACCENT_DANGER)
            return

        plan = self.pay_plan_field.value
        days = int(self.pay_days_field.value or 30)
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
            self._show_notification(f"Error: {result.get('error')}", ACCENT_DANGER)
            return

        self._close_modal(self.payment_dialog)
        self.table_body.controls = self._build_rows()
        self.table_body.update()
        self._show_notification(
            f"Pago registrado (${amount:.2f} / {bcv_service.format_bs(bcv_service.to_bs(amount))}). Membresía renovada hasta {result['new_vencimiento']}",
            ACCENT_SUCCESS,
        )

    # -----------------------------------------------------------------------
    # DELETE Member Handlers
    # -----------------------------------------------------------------------
    def _open_delete_dialog(self, member: dict):
        self._target_member_for_deletion = member
        self.delete_confirm_text.value = (
            f"¿Está seguro de eliminar al socio {member.get('nombre')} (Cédula: {member.get('cedula')})?\n\n"
            "Esta operación eliminará permanentemente su registro y desvinculará su tarjeta NFC."
        )
        self._open_modal(self.delete_confirm_dialog)

    def _confirm_delete_member(self, e):
        member = self._target_member_for_deletion
        if not member:
            return

        cedula = member.get("cedula")
        nombre = member.get("nombre")
        success = remove_member(cedula)
        self._close_modal(self.delete_confirm_dialog)

        if success:
            self.table_body.controls = self._build_rows()
            self.table_body.update()
            self._show_notification(f"Socio {nombre} eliminado correctamente.", "#b91c1c")
        else:
            self._show_notification("No se pudo eliminar el socio", ACCENT_DANGER)

    # -----------------------------------------------------------------------
    # LINK Tag Handlers
    # -----------------------------------------------------------------------
    def _open_link_fob_dialog(self, member: dict):
        self._target_member_for_linking = member
        self.link_fob_label.value = f"Acerque el llavero para {member['nombre']} al lector ACR122U..."
        self._open_modal(self.link_fob_dialog)
        nfc_reader.set_enroll_mode(self._on_fob_linked_to_existing_member)

    def _on_fob_linked_to_existing_member(self, uid: str):
        member = self._target_member_for_linking
        if not member:
            return

        update_member_nfc(member["cedula"], uid)
        self.table_body.controls = self._build_rows()

        if hasattr(self, "page") and self.page:
            try:
                self.table_body.update()
                self._close_modal(self.link_fob_dialog)
                self._show_notification(f"Llavero {uid} vinculado a {member['nombre']}", ACCENT_SUCCESS)
            except Exception:
                pass

    def _cancel_link_fob(self, e):
        self._close_modal(self.link_fob_dialog)

    def _show_notification(self, message: str, color: str):
        if hasattr(self, "page") and self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=TEXT_PRIMARY),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            self.page.update()
