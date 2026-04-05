"""Dashboard view — tactical overview for the manager."""

import flet as ft
from core.theme import (
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_WARNING, ACCENT_DANGER,
    FONT_SIZE_MD,
    card_style, heading_text, label_text,
)
from core.mock_data import MEMBERS, WEEKLY_ATTENDANCE
from core.business import get_dashboard_metrics
from ui.components.widgets import MetricCard, BarChartSim


class DashboardView(ft.Column):
    """Dashboard with metric cards and weekly attendance chart."""

    def __init__(self):
        metrics = get_dashboard_metrics()
        entrenando = metrics["entrenando"]
        morosos = metrics["morosos"]
        proximos_vencer = metrics["proximos_vencer"]

        super().__init__(
            controls=[
                heading_text("Dashboard"),
                ft.Container(height=8),
                ft.Row(
                    controls=[
                        MetricCard(
                            icon=ft.Icons.DIRECTIONS_RUN,
                            icon_color=ACCENT_SUCCESS,
                            value=str(entrenando),
                            label="Entrenando Ahora",
                        ),
                        MetricCard(
                            icon=ft.Icons.EVENT_NOTE,
                            icon_color=ACCENT_WARNING,
                            value=str(len(proximos_vencer)),
                            label="Próx. a Vencer (7d)",
                        ),
                        MetricCard(
                            icon=ft.Icons.PERSON_OFF,
                            icon_color=ACCENT_DANGER,
                            value=str(len(morosos)),
                            label="Morosos",
                        ),
                        MetricCard(
                            icon=ft.Icons.ACCOUNT_BALANCE_WALLET,
                            icon_color=ACCENT_PRIMARY,
                            value=f"${metrics['daily_income']:.2f}",
                            label="Ingresos del Dia",
                        ),
                    ],
                    spacing=16,
                ),
                ft.Container(height=20),
                ft.Row(
                    controls=[
                        BarChartSim(WEEKLY_ATTENDANCE),
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    heading_text("Resumen Rapido", size=FONT_SIZE_MD),
                                    ft.Container(height=12),
                                    self._summary_row("Total Miembros", str(len(MEMBERS))),
                                    self._summary_row("Tasa de Ocupacion", metrics["ocupacion"]),
                                    self._summary_row("Plan mas Popular", metrics["plan_popular"]),
                                    self._summary_row("Morosos", str(len(morosos))),
                                    self._summary_row("Prox. a Vencer", str(len(proximos_vencer))),
                                    self._summary_row("Ventas del Dia", str(metrics["total_sales"])),
                                    self._summary_row("Ticket Promedio", f"${metrics['avg_ticket']:.2f}"),
                                    self._summary_row("Exito de Acceso", f"{metrics['access_success_rate']:.1f}%"),
                                ],
                                spacing=12,
                            ),
                            expand=True,
                            **card_style(),
                        ),
                    ],
                    spacing=16,
                    expand=True,
                ),
                ft.Container(height=20),
                ft.Row(
                    controls=[
                        self._alert_list_section("Morosos", morosos, ACCENT_DANGER),
                        self._alert_list_section("Proximos a Vencer", proximos_vencer, ACCENT_WARNING),
                    ],
                    spacing=16,
                    expand=True,
                ),
            ],
            spacing=8,
            expand=True,
        )

    def _alert_list_section(self, title, members, color):
        if not members:
            return ft.Container(
                content=ft.Column(
                    controls=[
                        heading_text(title, size=16, color=color),
                        ft.Text("Sin registros", color=TEXT_MUTED, size=13),
                    ],
                    spacing=6,
                ),
                expand=True,
                **card_style(),
            )
        rows = [
            ft.Row(
                controls=[
                    ft.Text(m["nombre"], color=color, size=14, weight="w600"),
                    ft.Container(expand=True),
                    ft.Text(m["vencimiento"], color=TEXT_SECONDARY, size=13),
                ]
            ) for m in members
        ]
        return ft.Container(
            content=ft.Column(
                controls=[heading_text(title, size=16, color=color)] + rows,
                spacing=6,
            ),
            expand=True,
            **card_style(),
        )

    def _summary_row(self, label, value):
        return ft.Row(
            controls=[
                label_text(label),
                ft.Container(expand=True),
                ft.Text(value, size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600"),
            ],
        )
