"""Dashboard view — tactical real-time overview for the gym manager.
Reactively updates in real time on NFC scans, sales, membership payments and BCV rate changes.
"""

from __future__ import annotations

import flet as ft
from core.theme import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_WARNING, ACCENT_DANGER,
    FONT_SIZE_MD, FONT_SIZE_SM, BG_CARD, BG_INPUT, BORDER, RADIUS_MD, RADIUS_SM,
    card_style, heading_text, label_text,
)
from core.mock_data import MEMBERS, WEEKLY_ATTENDANCE
from core.business import get_dashboard_metrics
from core.bcv_service import bcv_service
from core.event_bus import event_bus
from ui.components.widgets import MetricCard, BarChartSim


class DashboardView(ft.Column):
    """Dashboard with real-time reactive metric cards, currency conversions, and attendance insights."""

    def __init__(self):
        super().__init__(spacing=14, expand=True, scroll=ft.ScrollMode.AUTO)

        # 1. Top KPI Metric Cards
        self.card_entrenando = MetricCard(
            icon=ft.Icons.DIRECTIONS_RUN,
            icon_color=ACCENT_SUCCESS,
            value="0",
            label="Entrenando Ahora",
        )
        self.card_proximos = MetricCard(
            icon=ft.Icons.EVENT_NOTE,
            icon_color=ACCENT_WARNING,
            value="0",
            label="Próx. a Vencer (7d)",
        )
        self.card_morosos = MetricCard(
            icon=ft.Icons.PERSON_OFF,
            icon_color=ACCENT_DANGER,
            value="0",
            label="Morosos",
        )
        self.card_ingresos = MetricCard(
            icon=ft.Icons.ACCOUNT_BALANCE_WALLET,
            icon_color=ACCENT_PRIMARY,
            value="$0.00",
            label="Ingresos del Día",
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

        # 3. Dynamic alert list containers
        self.morosos_container = ft.Container(expand=True, **card_style())
        self.proximos_container = ft.Container(expand=True, **card_style())

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
                    BarChartSim(WEEKLY_ATTENDANCE),
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

    def _on_event(self, data=None):
        self.refresh_dashboard()

    def refresh_dashboard(self):
        """Recompute all metrics and perform a thread-safe UI update."""
        self._calculate_and_apply_metrics()
        if hasattr(self, "page") and self.page:
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

        # Rebuild alert list containers
        self.morosos_container.content = self._build_alert_list("Morosos", morosos, ACCENT_DANGER)
        self.proximos_container.content = self._build_alert_list("Próximos a Vencer", proximos_vencer, ACCENT_WARNING)

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
            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.PERSON, size=16, color=color),
                            ft.Text(m.get("nombre", ""), color=TEXT_PRIMARY, size=13, weight="w600", expand=True),
                            ft.Container(
                                content=ft.Text(f"Vence: {m.get('vencimiento', '')}", size=11, color=color, weight="w500"),
                                bgcolor=BG_INPUT,
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                border_radius=RADIUS_SM,
                            ),
                        ],
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

    def _summary_row(self, label: str, value_control: ft.Control):
        return ft.Row(
            controls=[
                label_text(label),
                ft.Container(expand=True),
                value_control,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
