"""Dashboard view — tactical overview for the manager."""

import flet as ft
from core.theme import (
    BG_CARD, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_WARNING, ACCENT_DANGER,
    FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_XS, RADIUS_SM,
    card_style, heading_text, label_text,
)
from core.business import get_dashboard_metrics, run_auto_expiration, get_expiry_notifications
from ui.components.widgets import MetricCard, BarChartSim


class DashboardView(ft.Column):
    def __init__(self):
        self._running = False
        super().__init__(controls=[], spacing=8, expand=True, scroll=ft.ScrollMode.AUTO)
        run_auto_expiration()
        self._rebuild()

    def did_mount(self):
        self._running = True
        if self.page:
            self.page.run_task(self._auto_refresh)

    def will_unmount(self):
        self._running = False

    async def _auto_refresh(self):
        import asyncio
        while self._running:
            try:
                run_auto_expiration()
                self._rebuild()
                self.update()
            except Exception:
                self._running = False
                break
            await asyncio.sleep(5)

    def _rebuild(self):
        m = get_dashboard_metrics()
        notifs = get_expiry_notifications()
        morosos = m["morosos"]
        proximos = m["proximos_vencer"]

        c = [heading_text("Dashboard"), ft.Container(height=8)]

        if notifs:
            nr = []
            for n in notifs[:8]:
                d = n.get("days_left", 0)
                uc = ACCENT_DANGER if d <= 2 else ACCENT_WARNING
                nr.append(ft.Row(controls=[
                    ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, size=14, color=uc),
                    ft.Text(n["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY),
                    ft.Container(expand=True),
                    ft.Container(
                        content=ft.Text(f"{d}d" if d > 0 else "HOY", size=FONT_SIZE_XS, color=TEXT_PRIMARY, weight="w700"),
                        bgcolor=uc, padding=ft.padding.symmetric(horizontal=6, vertical=2), border_radius=RADIUS_SM,
                    ),
                ], spacing=6))
            c.append(ft.Container(
                content=ft.Column(controls=[
                    ft.Text(f"⚠ {len(notifs)} membresias por vencer", size=FONT_SIZE_MD, color=ACCENT_WARNING, weight="w600"),
                    *nr,
                ], spacing=4),
                bgcolor=BG_CARD, border=ft.border.all(1, ACCENT_WARNING), border_radius=RADIUS_SM, padding=14,
            ))

        c.append(ft.Row(controls=[
            MetricCard(ft.Icons.DIRECTIONS_RUN, ACCENT_SUCCESS, str(m["entrenando"]), "Entrenando"),
            MetricCard(ft.Icons.EVENT_NOTE, ACCENT_WARNING, str(len(proximos)), "Prox. Vencer"),
            MetricCard(ft.Icons.PERSON_OFF, ACCENT_DANGER, str(len(morosos)), "Morosos"),
            MetricCard(ft.Icons.ACCOUNT_BALANCE_WALLET, ACCENT_PRIMARY, f"${m['daily_income']:.2f}", "Ingresos"),
        ], spacing=16))

        c.append(ft.Container(height=16))
        c.append(ft.Row(controls=[
            BarChartSim(m["weekly_attendance"]),
            ft.Container(content=ft.Column(controls=[
                heading_text("Resumen", size=FONT_SIZE_MD),
                self._sr("Miembros", str(m["total_members"])),
                self._sr("Ocupacion", m["ocupacion"]),
                self._sr("Plan Popular", m["plan_popular"]),
                self._sr("Ventas", str(m["total_sales"])),
                self._sr("Ticket Prom.", f"${m['avg_ticket']:.2f}"),
                self._sr("Acceso OK", f"{m['access_success_rate']:.1f}%"),
            ], spacing=8), expand=True, **card_style()),
        ], spacing=16, expand=True))

        c.append(ft.Container(height=16))
        c.append(ft.Row(controls=[
            self._al("Morosos", morosos, ACCENT_DANGER),
            self._al("Prox. Vencer", proximos, ACCENT_WARNING),
        ], spacing=16, expand=True))

        self.controls = c

    def _al(self, t, members, color):
        if not members:
            return ft.Container(content=ft.Column(controls=[
                heading_text(t, size=16, color=color),
                ft.Text("Sin registros", color=TEXT_MUTED, size=13),
            ], spacing=6), expand=True, **card_style())
        rows = [ft.Row(controls=[
            ft.Text(x["nombre"], color=color, size=14, weight="w600"),
            ft.Container(expand=True),
            ft.Text(x["vencimiento"], color=TEXT_SECONDARY, size=13),
        ]) for x in members[:10]]
        return ft.Container(content=ft.Column(
            controls=[heading_text(t, size=16, color=color)] + rows, spacing=6,
        ), expand=True, **card_style())

    def _sr(self, label, value):
        return ft.Row(controls=[
            label_text(label), ft.Container(expand=True),
            ft.Text(value, size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600"),
        ])
