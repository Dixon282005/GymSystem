"""Dashboard view — tactical real-time overview for the gym manager.
Reactively updates in real time on NFC scans, sales, membership payments and BCV rate changes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import flet as ft
from core.theme import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_WARNING, ACCENT_DANGER,
    FONT_SIZE_MD, FONT_SIZE_SM, BG_CARD, BG_INPUT, BORDER, RADIUS_MD, RADIUS_SM,
    card_style, heading_text, label_text,
)
from core.mock_data import MEMBERS, WEEKLY_ATTENDANCE, DAILY_SALES, ACCESS_LOG
from core.business import get_dashboard_metrics, _parse_date, register_access_attempt
from core.bcv_service import bcv_service
from core.event_bus import event_bus
from core.db_store import load_membership_payments
from ui.components.widgets import MetricCard, BarChartSim, HourlyPeakChart
from core.whatsapp_service import get_whatsapp_url


class DashboardView(ft.Column):
    """Dashboard with real-time reactive metric cards, currency conversions, and attendance insights."""

    def __init__(self):
        super().__init__(spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)
        self._current_dialog: Optional[ft.AlertDialog] = None

        # 1. Top KPI Metric Cards (clickable to open itemized modals)
        self.card_entrenando = MetricCard(
            icon=ft.Icons.DIRECTIONS_RUN,
            icon_color=ACCENT_SUCCESS,
            value="0",
            label="Entrenando Ahora",
            on_click=lambda _: self._show_entrenando_modal(),
        )
        self.card_proximos = MetricCard(
            icon=ft.Icons.EVENT_NOTE,
            icon_color=ACCENT_WARNING,
            value="0",
            label="Próx. a Vencer (7d)",
            on_click=lambda _: self._show_proximos_modal(),
        )
        self.card_morosos = MetricCard(
            icon=ft.Icons.PERSON_OFF,
            icon_color=ACCENT_DANGER,
            value="0",
            label="Morosos",
            on_click=lambda _: self._show_morosos_modal(),
        )
        self.card_ingresos = MetricCard(
            icon=ft.Icons.ACCOUNT_BALANCE_WALLET,
            icon_color=ACCENT_PRIMARY,
            value="$0.00",
            label="Ingresos del Día",
            on_click=lambda _: self._show_ingresos_modal(),
        )

        # 2. Summary elements
        self.txt_total_miembros = ft.Text("0", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600")
        self.txt_ocupacion = ft.Text("0/0", size=FONT_SIZE_MD, color=ACCENT_SUCCESS, weight="w600")
        self.txt_entradas_hoy = ft.Text("0", size=FONT_SIZE_MD, color=ACCENT_SUCCESS, weight="w600")
        self.txt_salidas_hoy = ft.Text("0", size=FONT_SIZE_MD, color=ft.Colors.CYAN_ACCENT, weight="w600")
        self.txt_plan_popular = ft.Text("-", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600")
        self.txt_ventas_pos = ft.Text("0", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600")
        self.txt_pagos_membresia = ft.Text("0", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600")
        self.txt_ticket_promedio = ft.Text("$0.00", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600")
        self.txt_tasa_bcv = ft.Text("0.00 Bs/$", size=FONT_SIZE_MD, color=ACCENT_PRIMARY, weight="w600")
        self.txt_ingreso_bs = ft.Text("Bs. 0.00", size=13, color=ACCENT_PRIMARY, weight="w600")

        # 3. Dynamic alert and analytics containers
        self.morosos_container = ft.Container(expand=True, **card_style())
        self.proximos_container = ft.Container(expand=True, **card_style())
        self.habitual_members_container = ft.Container(expand=True, **card_style())
        self._current_habit_shift = "all"
        self._last_habits = {}

        # Header with live refresh button
        self.header_row = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        heading_text("Dashboard Operativo"),
                        ft.Text("Monitoreo en tiempo real de accesos, socios e ingresos", size=12, color=TEXT_MUTED),
                    ],
                    spacing=2,
                ),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CURRENCY_EXCHANGE, size=16, color=ACCENT_PRIMARY),
                            ft.Text("Tasa BCV:", size=12, color=TEXT_MUTED),
                            self.txt_tasa_bcv,
                        ],
                        spacing=6,
                    ),
                    bgcolor=BG_CARD,
                    border=ft.Border.all(1, BORDER),
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    border_radius=RADIUS_SM,
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    icon_color=TEXT_SECONDARY,
                    tooltip="Actualizar métricas",
                    on_click=lambda _: self.refresh_dashboard(),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        self.chart_asistencia = BarChartSim(WEEKLY_ATTENDANCE)
        self.chart_horas_pico = HourlyPeakChart()

        # Assemble main view structure
        self.controls = [
            self.header_row,
            ft.Container(height=4),
            ft.Row(
                controls=[
                    self.card_entrenando,
                    self.card_proximos,
                    self.card_morosos,
                    self.card_ingresos,
                ],
                spacing=16,
            ),
            ft.Container(height=8),
            ft.Row(
                controls=[
                    self.chart_asistencia,
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                heading_text("Resumen Táctico", size=FONT_SIZE_MD),
                                ft.Container(height=8),
                                self._summary_row("Total Socios Registrados", self.txt_total_miembros),
                                self._summary_row("Aforo / Ocupación", self.txt_ocupacion),
                                self._summary_row("Entradas Registradas Hoy", self.txt_entradas_hoy),
                                self._summary_row("Salidas Registradas Hoy", self.txt_salidas_hoy),
                                self._summary_row("Plan Más Popular", self.txt_plan_popular),
                                self._summary_row("Ventas POS Realizadas", self.txt_ventas_pos),
                                self._summary_row("Membresías Renovadas Hoy", self.txt_pagos_membresia),
                                self._summary_row("Ticket Promedio Diario", self.txt_ticket_promedio),
                                self._summary_row("Ingresos Equivalentes en Bs.", self.txt_ingreso_bs),
                            ],
                            spacing=10,
                        ),
                        expand=True,
                        **card_style(),
                    ),
                ],
                spacing=16,
            ),
            ft.Container(height=8),
            ft.Row(
                controls=[
                    self.chart_horas_pico,
                    self.habitual_members_container,
                ],
                spacing=16,
            ),
            ft.Container(height=8),
            ft.Row(
                controls=[
                    self.morosos_container,
                    self.proximos_container,
                ],
                spacing=16,
            ),
        ]

        # Initial metrics calculation
        self._calculate_and_apply_metrics()

    def did_mount(self):
        """Subscribe to EventBus when mounted into the page."""
        event_bus.subscribe("access_scan", self._on_event)
        event_bus.subscribe("members_changed", self._on_event)
        event_bus.subscribe("sales_changed", self._on_event)
        event_bus.subscribe("bcv_updated", self._on_event)
        self.refresh_dashboard()

    def will_unmount(self):
        """Unsubscribe from EventBus when leaving page to avoid memory leaks."""
        event_bus.unsubscribe("access_scan", self._on_event)
        event_bus.unsubscribe("members_changed", self._on_event)
        event_bus.unsubscribe("sales_changed", self._on_event)
        event_bus.unsubscribe("bcv_updated", self._on_event)
        self.page = None

    def _on_event(self, data=None):
        if getattr(self, "page", None) is None:
            return
        self.refresh_dashboard()

    def refresh_dashboard(self):
        """Recompute all metrics and perform a thread-safe UI update."""
        if getattr(self, "page", None) is None:
            return
        self._calculate_and_apply_metrics()
        try:
            self.update()
        except Exception:
            pass

    def _calculate_and_apply_metrics(self):
        metrics = get_dashboard_metrics()
        entrenando = metrics["entrenando"]
        morosos = metrics["morosos"]
        proximos_vencer = metrics["proximos_vencer"]
        daily_income = metrics["daily_income"]
        daily_income_bs = metrics.get("daily_income_bs", 0.0)
        bcv_rate = metrics.get("bcv_rate", 0.0)

        # Update KPI Cards
        self.card_entrenando.value = str(entrenando)
        self.card_proximos.value = str(len(proximos_vencer))
        self.card_morosos.value = str(len(morosos))
        self.card_ingresos.value = f"${daily_income:.2f}"

        # Update Weekly Attendance Chart (De-duplicated unique members)
        weekly_data = metrics.get("weekly_attendance")
        if weekly_data and hasattr(self, "chart_asistencia"):
            self.chart_asistencia.set_data(weekly_data)

        # Update Hourly Peak / Traffic Chart
        hourly_traffic = metrics.get("hourly_traffic", {})
        if hasattr(self, "chart_horas_pico"):
            self.chart_horas_pico.set_data(hourly_traffic)

        # Update Habitual Members breakdown
        self._last_habits = metrics.get("member_habits", {})
        self.habitual_members_container.content = self._build_habitual_members(
            self._last_habits, self._current_habit_shift
        )

        # Update Summary Table
        self.txt_total_miembros.value = str(metrics["total_members"])
        self.txt_ocupacion.value = metrics["ocupacion"]
        self.txt_entradas_hoy.value = str(metrics.get("entries_today", 0))
        self.txt_salidas_hoy.value = str(metrics.get("exits_today", 0))
        self.txt_plan_popular.value = metrics["plan_popular"]
        self.txt_ventas_pos.value = str(metrics["total_sales"])
        self.txt_pagos_membresia.value = str(metrics.get("payments_count", 0))
        self.txt_ticket_promedio.value = f"${metrics['avg_ticket']:.2f}"
        self.txt_tasa_bcv.value = f"{bcv_rate:.2f} Bs/$"
        self.txt_ingreso_bs.value = f"Bs. {daily_income_bs:,.2f}"

        # Rebuild alert list containers with WhatsApp contact buttons
        self.morosos_container.content = self._build_alert_list("Morosos", morosos, ACCENT_DANGER)
        self.proximos_container.content = self._build_alert_list("Próximos a Vencer", proximos_vencer, ACCENT_WARNING)

    def _change_habit_shift(self, shift_key: str):
        self._current_habit_shift = shift_key
        self.habitual_members_container.content = self._build_habitual_members(
            self._last_habits, self._current_habit_shift
        )
        try:
            self.habitual_members_container.update()
        except Exception:
            pass

    def _build_habitual_members(self, habits_dict: dict, current_shift: str) -> ft.Control:
        shift_key_map = {
            "all": "all",
            "morning": "morning",
            "afternoon": "afternoon",
            "evening": "evening",
        }
        members_list = habits_dict.get(shift_key_map.get(current_shift, "all"), [])

        # Filter buttons
        filter_configs = [
            ("all", "Todos"),
            ("morning", "Mañana (6-12)"),
            ("afternoon", "Tarde (12-17)"),
            ("evening", "Noche (17-22)"),
        ]
        filter_buttons = []
        for key, lbl in filter_configs:
            is_active = (key == current_shift)
            filter_buttons.append(
                ft.Container(
                    content=ft.Text(
                        lbl,
                        size=11,
                        color=TEXT_PRIMARY if is_active else TEXT_MUTED,
                        weight="w600" if is_active else "w400",
                    ),
                    bgcolor=ACCENT_PRIMARY if is_active else BG_INPUT,
                    padding=ft.padding.symmetric(horizontal=10, vertical=5),
                    border_radius=RADIUS_SM,
                    ink=True,
                    on_click=lambda e, k=key: self._change_habit_shift(k),
                )
            )

        rows = []
        for m in members_list[:6]:
            phone_str = m.get("telefono", "")
            wa_url = get_whatsapp_url(m) if phone_str else None

            member_row_controls = [
                ft.Icon(ft.Icons.PERSON_PIN_ROUNDED, size=18, color=ACCENT_PRIMARY),
                ft.Column(
                    controls=[
                        ft.Text(m.get("nombre", ""), size=13, weight="w600", color=TEXT_PRIMARY),
                        ft.Text(
                            f"Plan: {m.get('plan', '-')} · C.I. {m.get('cedula', '')}",
                            size=10,
                            color=TEXT_MUTED,
                        ),
                    ],
                    spacing=1,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Text(f"🕒 {m.get('habitual_time', '')}", size=11, color=ACCENT_PRIMARY, weight="w600"),
                    bgcolor=BG_INPUT,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    border_radius=RADIUS_SM,
                ),
                ft.Container(
                    content=ft.Text(
                        f"{m.get('total_visits', 1)} visita{'s' if m.get('total_visits', 1) != 1 else ''}",
                        size=11,
                        color=ACCENT_SUCCESS,
                        weight="w600",
                    ),
                    bgcolor=ft.Colors.with_opacity(0.12, ACCENT_SUCCESS),
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    border_radius=RADIUS_SM,
                ),
            ]

            if wa_url:
                member_row_controls.append(
                    ft.IconButton(
                        icon=ft.Icons.CHAT,
                        icon_size=16,
                        icon_color="#25D366",
                        tooltip=f"WhatsApp ({phone_str})",
                        url=wa_url,
                        on_click=lambda e, mem=m: self._launch_whatsapp(mem),
                    )
                )

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=member_row_controls,
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(vertical=4),
                )
            )

        if not rows:
            content_list = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=TEXT_MUTED),
                        ft.Text("Sin asistencias registradas en este turno", size=12, color=TEXT_MUTED),
                    ],
                    spacing=8,
                ),
                padding=ft.padding.symmetric(vertical=12),
            )
        else:
            content_list = ft.Column(controls=rows, spacing=4)

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.GROUPS_OUTLINED, size=18, color=ACCENT_PRIMARY),
                                heading_text("Socios Habituales por Horario", size=FONT_SIZE_MD),
                            ],
                            spacing=8,
                        ),
                        ft.Container(
                            content=ft.Text(f"{len(members_list)} socios", size=11, color=ACCENT_PRIMARY, weight="w600"),
                            bgcolor=ft.Colors.with_opacity(0.12, ACCENT_PRIMARY),
                            padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            border_radius=12,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(
                    "Mide a qué horas van normalmente y quiénes son los más asiduos",
                    size=11,
                    color=TEXT_MUTED,
                ),
                ft.Row(controls=filter_buttons, spacing=6, wrap=True),
                ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=2, bottom=4)),
                content_list,
            ],
            spacing=6,
        )

    def _build_alert_list(self, title: str, members: list, color: str) -> ft.Control:
        if not members:
            return ft.Column(
                controls=[
                    heading_text(title, size=16, color=color),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=18, color=ACCENT_SUCCESS),
                                ft.Text("No hay socios en esta categoría", color=TEXT_MUTED, size=13),
                            ],
                            spacing=8,
                        ),
                        padding=ft.padding.symmetric(vertical=10),
                    ),
                ],
                spacing=6,
            )

        rows = []
        for m in members[:6]:
            phone_str = m.get("telefono", "")
            wa_url = get_whatsapp_url(m) if phone_str else None

            row_controls = [
                ft.Icon(ft.Icons.PERSON, size=16, color=color),
                ft.Column(
                    controls=[
                        ft.Text(m.get("nombre", ""), color=TEXT_PRIMARY, size=13, weight="w600"),
                        ft.Text(
                            f"📞 {phone_str}" if phone_str else "Sin teléfono",
                            size=10,
                            color=TEXT_MUTED,
                        ),
                    ],
                    spacing=1,
                    expand=True,
                ),
                ft.Container(
                    content=ft.Text(f"Vence: {m.get('vencimiento', '')}", size=11, color=color, weight="w500"),
                    bgcolor=BG_INPUT,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    border_radius=RADIUS_SM,
                ),
            ]

            if wa_url:
                row_controls.append(
                    ft.IconButton(
                        icon=ft.Icons.CHAT,
                        icon_size=16,
                        icon_color="#25D366",
                        tooltip=f"Enviar recordatorio por WhatsApp ({phone_str})",
                        url=wa_url,
                        on_click=lambda e, mem=m: self._launch_whatsapp(mem),
                    )
                )

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=row_controls,
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(vertical=4),
                )
            )

        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        heading_text(title, size=16, color=color),
                        ft.Container(
                            content=ft.Text(str(len(members)), size=11, color=color, weight="w700"),
                            bgcolor=ft.Colors.with_opacity(0.15, color),
                            padding=ft.padding.symmetric(horizontal=8, vertical=2),
                            border_radius=12,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(height=4),
                ft.Column(controls=rows, spacing=4),
            ],
            spacing=4,
        )

    def _launch_whatsapp(self, member: dict):
        """Open WhatsApp web / mobile link with pre-filled renewal reminder message."""
        url = get_whatsapp_url(member)
        if url and hasattr(self, "page") and self.page:
            try:
                if hasattr(self.page, "launch_url"):
                    self.page.launch_url(url, web_popup_window_name="_blank")
            except Exception as ex:
                print(f"[DashboardView] Error launching WhatsApp: {ex}")

    def _summary_row(self, label: str, value_control: ft.Control):
        return ft.Row(
            controls=[
                label_text(label),
                ft.Container(expand=True),
                value_control,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def _open_modal(self, dialog: ft.AlertDialog):
        self._current_dialog = dialog
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "open"):
                try:
                    self.page.open(dialog)
                    return
                except Exception:
                    pass
            if hasattr(self.page, "show_dialog"):
                try:
                    self.page.show_dialog(dialog)
                    return
                except Exception:
                    pass
            self.page.dialog = dialog
            dialog.open = True
            try:
                self.page.update()
            except Exception:
                pass

    def _close_modal(self, dialog: Optional[ft.AlertDialog] = None):
        target = dialog or getattr(self, "_current_dialog", None)
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "close"):
                try:
                    self.page.close(target)
                    return
                except Exception:
                    pass
            if hasattr(self.page, "pop_dialog"):
                try:
                    self.page.pop_dialog()
                    return
                except Exception:
                    pass
            if target:
                target.open = False
            elif getattr(self.page, "dialog", None):
                self.page.dialog.open = False
            try:
                self.page.update()
            except Exception:
                pass

    def _show_entrenando_modal(self):
        entrenando_members = [m for m in MEMBERS if m.get("entrenando")]

        items = []
        for m in entrenando_members:
            cedula = m.get("cedula", "")
            nombre = m.get("nombre", "Socio")
            plan = m.get("plan", "-")
            phone = m.get("telefono", "")

            entry_event = next(
                (e for e in ACCESS_LOG if (e.get("cedula") == cedula or e.get("nombre") == nombre) and e.get("status") in ("ENTRADA", "PERMITIDO")),
                None,
            )
            hora_str = entry_event.get("hora", "Hoy") if entry_event else "En sala"

            actions_row = []
            if phone:
                actions_row.append(
                    ft.IconButton(
                        icon=ft.Icons.CHAT,
                        icon_color="#25D366",
                        icon_size=18,
                        tooltip=f"WhatsApp ({phone})",
                        on_click=lambda e, mem=m: self._launch_whatsapp(mem),
                    )
                )

            def _checkout_member(e, mem=m):
                try:
                    register_access_attempt(mem.get("cedula"), mem, allowed=True, action="SALIDA")
                except Exception as ex:
                    print(f"[Dashboard] Error registrando salida: {ex}")
                self._close_modal()
                self.refresh_dashboard()

            actions_row.append(
                ft.TextButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LOGOUT, size=14, color=ACCENT_DANGER),
                            ft.Text("Marcar Salida", size=11, color=ACCENT_DANGER, weight="w600"),
                        ],
                        spacing=4,
                    ),
                    tooltip="Registrar salida de sala",
                    on_click=_checkout_member,
                )
            )

            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Icon(ft.Icons.DIRECTIONS_RUN, color=ACCENT_SUCCESS, size=20),
                                bgcolor=ft.Colors.with_opacity(0.12, ACCENT_SUCCESS),
                                border_radius=RADIUS_SM,
                                padding=8,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(nombre, size=13, weight="w600", color=TEXT_PRIMARY),
                                    ft.Row(
                                        controls=[
                                            ft.Text(f"C.I. {cedula}", size=11, color=TEXT_MUTED),
                                            ft.Text("·", size=11, color=TEXT_MUTED),
                                            ft.Text(f"Plan: {plan}", size=11, color=ACCENT_PRIMARY, weight="w500"),
                                        ],
                                        spacing=4,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.ACCESS_TIME, size=12, color=ACCENT_SUCCESS),
                                        ft.Text(f"Entrada: {hora_str}", size=11, color=ACCENT_SUCCESS, weight="w600"),
                                    ],
                                    spacing=4,
                                ),
                                bgcolor=BG_INPUT,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=RADIUS_SM,
                            ),
                            ft.Row(controls=actions_row, spacing=2),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=BG_INPUT,
                    border=ft.Border.all(1, BORDER),
                    border_radius=RADIUS_SM,
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                )
            )

        if not items:
            list_content = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.DIRECTIONS_WALK, size=40, color=TEXT_MUTED),
                        ft.Text("No hay socios entrenando en este momento", size=14, color=TEXT_PRIMARY, weight="w600"),
                        ft.Text("Los socios aparecerán aquí tan pronto registren su entrada en el quiosco o lector NFC.", size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.padding.symmetric(vertical=40, horizontal=20),
                alignment=ft.Alignment(0, 0),
            )
        else:
            list_content = ft.Column(
                controls=items,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.DIRECTIONS_RUN, color=ACCENT_SUCCESS, size=24),
                    heading_text("Socios Entrenando Ahora", size=FONT_SIZE_MD),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(f"{len(entrenando_members)} en sala", size=11, color=ACCENT_SUCCESS, weight="w700"),
                        bgcolor=ft.Colors.with_opacity(0.15, ACCENT_SUCCESS),
                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                        border_radius=12,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Listado de miembros activos dentro del gimnasio en tiempo real.", size=12, color=TEXT_MUTED),
                        ft.Container(height=4),
                        ft.Container(
                            content=list_content,
                            height=360,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                width=560,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda _: self._close_modal(dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )
        self._open_modal(dialog)

    def _show_proximos_modal(self):
        today = datetime.now().date()
        proximos = []
        for m in MEMBERS:
            if m.get("estado") != "Activo":
                continue
            venc_str = m.get("vencimiento", "")
            if not venc_str:
                continue
            try:
                venc_date = _parse_date(venc_str)
                days_left = (venc_date - today).days
                if 0 <= days_left <= 7:
                    proximos.append((days_left, venc_date, m))
            except Exception:
                continue
        proximos.sort(key=lambda x: x[0])

        items = []
        for days_left, venc_date, m in proximos:
            cedula = m.get("cedula", "")
            nombre = m.get("nombre", "Socio")
            plan = m.get("plan", "-")
            phone = m.get("telefono", "")

            if days_left == 0:
                badge_text = "¡Vence Hoy!"
                badge_color = ACCENT_DANGER
            elif days_left == 1:
                badge_text = "Vence Mañana"
                badge_color = ACCENT_WARNING
            else:
                badge_text = f"En {days_left} días"
                badge_color = ACCENT_WARNING

            actions_row = []
            if phone:
                actions_row.append(
                    ft.ElevatedButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CHAT, size=14, color=TEXT_PRIMARY),
                                ft.Text("Recordar", size=11, color=TEXT_PRIMARY, weight="w600"),
                            ],
                            spacing=4,
                        ),
                        bgcolor="#25D366",
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                        tooltip=f"Enviar aviso de renovación por WhatsApp ({phone})",
                        on_click=lambda e, mem=m: self._launch_whatsapp(mem),
                    )
                )

            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Icon(ft.Icons.EVENT_NOTE, color=ACCENT_WARNING, size=20),
                                bgcolor=ft.Colors.with_opacity(0.12, ACCENT_WARNING),
                                border_radius=RADIUS_SM,
                                padding=8,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(nombre, size=13, weight="w600", color=TEXT_PRIMARY),
                                    ft.Row(
                                        controls=[
                                            ft.Text(f"C.I. {cedula}", size=11, color=TEXT_MUTED),
                                            ft.Text("·", size=11, color=TEXT_MUTED),
                                            ft.Text(f"Plan: {plan}", size=11, color=ACCENT_PRIMARY, weight="w500"),
                                            ft.Text("·", size=11, color=TEXT_MUTED),
                                            ft.Text(f"📞 {phone}" if phone else "Sin teléfono", size=11, color=TEXT_MUTED),
                                        ],
                                        spacing=4,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Text(badge_text, size=11, color=badge_color, weight="w700"),
                                        ft.Text(f"Vence: {m.get('vencimiento')}", size=10, color=TEXT_MUTED),
                                    ],
                                    spacing=1,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                ),
                                bgcolor=BG_INPUT,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=RADIUS_SM,
                            ),
                            ft.Row(controls=actions_row, spacing=2),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=BG_INPUT,
                    border=ft.Border.all(1, BORDER),
                    border_radius=RADIUS_SM,
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                )
            )

        if not items:
            list_content = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=40, color=ACCENT_SUCCESS),
                        ft.Text("No hay socios próximos a vencer en los próximos 7 días", size=13, color=TEXT_PRIMARY, weight="w600"),
                        ft.Text("Todas las membresías activas tienen más de una semana de vigencia.", size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.padding.symmetric(vertical=40, horizontal=20),
                alignment=ft.Alignment(0, 0),
            )
        else:
            list_content = ft.Column(
                controls=items,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.EVENT_NOTE, color=ACCENT_WARNING, size=24),
                    heading_text("Socios Próximos a Vencer (7 Días)", size=FONT_SIZE_MD),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(f"{len(proximos)} socios", size=11, color=ACCENT_WARNING, weight="w700"),
                        bgcolor=ft.Colors.with_opacity(0.15, ACCENT_WARNING),
                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                        border_radius=12,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Miembros cuya membresía vence en los próximos 7 días. Puedes contactarlos vía WhatsApp.", size=12, color=TEXT_MUTED),
                        ft.Container(height=4),
                        ft.Container(
                            content=list_content,
                            height=360,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                width=580,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda _: self._close_modal(dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )
        self._open_modal(dialog)

    def _show_morosos_modal(self):
        today = datetime.now().date()
        morosos_list = []
        for m in MEMBERS:
            if m.get("estado") == "Moroso":
                venc_str = m.get("vencimiento", "")
                days_overdue = 0
                if venc_str:
                    try:
                        days_overdue = (today - _parse_date(venc_str)).days
                    except Exception:
                        pass
                morosos_list.append((days_overdue, m))
        morosos_list.sort(key=lambda x: x[0], reverse=True)

        items = []
        for days_overdue, m in morosos_list:
            cedula = m.get("cedula", "")
            nombre = m.get("nombre", "Socio")
            plan = m.get("plan", "-")
            phone = m.get("telefono", "")

            actions_row = []
            if phone:
                actions_row.append(
                    ft.ElevatedButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CHAT, size=14, color=TEXT_PRIMARY),
                                ft.Text("Cobrar", size=11, color=TEXT_PRIMARY, weight="w600"),
                            ],
                            spacing=4,
                        ),
                        bgcolor="#25D366",
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                        tooltip=f"Cobrar membresía por WhatsApp ({phone})",
                        on_click=lambda e, mem=m: self._launch_whatsapp(mem),
                    )
                )

            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Icon(ft.Icons.PERSON_OFF, color=ACCENT_DANGER, size=20),
                                bgcolor=ft.Colors.with_opacity(0.12, ACCENT_DANGER),
                                border_radius=RADIUS_SM,
                                padding=8,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(nombre, size=13, weight="w600", color=TEXT_PRIMARY),
                                    ft.Row(
                                        controls=[
                                            ft.Text(f"C.I. {cedula}", size=11, color=TEXT_MUTED),
                                            ft.Text("·", size=11, color=TEXT_MUTED),
                                            ft.Text(f"Plan: {plan}", size=11, color=ACCENT_DANGER, weight="w500"),
                                            ft.Text("·", size=11, color=TEXT_MUTED),
                                            ft.Text(f"📞 {phone}" if phone else "Sin teléfono", size=11, color=TEXT_MUTED),
                                        ],
                                        spacing=4,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Text(f"Vencido hace {days_overdue}d" if days_overdue > 0 else "Vencido", size=11, color=ACCENT_DANGER, weight="w700"),
                                        ft.Text(f"Vence: {m.get('vencimiento', '-')}", size=10, color=TEXT_MUTED),
                                    ],
                                    spacing=1,
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                ),
                                bgcolor=BG_INPUT,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=RADIUS_SM,
                            ),
                            ft.Row(controls=actions_row, spacing=2),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=BG_INPUT,
                    border=ft.Border.all(1, BORDER),
                    border_radius=RADIUS_SM,
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                )
            )

        if not items:
            list_content = ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=40, color=ACCENT_SUCCESS),
                        ft.Text("¡Excelente! No hay socios morosos", size=14, color=TEXT_PRIMARY, weight="w600"),
                        ft.Text("Todos los clientes están al día con sus pagos.", size=12, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.padding.symmetric(vertical=40, horizontal=20),
                alignment=ft.Alignment(0, 0),
            )
        else:
            list_content = ft.Column(
                controls=items,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.PERSON_OFF, color=ACCENT_DANGER, size=24),
                    heading_text("Listado de Socios Morosos", size=FONT_SIZE_MD),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(f"{len(morosos_list)} morosos", size=11, color=ACCENT_DANGER, weight="w700"),
                        bgcolor=ft.Colors.with_opacity(0.15, ACCENT_DANGER),
                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                        border_radius=12,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Clientes con membresía vencida que tienen bloqueado el acceso al gimnasio.", size=12, color=TEXT_MUTED),
                        ft.Container(height=4),
                        ft.Container(
                            content=list_content,
                            height=360,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                ),
                width=580,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda _: self._close_modal(dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )
        self._open_modal(dialog)

    def _show_ingresos_modal(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        bcv_rate = bcv_service.get_rate()

        # 1. Membership payments today
        try:
            all_payments = load_membership_payments(limit=500)
        except Exception:
            all_payments = []
        payments_today = [p for p in all_payments if str(p.get("fecha_pago", "")).startswith(today_str)]
        payments_total_usd = sum(float(p.get("monto", 0.0)) for p in payments_today)
        payments_total_bs = bcv_service.to_bs(payments_total_usd)

        # 2. POS sales today
        pos_sales_today = list(reversed(DAILY_SALES))
        pos_total_usd = sum(float(s.get("monto", 0.0)) for s in pos_sales_today)
        pos_total_bs = bcv_service.to_bs(pos_total_usd)

        grand_total_usd = payments_total_usd + pos_total_usd
        grand_total_bs = payments_total_bs + pos_total_bs

        filter_state = {"filter": "all"}
        list_container = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)

        def _render_list():
            current_filter = filter_state["filter"]
            rows = []

            if current_filter in ("all", "memberships"):
                for p in payments_today:
                    monto_val = float(p.get("monto", 0.0))
                    monto_bs_val = float(p.get("monto_bs", 0.0)) or bcv_service.to_bs(monto_val)
                    fecha_pago_str = str(p.get("fecha_pago", ""))
                    hora_pago = fecha_pago_str.split()[1] if " " in fecha_pago_str else fecha_pago_str
                    ref_str = p.get("referencia", "")

                    rows.append({
                        "type": "membership",
                        "time": hora_pago,
                        "title": f"{p.get('nombre', 'Socio')} (C.I. {p.get('cedula', '')})",
                        "subtitle": f"Plan: {p.get('plan', '-')} · Método: {p.get('metodo', 'Efectivo')}" + (f" · Ref: {ref_str}" if ref_str else ""),
                        "usd": monto_val,
                        "bs": monto_bs_val,
                    })

            if current_filter in ("all", "pos"):
                for s in pos_sales_today:
                    monto_val = float(s.get("monto", 0.0))
                    monto_bs_val = bcv_service.to_bs(monto_val)
                    rows.append({
                        "type": "pos",
                        "time": s.get("hora", ""),
                        "title": s.get("producto", "Venta Cantina"),
                        "subtitle": f"Cantina / Punto de Venta · Hora: {s.get('hora', '')}",
                        "usd": monto_val,
                        "bs": monto_bs_val,
                    })

            if not rows:
                list_container.controls = [
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Icon(ft.Icons.RECEIPT_LONG_OUTLINED, size=36, color=TEXT_MUTED),
                                ft.Text("No hay transacciones registradas en esta categoría hoy", size=13, color=TEXT_MUTED),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            spacing=6,
                        ),
                        padding=ft.padding.symmetric(vertical=40),
                        alignment=ft.Alignment(0, 0),
                    )
                ]
            else:
                card_items = []
                for r in rows:
                    is_mem = (r["type"] == "membership")
                    icon = ft.Icons.CARD_MEMBERSHIP if is_mem else ft.Icons.POINT_OF_SALE
                    accent = ACCENT_SUCCESS if is_mem else ft.Colors.CYAN_ACCENT
                    tag_lbl = "MEMBRESÍA" if is_mem else "CANTINA"

                    card_items.append(
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Container(
                                        content=ft.Icon(icon, color=accent, size=18),
                                        bgcolor=ft.Colors.with_opacity(0.12, accent),
                                        border_radius=RADIUS_SM,
                                        padding=8,
                                    ),
                                    ft.Column(
                                        controls=[
                                            ft.Row(
                                                controls=[
                                                    ft.Text(r["title"], size=13, weight="w600", color=TEXT_PRIMARY),
                                                    ft.Container(
                                                        content=ft.Text(tag_lbl, size=9, color=accent, weight="w700"),
                                                        bgcolor=ft.Colors.with_opacity(0.12, accent),
                                                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                                        border_radius=4,
                                                    ),
                                                ],
                                                spacing=6,
                                                wrap=True,
                                            ),
                                            ft.Text(r["subtitle"], size=11, color=TEXT_MUTED),
                                        ],
                                        spacing=2,
                                        expand=True,
                                    ),
                                    ft.Column(
                                        controls=[
                                            ft.Text(f"+${r['usd']:.2f}", size=13, color=ACCENT_SUCCESS, weight="w700"),
                                            ft.Text(f"Bs. {r['bs']:,.2f}", size=10, color=TEXT_MUTED),
                                        ],
                                        spacing=1,
                                        horizontal_alignment=ft.CrossAxisAlignment.END,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            bgcolor=BG_INPUT,
                            border=ft.Border.all(1, BORDER),
                            border_radius=RADIUS_SM,
                            padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        )
                    )
                list_container.controls = card_items

        _render_list()

        chip_all = ft.Container(
            content=ft.Text(f"Todos (${grand_total_usd:.2f})", size=11, color=TEXT_PRIMARY, weight="w600"),
            bgcolor=ACCENT_PRIMARY,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border_radius=RADIUS_SM,
            ink=True,
        )
        chip_memberships = ft.Container(
            content=ft.Text(f"💳 Membresías (${payments_total_usd:.2f} · {len(payments_today)})", size=11, color=TEXT_MUTED, weight="w500"),
            bgcolor=BG_INPUT,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border_radius=RADIUS_SM,
            ink=True,
        )
        chip_pos = ft.Container(
            content=ft.Text(f"🛒 Cantina / POS (${pos_total_usd:.2f} · {len(pos_sales_today)})", size=11, color=TEXT_MUTED, weight="w500"),
            bgcolor=BG_INPUT,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border_radius=RADIUS_SM,
            ink=True,
        )

        chips_row = ft.Row(
            controls=[chip_all, chip_memberships, chip_pos],
            spacing=8,
            wrap=True,
        )

        def _set_filter(f_name: str):
            filter_state["filter"] = f_name
            chip_all.bgcolor = ACCENT_PRIMARY if f_name == "all" else BG_INPUT
            chip_all.content.color = TEXT_PRIMARY if f_name == "all" else TEXT_MUTED
            chip_all.content.weight = "w600" if f_name == "all" else "w500"

            chip_memberships.bgcolor = ACCENT_PRIMARY if f_name == "memberships" else BG_INPUT
            chip_memberships.content.color = TEXT_PRIMARY if f_name == "memberships" else TEXT_MUTED
            chip_memberships.content.weight = "w600" if f_name == "memberships" else "w500"

            chip_pos.bgcolor = ACCENT_PRIMARY if f_name == "pos" else BG_INPUT
            chip_pos.content.color = TEXT_PRIMARY if f_name == "pos" else TEXT_MUTED
            chip_pos.content.weight = "w600" if f_name == "pos" else "w500"

            _render_list()
            try:
                chips_row.update()
                list_container.update()
            except Exception:
                pass

        chip_all.on_click = lambda _: _set_filter("all")
        chip_memberships.on_click = lambda _: _set_filter("memberships")
        chip_pos.on_click = lambda _: _set_filter("pos")

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.ACCOUNT_BALANCE_WALLET, color=ACCENT_PRIMARY, size=24),
                    heading_text("Desglose de Ingresos del Día", size=FONT_SIZE_MD),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(f"${grand_total_usd:.2f} USD", size=12, color=ACCENT_PRIMARY, weight="w700"),
                        bgcolor=ft.Colors.with_opacity(0.15, ACCENT_PRIMARY),
                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                        border_radius=12,
                    ),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Column(
                                        controls=[
                                            ft.Text("Total Hoy (USD)", size=10, color=TEXT_MUTED),
                                            ft.Text(f"${grand_total_usd:.2f}", size=14, color=ACCENT_SUCCESS, weight="w700"),
                                        ],
                                        spacing=1,
                                    ),
                                    ft.Container(width=1, height=28, bgcolor=BORDER),
                                    ft.Column(
                                        controls=[
                                            ft.Text("Total Hoy (Bs.)", size=10, color=TEXT_MUTED),
                                            ft.Text(f"Bs. {grand_total_bs:,.2f}", size=14, color=TEXT_PRIMARY, weight="w700"),
                                        ],
                                        spacing=1,
                                    ),
                                    ft.Container(width=1, height=28, bgcolor=BORDER),
                                    ft.Column(
                                        controls=[
                                            ft.Text("Tasa Oficial BCV", size=10, color=TEXT_MUTED),
                                            ft.Text(f"{bcv_rate:.2f} Bs/$", size=13, color=ACCENT_PRIMARY, weight="w600"),
                                        ],
                                        spacing=1,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                            ),
                            bgcolor=BG_INPUT,
                            border=ft.Border.all(1, BORDER),
                            border_radius=RADIUS_SM,
                            padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        ),
                        chips_row,
                        ft.Container(height=2),
                        ft.Container(
                            content=list_container,
                            height=330,
                        ),
                    ],
                    spacing=8,
                    tight=True,
                ),
                width=600,
            ),
            actions=[
                ft.TextButton("Cerrar", on_click=lambda _: self._close_modal(dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )
        self._open_modal(dialog)
