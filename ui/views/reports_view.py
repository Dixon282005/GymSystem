"""Comprehensive Financial, Attendance & Retention Reports View.
Provides shift cash closure summaries, payment method breakdowns,
member retention analysis, and direct Excel & text report downloads.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import os
from typing import Optional

import flet as ft

from core.bcv_service import bcv_service
from core.event_bus import event_bus
from core.paths import get_reports_root
from core.reports_export import export_inactive_members_excel, save_daily_report_files
from core.repositories import (
    AccessRepository,
    AuditLogRepository,
    MemberRepository,
    PaymentRepository,
    SalesRepository,
    SettingsRepository,
)

ButtonControl = getattr(ft, "Button", ft.ElevatedButton)
from core.theme import (
    ACCENT_DANGER,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    ACCENT_WARNING,
    BCVRateChip,
    BG_BASE,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FONT_SIZE_LG,
    FONT_SIZE_MD,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
    PADDING_MD,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    button_primary,
    card_style,
    heading_text,
    label_text,
    show_snack,
)


def _fmt_bs(amount: float) -> str:
    return f"Bs. {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_usd(amount: float) -> str:
    return f"${amount:,.2f}"


class ReportsView(ft.Column):
    def __init__(self):
        self._selected_date = datetime.now().date()
        self._bcv_rate = bcv_service.get_rate()
        self._dialogs_attached = False

        self.date_label = ft.Text(
            f"Fecha del Reporte: {self._selected_date.isoformat()}",
            size=FONT_SIZE_MD,
            color=TEXT_PRIMARY,
            weight=ft.FontWeight.W_600,
        )

        # Totals and breakdown controls
        self.payments_total_usd = ft.Text("$0.00", size=FONT_SIZE_LG, color=ACCENT_SUCCESS, weight=ft.FontWeight.W_700)
        self.payments_total_bs = ft.Text("Bs. 0,00", size=FONT_SIZE_SM, color=TEXT_MUTED)

        self.breakdown_efectivo = ft.Text("Efectivo: $0.00 (Bs. 0,00)", size=FONT_SIZE_XS, color=TEXT_SECONDARY)
        self.breakdown_transferencia = ft.Text("Transfer: $0.00 (Bs. 0,00)", size=FONT_SIZE_XS, color=TEXT_SECONDARY)
        self.breakdown_pago_movil = ft.Text("Pago Móvil: $0.00 (Bs. 0,00)", size=FONT_SIZE_XS, color=TEXT_SECONDARY)
        self.breakdown_punto = ft.Text("Punto: $0.00 (Bs. 0,00)", size=FONT_SIZE_XS, color=TEXT_SECONDARY)

        self.payments_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self.created_members_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        self.sales_total_usd = ft.Text("$0.00", size=FONT_SIZE_LG, color=ACCENT_PRIMARY, weight=ft.FontWeight.W_700)
        self.sales_total_bs = ft.Text("Bs. 0,00", size=FONT_SIZE_SM, color=TEXT_MUTED)
        self.sales_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        self.access_stats = ft.Text("Permitidos: 0 · Check-outs: 0 · Denegados: 0", size=FONT_SIZE_SM, color=TEXT_SECONDARY)
        self.access_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        # Retention tab controls
        self._retention_days = 30
        self._retention_members = []
        self.retention_days_dropdown = ft.Dropdown(
            label="Sin ingreso hace más de",
            options=[
                ft.dropdown.Option("7", "7 días"),
                ft.dropdown.Option("15", "15 días"),
                ft.dropdown.Option("30", "30 días"),
                ft.dropdown.Option("60", "60 días"),
            ],
            value="30",
            width=160,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=FONT_SIZE_SM,
            on_select=self._on_retention_days_change,
        )
        self.retention_count = ft.Text("0 miembros", size=FONT_SIZE_SM, color=TEXT_MUTED)
        self.retention_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

        # Shift and cash closure settings
        settings = SettingsRepository.get_all()
        last_close = settings.get("last_close_timestamp", "") or "Sin cierre registrado"
        self.last_close_label = ft.Text(f"Inicio del turno actual: {last_close}", size=FONT_SIZE_XS, color=TEXT_MUTED)

        self.auto_checkout_switch = ft.Switch(
            label="Sacar automáticamente a todos los del gym al cerrar caja (12:00 AM)",
            value=bool(settings.get("auto_checkout_on_close", False)),
            active_color=ACCENT_PRIMARY,
            label_text_style=ft.TextStyle(size=FONT_SIZE_XS, color=TEXT_SECONDARY),
            on_change=self._on_auto_checkout_changed,
        )

        reports_path = get_reports_root()
        self.auto_close_info = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SCHEDULE, size=16, color=ACCENT_PRIMARY),
                            ft.Text(
                                "La caja se cierra automáticamente todos los días a las 12:00 AM (medianoche) para comenzar el siguiente día. Exportar no cierra la caja; el cierre del turno ocurre automáticamente a medianoche.",
                                size=FONT_SIZE_XS,
                                color=TEXT_MUTED,
                                expand=True,
                            ),
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Text(f"Los reportes se guardan en: {reports_path}", size=FONT_SIZE_XS, color=TEXT_MUTED),
                ],
                spacing=4,
            ),
            padding=ft.padding.all(10),
            bgcolor=BG_BASE,
            border=ft.border.all(1, BORDER),
            border_radius=RADIUS_SM,
        )

        self.date_picker = ft.DatePicker(
            on_change=self._on_date_changed,
            first_date=datetime(2025, 1, 1),
            last_date=datetime(2030, 12, 31),
        )

        # Arqueo & Cash Closure Dialog
        self.arqueo_summary_container = ft.Column(spacing=8)
        self.arqueo_auto_checkout_chk = ft.Checkbox(label="Marcar salida a los socios actualmente en sala", value=True)
        self.arqueo_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.POINT_OF_SALE, color=ACCENT_WARNING, size=24),
                    heading_text("Cierre de Turno y Arqueo de Caja", size=FONT_SIZE_MD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.arqueo_summary_container,
                        ft.Container(height=4),
                        self.arqueo_auto_checkout_chk,
                    ],
                    tight=True,
                    spacing=8,
                ),
                width=460,
                padding=PADDING_MD,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_dialog(self.arqueo_dialog)),
                ButtonControl(
                    content=ft.Row([ft.Icon(ft.Icons.LOCK, size=16, color="#ffffff"), ft.Text("Confirmar Cierre de Turno", size=FONT_SIZE_SM, color="#ffffff")], spacing=6),
                    bgcolor=ACCENT_WARNING,
                    on_click=self._confirm_cash_closure,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # Top Bar
        header = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.ASSESSMENT, color=ACCENT_PRIMARY, size=24),
                        heading_text("Reportes del turno", size=FONT_SIZE_LG),
                        BCVRateChip(self._bcv_rate),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    controls=[
                        ButtonControl(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.REFRESH, size=16, color="#ffffff"),
                                    ft.Text("Actualizar", size=FONT_SIZE_SM, color="#ffffff", weight=ft.FontWeight.W_600),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            bgcolor=BG_INPUT,
                            on_click=self._on_refresh_click,
                            style=ft.ButtonStyle(
                                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                                shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                            ),
                        ),
                        ButtonControl(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.DATE_RANGE, size=16, color="#ffffff"),
                                    ft.Text("Seleccionar Fecha", size=FONT_SIZE_SM, color="#ffffff", weight=ft.FontWeight.W_600),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            bgcolor=BG_INPUT,
                            on_click=self._open_date_picker,
                            style=ft.ButtonStyle(
                                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                                shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                            ),
                        ),
                        ButtonControl(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.LOCK_CLOCK, size=16, color="#ffffff"),
                                    ft.Text("Cerrar Turno Ahora", size=FONT_SIZE_SM, color="#ffffff", weight=ft.FontWeight.W_600),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            bgcolor=ft.Colors.AMBER_800,
                            on_click=self._open_arqueo_dialog,
                            style=ft.ButtonStyle(
                                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                                shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                            ),
                        ),
                        button_primary("Exportar reporte del turno", on_click=self._direct_download_excel, icon=ft.Icons.FILE_DOWNLOAD),
                    ],
                    spacing=10,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # Tab panels
        payments_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column([label_text("Membresías Cobradas"), self.payments_total_usd, self.payments_total_bs], spacing=2),
                            ft.Column(
                                [
                                    ft.Row([self.breakdown_efectivo, self.breakdown_transferencia], spacing=10),
                                    ft.Row([self.breakdown_pago_movil, self.breakdown_punto], spacing=10),
                                ],
                                spacing=4,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color=BORDER, height=1),
                    ft.Container(content=self.payments_list, expand=True),
                ],
                spacing=10,
                expand=True,
            ),
            **card_style(),
            expand=True,
        )

        created_card = ft.Container(
            content=ft.Column(
                [
                    label_text("Clientes Registrados Hoy"),
                    ft.Text("Lista de nuevos registros en el sistema", size=FONT_SIZE_XS, color=TEXT_MUTED),
                    ft.Divider(color=BORDER, height=1),
                    ft.Container(content=self.created_members_list, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            **card_style(),
            expand=True,
        )

        sales_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            label_text("Ventas de Cantina"),
                            ft.Row([self.sales_total_usd, self.sales_total_bs], spacing=8),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color=BORDER, height=1),
                    ft.Container(content=self.sales_list, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            **card_style(),
            expand=True,
        )

        access_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            label_text("Registro de Accesos"),
                            self.access_stats,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color=BORDER, height=1),
                    ft.Container(content=self.access_list, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            **card_style(),
            expand=True,
        )

        retention_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row([self.retention_days_dropdown, self.retention_count], spacing=12),
                            ButtonControl(
                                content=ft.Row(
                                    [
                                        ft.Icon(ft.Icons.FILE_DOWNLOAD, size=16),
                                        ft.Text("Exportar Excel", size=FONT_SIZE_SM),
                                    ],
                                    spacing=6,
                                    tight=True,
                                ),
                                bgcolor=BG_INPUT,
                                color=TEXT_PRIMARY,
                                on_click=self._export_retention_excel,
                                style=ft.ButtonStyle(
                                    padding=ft.padding.symmetric(horizontal=12, vertical=10),
                                    shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color=BORDER, height=1),
                    ft.Container(content=self.retention_list, expand=True),
                ],
                spacing=8,
                expand=True,
            ),
            **card_style(),
            expand=True,
        )

        # Tabs
        self.tab_bar = ft.TabBar(
            tabs=[
                ft.Tab(label="Membresías / Pagos"),
                ft.Tab(label="Clientes Creados Hoy"),
                ft.Tab(label="Ventas POS (Cantina)"),
                ft.Tab(label="Accesos del Día"),
                ft.Tab(label="Retención"),
            ]
        )
        self.tab_view = ft.TabBarView(
            controls=[
                payments_card,
                created_card,
                sales_card,
                access_card,
                retention_card,
            ],
            expand=True,
        )
        self.tabs = ft.Tabs(
            length=5,
            selected_index=0,
            content=ft.Column([self.tab_bar, self.tab_view], expand=True, spacing=10),
            expand=True,
        )


        super().__init__(
            controls=[
                header,
                ft.Row([self.date_label, self.last_close_label], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(content=self.tabs, expand=True),
                ft.Row([self.auto_checkout_switch], alignment=ft.MainAxisAlignment.START),
                self.auto_close_info,
            ],
            spacing=10,
            expand=True,
        )

    def did_mount(self):
        try:
            if self.page and not self._dialogs_attached:
                if self.date_picker not in self.page.overlay:
                    self.page.overlay.append(self.date_picker)
                self._dialogs_attached = True
                self.page.update()
            event_bus.subscribe("sales_changed", self._on_event_refresh)
            event_bus.subscribe("access_scan", self._on_event_refresh)
            event_bus.subscribe("members_changed", self._on_event_refresh)
            event_bus.subscribe("bcv_updated", self._on_event_refresh)
            self._load_report_data()
            self._load_retention_data()
        except Exception as ex:
            print(f"[ReportsView.did_mount] Error: {ex}")

    def will_unmount(self):
        try:
            event_bus.unsubscribe("sales_changed", self._on_event_refresh)
            event_bus.unsubscribe("access_scan", self._on_event_refresh)
            event_bus.unsubscribe("members_changed", self._on_event_refresh)
            event_bus.unsubscribe("bcv_updated", self._on_event_refresh)
            if self.page and self._dialogs_attached:
                if self.date_picker in self.page.overlay:
                    self.page.overlay.remove(self.date_picker)
                self._dialogs_attached = False
        except Exception:
            pass

    def _on_event_refresh(self, data=None):
        try:
            self._bcv_rate = bcv_service.get_rate()
            self._load_report_data()
            self._load_retention_data()
            if hasattr(self, "page") and self.page:
                self.update()
        except Exception as ex:
            print(f"[ReportsView._on_event_refresh] Error: {ex}")

    def _on_refresh_click(self, e):
        self._on_event_refresh()
        if hasattr(self, "page") and self.page:
            show_snack(self.page, "Reportes actualizados correctamente", ft.Icons.CHECK_CIRCLE, ACCENT_SUCCESS)

    def _open_date_picker(self, e):
        if self._dialogs_attached and self.page:
            self.date_picker.open = True
            self.page.update()

    def _on_date_changed(self, e):
        try:
            if self.date_picker.value:
                self._selected_date = self.date_picker.value.date()
                self.date_label.value = f"Fecha del Reporte: {self._selected_date.isoformat()}"
                self._load_report_data()
                self.update()
        except Exception as ex:
            print(f"[ReportsView._on_date_changed] Error: {ex}")

    def _load_report_data(self):
        target_date_str = self._selected_date.isoformat()

        # Update last close label
        settings = SettingsRepository.get_all()
        last_close = settings.get("last_close_timestamp", "") or "Sin cierre registrado"
        self.last_close_label.value = f"Inicio del turno actual: {last_close}"

        # 1. Payments
        all_payments = PaymentRepository.list_payments(limit=2000)
        payments_today = [
            p for p in all_payments
            if str(p.get("fecha_pago", "") or p.get("created_at", ""))[:10] == target_date_str
        ]

        total_pay_usd = sum(float(p.get("monto", 0.0)) for p in payments_today)
        total_pay_bs = sum(
            float(p.get("monto_bs", 0.0)) if float(p.get("monto_bs", 0.0)) > 0 else float(p.get("monto", 0.0)) * self._bcv_rate
            for p in payments_today
        )

        self.payments_total_usd.value = _fmt_usd(total_pay_usd)
        self.payments_total_bs.value = _fmt_bs(total_pay_bs)

        by_method = {"efectivo": 0.0, "transferencia": 0.0, "pago_movil": 0.0, "punto": 0.0}
        pay_rows = []
        for p in payments_today:
            met = str(p.get("metodo", "efectivo")).strip().lower().replace(" ", "_")
            monto = float(p.get("monto", 0.0))
            if met in by_method:
                by_method[met] += monto

            p_rate = float(p.get("tasa_bcv", 0.0)) or float(p.get("tasa_valor", 0.0)) or self._bcv_rate
            bs_amount = float(p.get("monto_bs", 0.0)) or (monto * p_rate)

            member_name = p.get("nombre")
            if not member_name:
                member = MemberRepository.find_by_cedula(p.get("cedula", ""))
                member_name = member.get("nombre", "Miembro no encontrado") if member else "—"

            p_time = str(p.get("fecha_pago", ""))[11:16]
            time_txt = f" · Hora: {p_time}" if p_time else ""
            ref_txt = f" · Ref: {p.get('referencia')}" if p.get("referencia") else ""
            dias_txt = f" ({p.get('dias')} días)" if p.get("dias") else ""

            row = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(f"{p.get('cedula', '')} · {member_name}", size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                ft.Text(
                                    f"Plan: {p.get('plan', '')}{dias_txt} · Método: {p.get('metodo', '').title()}{ref_txt}{time_txt}",
                                    size=FONT_SIZE_XS,
                                    color=TEXT_MUTED,
                                ),
                                ft.Text(
                                    f"Período: {p.get('fecha_inicio', '')} a {p.get('fecha_fin', '')}" if p.get("fecha_inicio") else f"Registrado: {p.get('fecha_pago', '')}",
                                    size=FONT_SIZE_XS,
                                    color=TEXT_SECONDARY,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.Column(
                            controls=[
                                ft.Text(_fmt_usd(monto), size=FONT_SIZE_SM, color=ACCENT_SUCCESS, weight=ft.FontWeight.W_700),
                                ft.Text(_fmt_bs(bs_amount), size=FONT_SIZE_XS, color=TEXT_MUTED),
                            ],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            width=140,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
            )
            pay_rows.append(row)

        self.breakdown_efectivo.value = f"Efectivo: {_fmt_usd(by_method['efectivo'])} ({_fmt_bs(by_method['efectivo'] * self._bcv_rate)})"
        self.breakdown_transferencia.value = f"Transfer: {_fmt_usd(by_method['transferencia'])} ({_fmt_bs(by_method['transferencia'] * self._bcv_rate)})"
        self.breakdown_pago_movil.value = f"Pago Móvil: {_fmt_usd(by_method['pago_movil'])} ({_fmt_bs(by_method['pago_movil'] * self._bcv_rate)})"
        self.breakdown_punto.value = f"Punto: {_fmt_usd(by_method['punto'])} ({_fmt_bs(by_method['punto'] * self._bcv_rate)})"

        self.payments_list.controls = pay_rows or [
            ft.Container(content=ft.Text("No hay pagos registrados para este día", color=TEXT_MUTED, size=FONT_SIZE_SM), padding=20)
        ]

        # 2. Created Members
        all_logs = AuditLogRepository.list_logs(limit=2000)
        created_today = [
            l for l in all_logs
            if l.get("action") in ("REGISTRO_SOCIO", "CREAR_SOCIO", "CREAR_MIEMBRO")
            and str(l.get("timestamp", ""))[:10] == target_date_str
        ]
        created_rows = []
        for l in created_today:
            details_raw = l.get("details", "{}")
            try:
                details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
            except Exception:
                details = {}

            pay_info = ""
            if details.get("monto_pago_usd"):
                pay_info = f" · Pago Inicial: ${_fmt_usd(float(details['monto_pago_usd']))}"

            created_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                [
                                    ft.Text(f"{details.get('cedula', '')} · {details.get('nombre', '')}", size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                    ft.Text(f"Plan: {details.get('plan', '')}{pay_info} · Creado por: {l.get('username', 'sistema')}", size=FONT_SIZE_XS, color=TEXT_MUTED),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Text(str(l.get("timestamp", ""))[11:16], size=FONT_SIZE_SM, color=TEXT_SECONDARY),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                )
            )

        self.created_members_list.controls = created_rows or [
            ft.Container(content=ft.Text("No hay clientes creados hoy", color=TEXT_MUTED, size=FONT_SIZE_SM), padding=20)
        ]

        # 3. Sales
        all_sales = SalesRepository.list_recent(limit=2000)
        sales_today = [
            s for s in all_sales
            if (s.get("fecha") or str(s.get("sold_at", ""))[:10]) == target_date_str
        ]

        total_sales_usd = sum(float(s.get("monto", 0.0)) for s in sales_today)
        total_sales_bs = total_sales_usd * self._bcv_rate

        self.sales_total_usd.value = _fmt_usd(total_sales_usd)
        self.sales_total_bs.value = _fmt_bs(total_sales_bs)

        sales_rows = []
        for s in sales_today:
            monto = float(s.get("monto", 0.0))
            s_hora = s.get("hora") or (str(s.get("sold_at", ""))[11:16] if s.get("sold_at") else "")
            sales_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(s.get("producto", ""), size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight=ft.FontWeight.W_500, expand=True),
                            ft.Text(s_hora, size=FONT_SIZE_XS, color=TEXT_MUTED, width=80),
                            ft.Text(_fmt_usd(monto), size=FONT_SIZE_SM, color=ACCENT_PRIMARY, weight=ft.FontWeight.W_600),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                )
            )

        self.sales_list.controls = sales_rows or [
            ft.Container(content=ft.Text("No hay ventas POS registradas para este día", color=TEXT_MUTED, size=FONT_SIZE_SM), padding=20)
        ]

        # 4. Accesses
        all_access = AccessRepository.list_recent(limit=2000)
        access_today = [
            a for a in all_access
            if (a.get("fecha") or str(a.get("event_time", ""))[:10]) == target_date_str
        ]

        count_allowed = sum(1 for a in access_today if a.get("status") in ("PERMITIDO", "ENTRADA"))
        count_checkout = sum(1 for a in access_today if a.get("status") in ("CHECK-OUT", "SALIDA"))
        count_denied = sum(1 for a in access_today if a.get("status") not in ("PERMITIDO", "ENTRADA", "CHECK-OUT", "SALIDA"))

        self.access_stats.value = f"Permitidos: {count_allowed} · Check-outs: {count_checkout} · Denegados: {count_denied}"

        access_rows = []
        for a in access_today:
            status = a.get("status", "PERMITIDO")
            if status in ("PERMITIDO", "ENTRADA"):
                st_color = ACCENT_SUCCESS
            elif status in ("CHECK-OUT", "SALIDA"):
                st_color = ACCENT_PRIMARY
            else:
                st_color = ACCENT_DANGER

            a_hora = a.get("hora") or (str(a.get("event_time", ""))[11:16] if a.get("event_time") else "")
            access_rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(f"{a.get('cedula', '')} · {a.get('nombre', '')}", size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                    ft.Text(f"Plan: {a.get('plan', '')}", size=FONT_SIZE_XS, color=TEXT_MUTED),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Text(status, size=FONT_SIZE_XS, color="#ffffff", weight=ft.FontWeight.W_600),
                                bgcolor=st_color,
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                border_radius=RADIUS_SM,
                            ),
                            ft.Text(a_hora, size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=60),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                )
            )

        self.access_list.controls = access_rows or [
            ft.Container(content=ft.Text("No hay registros de acceso para este día", color=TEXT_MUTED, size=FONT_SIZE_SM), padding=20)
        ]

        try:
            self.update()
        except Exception:
            pass

    def _on_auto_checkout_changed(self, e):
        try:
            settings = SettingsRepository.get_all()
            settings["auto_checkout_on_close"] = bool(self.auto_checkout_switch.value)
            SettingsRepository.save_all(settings)
            estado = "activado" if self.auto_checkout_switch.value else "desactivado"
            if self.page:
                show_snack(self.page, f"Check-out automático al cierre de caja {estado}.")
        except Exception as ex:
            if self.page:
                show_snack(self.page, f"Error guardando preferencia: {ex}")

    def _on_retention_days_change(self, e):
        try:
            self._retention_days = int(self.retention_days_dropdown.value or "30")
            self._load_retention_data()
        except Exception as ex:
            if self.page:
                show_snack(self.page, f"Error: {ex}")

    def _load_retention_data(self):
        try:
            members = MemberRepository.list_low_attendance(min_days=self._retention_days)
            self._retention_members = members
            count = len(members)
            suffix = "s" if count != 1 else ""
            self.retention_count.value = f"{count} miembro{suffix}"

            rows = []
            for m in members:
                dias = m.get("dias_sin_ingreso", -1)
                dias_txt = "Nunca ingresó" if dias == -1 else f"{dias} días sin ingreso"
                ultimo = m.get("ultimo_ingreso", "Nunca")

                rows.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Column(
                                    controls=[
                                        ft.Text(m.get("nombre", ""), size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                                        ft.Text(f"Cédula: {m.get('cedula', '')} · Tel: {m.get('telefono') or '—'}", size=FONT_SIZE_XS, color=TEXT_MUTED),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(f"Plan: {m.get('plan', '')} · {m.get('estado', '')}", size=FONT_SIZE_XS, color=TEXT_SECONDARY),
                                        ft.Text(f"Último ingreso: {ultimo}", size=FONT_SIZE_XS, color=TEXT_MUTED),
                                    ],
                                    spacing=2,
                                    width=180,
                                ),
                                ft.Container(
                                    content=ft.Text(dias_txt, size=FONT_SIZE_XS, color=ACCENT_WARNING, weight=ft.FontWeight.W_600),
                                    bgcolor=BG_BASE,
                                    border=ft.border.all(1, BORDER),
                                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                    border_radius=RADIUS_SM,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                    )
                )

            self.retention_list.controls = rows or [
                ft.Container(content=ft.Text(f"No hay miembros activos sin ingreso en {self._retention_days}+ días", color=TEXT_MUTED, size=FONT_SIZE_SM), padding=20)
            ]
            self.retention_count.update()
            self.retention_list.update()
        except Exception as ex:
            if self.page:
                show_snack(self.page, f"Error cargando retención: {ex}")

    def _export_retention_excel(self, e):
        try:
            filepath = export_inactive_members_excel(min_days=self._retention_days, members=self._retention_members)
            if self.page:
                show_snack(self.page, f"Reporte de retención guardado: {filepath}")
        except Exception as ex:
            if self.page:
                show_snack(self.page, f"Error al exportar retención: {ex}")

    def _direct_download_excel(self, e):
        try:
            month_folder = self._selected_date.strftime("%Y-%m")
            date_folder = self._selected_date.strftime("%Y-%m-%d")
            save_daily_report_files(target_date=self._selected_date, bcv_rate=self._bcv_rate)
            if self.page:
                show_snack(self.page, f"Reporte Excel y TXT guardados en: reports/{month_folder}/{date_folder}/")
        except Exception as ex:
            if self.page:
                show_snack(self.page, f"Error al generar reporte: {ex}")

    def _open_dialog(self, dialog):
        if self.page:
            if hasattr(self.page, "show_dialog"):
                try:
                    self.page.show_dialog(dialog)
                    return
                except Exception:
                    pass
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()

    def _close_dialog(self, dialog):
        if self.page:
            if hasattr(self.page, "pop_dialog"):
                try:
                    self.page.pop_dialog()
                    return
                except Exception:
                    pass
            dialog.open = False
            self.page.update()

    def _open_arqueo_dialog(self, e):
        from datetime import datetime
        from core.repositories import SettingsRepository
        from core.reports_export import collect_shift_data
        now = datetime.now()
        settings = SettingsRepository.get_all()
        start_str = settings.get("last_close_timestamp", "") or f"{now.date().isoformat()} 00:00"
        end_str = now.strftime("%Y-%m-%d %H:%M")

        payments_shift, sales_shift, access_shift = collect_shift_data(start_str, end_str)

        total_usd = sum(float(p.get("monto", 0.0) or 0.0) for p in payments_shift) + sum(float(s.get("monto", 0.0) or 0.0) for s in sales_shift)
        total_bs = sum(float(p.get("monto_bs", 0.0) or 0.0) for p in payments_shift) + sum(float(s.get("monto_bs", 0.0) or 0.0) for s in sales_shift)

        self.arqueo_summary_container.controls = [
            ft.Text(f"Período del Turno: {start_str}  →  {end_str}", size=12, color=TEXT_SECONDARY),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column([ft.Text("Total Recaudado (USD):", size=11, color=TEXT_MUTED), ft.Text(f"${total_usd:,.2f}", size=18, color=ACCENT_SUCCESS, weight=ft.FontWeight.W_700)]),
                        ft.Column([ft.Text("Total Recaudado (Bs.):", size=11, color=TEXT_MUTED), ft.Text(f"Bs. {total_bs:,.2f}", size=16, color=ACCENT_PRIMARY, weight=ft.FontWeight.W_700)]),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_AROUND,
                ),
                padding=10,
                bgcolor=BG_INPUT,
                border_radius=RADIUS_SM,
            ),
            ft.Text(f"• Pagos de Membresías: {len(payments_shift)} operaciones", size=12, color=TEXT_SECONDARY),
            ft.Text(f"• Ventas en Cafetín / POS: {len(sales_shift)} ventas", size=12, color=TEXT_SECONDARY),
            ft.Text(f"• Accesos registrados en sala: {len(access_shift)} toques", size=12, color=TEXT_SECONDARY),
        ]
        self._open_dialog(self.arqueo_dialog)

    def _confirm_cash_closure(self, e):
        from core.cash_closure import perform_cash_closure
        try:
            auto_co = bool(self.arqueo_auto_checkout_chk.value)
            res = perform_cash_closure(auto_checkout=auto_co, trigger="manual")
            self._close_dialog(self.arqueo_dialog)
            if self.page:
                show_snack(self.page, f"¡Turno cerrado con éxito! Reportes guardados en {res.get('relative_folder', 'reports/')}")
            self._on_refresh_click(None)
        except Exception as ex:
            if self.page:
                show_snack(self.page, f"Error en cierre de turno: {ex}")

