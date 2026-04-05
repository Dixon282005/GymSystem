"""Reusable UI components."""

import flet as ft
from core.theme import (
    BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_DANGER, ACCENT_SUCCESS,
    RADIUS_SM, PADDING_MD,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_XL,
    card_style,
)


class MetricCard(ft.Container):
    """Metric card with icon, value, label, and accent color."""

    def __init__(self, icon, icon_color, value, label, icon_data=None):
        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(icon, color=icon_color, size=22),
                            ft.Container(expand=True),
                        ],
                    ),
                    ft.Text(value, size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w700"),
                    ft.Text(label, size=FONT_SIZE_SM, color=TEXT_SECONDARY, weight="w500"),
                ],
                spacing=6,
            ),
            expand=True,
            **card_style(),
        )


class SidebarItem(ft.Container):
    """Sidebar navigation item with icon and label."""

    def __init__(self, icon, label, on_click=None, active=False):
        self.label_text = label
        self.icon_ref = icon
        super().__init__(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=ACCENT_PRIMARY if active else TEXT_SECONDARY, size=20),
                    ft.Text(
                        label,
                        size=FONT_SIZE_SM,
                        color=ACCENT_PRIMARY if active else TEXT_SECONDARY,
                        weight="w600" if active else "w400",
                    ),
                ],
                spacing=12,
                alignment=ft.MainAxisAlignment.START,
            ),
            on_click=on_click,
            padding=14,
            bgcolor=BG_INPUT if active else "transparent",
            border_radius=RADIUS_SM,
            ink=True,
        )

    def set_active(self, active):
        self.bgcolor = BG_INPUT if active else "transparent"
        self.content.controls[0].color = ACCENT_PRIMARY if active else TEXT_SECONDARY
        self.content.controls[1].color = ACCENT_PRIMARY if active else TEXT_SECONDARY
        self.content.controls[1].weight = "w600" if active else "w400"
        self.update()


class LiveClock(ft.Container):
    """Real-time clock display."""

    def __init__(self):
        self._running = False
        self.time_text = ft.Text("", size=FONT_SIZE_MD, color=TEXT_SECONDARY, weight="w500")
        super().__init__(
            content=self.time_text,
            padding=10,
        )
        self._set_now()

    def did_mount(self):
        self._running = True
        if self.page:
            self.page.run_task(self._run_clock)

    def will_unmount(self):
        self._running = False

    def _set_now(self):
        from datetime import datetime

        now = datetime.now()
        self.time_text.value = now.strftime("%H:%M:%S")

    async def _run_clock(self):
        import asyncio

        while self._running:
            self._set_now()
            try:
                self.time_text.update()
            except Exception:
                self._running = False
                break
            await asyncio.sleep(1)


class GlobalSearch(ft.TextField):
    """Global search bar for member lookup."""

    def __init__(self, on_search=None):
        super().__init__(
            hint_text="Buscar por cedula o nombre...",
            prefix_icon=ft.Icons.SEARCH,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=FONT_SIZE_SM,
            height=42,
            on_submit=on_search,
        )


class AccessLogCard(ft.Container):
    """Card showing a single access event."""

    def __init__(self, nombre, plan, hora, status, cedula):
        is_allowed = status == "PERMITIDO"
        badge_color = ACCENT_SUCCESS if is_allowed else ACCENT_DANGER
        badge_text = "PERMITIDO" if is_allowed else "ACCESO DENEGADO"

        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Icon(
                                    ft.Icons.ACCOUNT_CIRCLE,
                                    size=36,
                                    color=TEXT_MUTED,
                                ),
                                width=44,
                                height=44,
                                bgcolor=BG_INPUT,
                                border_radius=RADIUS_SM,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(nombre, size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600"),
                                    ft.Text(f"{plan} · {cedula}", size=FONT_SIZE_XS, color=TEXT_SECONDARY),
                                ],
                                spacing=2,
                            ),
                            ft.Container(expand=True),
                            ft.Column(
                                controls=[
                                    ft.Text(
                                        badge_text,
                                        size=FONT_SIZE_XS,
                                        color=TEXT_PRIMARY,
                                        weight="w700",
                                        bgcolor=badge_color,
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    ft.Text(hora, size=FONT_SIZE_XS, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                                ],
                                spacing=4,
                                horizontal_alignment=ft.CrossAxisAlignment.END,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                ],
                spacing=8,
            ),
            **card_style(),
        )


class BarChartSim(ft.Container):
    """Simulated bar chart for weekly attendance."""

    def __init__(self, data):
        max_val = max(d["count"] for d in data) if data else 1
        bars = []
        for d in data:
            height = max(20, int((d["count"] / max_val) * 160))
            bars.append(
                ft.Column(
                    controls=[
                        ft.Text(str(d["count"]), size=FONT_SIZE_XS, color=TEXT_SECONDARY, text_align=ft.TextAlign.CENTER),
                        ft.Container(
                            width=36,
                            height=height,
                            bgcolor=ACCENT_PRIMARY,
                            border_radius=RADIUS_SM,
                            opacity=0.85,
                        ),
                        ft.Text(d["dia"], size=FONT_SIZE_XS, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                )
            )

        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Text("Asistencia Semanal", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600"),
                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=16)),
                    ft.Row(
                        controls=bars,
                        alignment=ft.MainAxisAlignment.SPACE_AROUND,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=12,
            ),
            expand=True,
            **card_style(),
        )


class POSProductRow(ft.Container):
    """Single row for POS product selection."""

    def __init__(self, producto, on_add=None):
        self.producto = producto
        self.qty = 1
        self._on_add = on_add

        self.qty_text = ft.Text("1", size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600")

        super().__init__(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(producto["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500"),
                            ft.Text(f"Stock: {producto['stock']}", size=FONT_SIZE_XS, color=TEXT_MUTED),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    ft.Text(f"${producto['precio']:.2f}", size=FONT_SIZE_SM, color=ACCENT_PRIMARY, weight="w600"),
                    ft.IconButton(
                        ft.Icons.ADD_CIRCLE_OUTLINE,
                        icon_size=22,
                        icon_color=ACCENT_PRIMARY,
                        on_click=self._handle_add,
                        tooltip="Agregar al carrito",
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            **card_style(padding=PADDING_MD),
        )

    def _handle_add(self, e):
        if self._on_add:
            self._on_add(self.producto, self.qty)
