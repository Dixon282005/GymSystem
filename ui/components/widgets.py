"""Reusable UI components."""

import flet as ft
from core.theme import (
    BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_DANGER, ACCENT_SUCCESS, ACCENT_WARNING,
    RADIUS_SM, PADDING_MD,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_XL,
    card_style,
)

def show_snack(page, msg: str, color=None):
    """Show a standardized toast notification at the bottom overlay."""
    try:
        if color is None:
            color = "#333333"
        sb = ft.SnackBar(
            content=ft.Text(msg, color=TEXT_PRIMARY, weight="w600"),
            bgcolor=color,
        )
        if hasattr(page, "overlay"):
            page.overlay.append(sb)
        sb.open = True
        page.update()
    except Exception:
        pass


class MetricCard(ft.Container):
    """Metric card with icon, value, label, and accent color."""

    def __init__(self, icon, icon_color, value, label, icon_data=None):
        self.value_text = ft.Text(str(value), size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w700")
        self.label_text = ft.Text(str(label), size=FONT_SIZE_SM, color=TEXT_SECONDARY, weight="w500")
        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(icon, color=icon_color, size=22),
                            ft.Container(expand=True),
                        ],
                    ),
                    self.value_text,
                    self.label_text,
                ],
                spacing=6,
            ),
            expand=True,
            **card_style(),
        )

    @property
    def value(self):
        return self.value_text.value

    @value.setter
    def value(self, new_val):
        self.value_text.value = str(new_val)


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
        try:
            self.update()
        except Exception:
            pass


class LiveClock(ft.Container):
    """Real-time clock display."""

    def __init__(self):
        self._running = False
        self._clock_thread = None
        self.time_text = ft.Text("", size=FONT_SIZE_MD, color=TEXT_SECONDARY, weight="w500")
        super().__init__(
            content=self.time_text,
            padding=10,
        )
        self._set_now()

    def did_mount(self):
        import threading

        self._running = True
        self._clock_thread = threading.Thread(target=self._run_clock, daemon=True)
        self._clock_thread.start()

    def will_unmount(self):
        self._running = False

    def _set_now(self):
        from datetime import datetime

        now = datetime.now()
        self.time_text.value = now.strftime("%H:%M:%S")

    def _run_clock(self):
        import time

        while self._running:
            self._set_now()
            try:
                self.update()
            except Exception:
                self._running = False
                break
            time.sleep(1)


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
        clean_status = (status or "").upper()
        if clean_status == "SALIDA":
            badge_color = "#0891b2"
            badge_text = "SALIDA"
            card_icon = ft.Icons.DIRECTIONS_WALK
            icon_color = "#22d3ee"
        elif clean_status in ("ENTRADA", "PERMITIDO"):
            badge_color = ACCENT_SUCCESS
            badge_text = "ENTRADA"
            card_icon = ft.Icons.LOGIN
            icon_color = ACCENT_SUCCESS
        else:
            badge_color = ACCENT_DANGER
            badge_text = "DENEGADO"
            card_icon = ft.Icons.BLOCK
            icon_color = ACCENT_DANGER

        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Icon(
                                    card_icon,
                                    size=24,
                                    color=icon_color,
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
                                    ft.Container(
                                        content=ft.Text(
                                            badge_text,
                                            size=10,
                                            color=TEXT_PRIMARY,
                                            weight="w700",
                                        ),
                                        bgcolor=badge_color,
                                        padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                        border_radius=4,
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
    """Weekly unique attendance bar chart with dual metric transparency."""

    def __init__(self, data=None):
        self.bars_row = ft.Row(
            spacing=16,
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )
        self.sub_label = ft.Text(
            "Socios únicos por día (no infla por múltiples entradas del mismo socio)",
            size=11,
            color=TEXT_MUTED,
        )
        if data:
            self.set_data(data)
        else:
            self.set_data([])

        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.BAR_CHART, size=18, color=ACCENT_PRIMARY),
                            ft.Text("Asistencia Semanal Real", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600"),
                        ],
                        spacing=8,
                    ),
                    self.sub_label,
                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=4, bottom=12)),
                    self.bars_row,
                ],
                spacing=6,
            ),
            expand=True,
            **card_style(),
        )

    def set_data(self, data):
        if not data:
            data = [
                {"dia": "Lun", "count": 0, "total_scans": 0},
                {"dia": "Mar", "count": 0, "total_scans": 0},
                {"dia": "Mie", "count": 0, "total_scans": 0},
                {"dia": "Jue", "count": 0, "total_scans": 0},
                {"dia": "Vie", "count": 0, "total_scans": 0},
                {"dia": "Sab", "count": 0, "total_scans": 0},
                {"dia": "Dom", "count": 0, "total_scans": 0},
            ]
        max_val = max([d.get("count", 0) for d in data], default=1) or 1
        bars = []
        for d in data:
            cnt = d.get("count", 0)
            scans = d.get("total_scans", cnt)
            height = max(18, int((cnt / max_val) * 125)) if cnt > 0 else 6
            color = ACCENT_PRIMARY if cnt > 0 else ft.Colors.with_opacity(0.2, ACCENT_PRIMARY)
            tooltip_txt = f"{d['dia']}: {cnt} socio{'s' if cnt != 1 else ''} único{'s' if cnt != 1 else ''} ({scans} toques registrados)"
            bars.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            str(cnt),
                            size=FONT_SIZE_XS,
                            color=TEXT_PRIMARY if cnt > 0 else TEXT_MUTED,
                            text_align=ft.TextAlign.CENTER,
                            weight="w700" if cnt > 0 else "w400",
                        ),
                        ft.Container(
                            width=36,
                            height=height,
                            bgcolor=color,
                            border_radius=RADIUS_SM,
                            opacity=0.9 if cnt > 0 else 0.35,
                            tooltip=tooltip_txt,
                        ),
                        ft.Text(d["dia"], size=FONT_SIZE_XS, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6,
                )
            )
        self.bars_row.controls = bars


class HourlyPeakChart(ft.Container):
    """Hourly traffic distribution chart highlighting Peak Hours (Horas Pico) and quiet hours."""

    def __init__(self, hourly_data=None):
        self.bars_row = ft.Row(
            spacing=8,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.END,
            scroll=ft.ScrollMode.AUTO,
        )
        self.badge_peak = ft.Text("Hora Pico: --", size=11, color=ACCENT_WARNING, weight="w600")
        self.badge_quiet = ft.Text("Hora Valle: --", size=11, color=ACCENT_SUCCESS, weight="w600")
        self.badge_shift = ft.Text("Mayor Afluencia: --", size=11, color=ACCENT_PRIMARY, weight="w600")

        if hourly_data:
            self.set_data(hourly_data)
        else:
            self.set_data({})

        super().__init__(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ACCESS_TIME_FILLED, size=18, color=ACCENT_WARNING),
                            ft.Text("Afluencia y Horas Pico (6am a 10pm)", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight="w600"),
                        ],
                        spacing=8,
                    ),
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=self.badge_peak,
                                bgcolor=ft.Colors.with_opacity(0.12, ACCENT_WARNING),
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                border_radius=RADIUS_SM,
                            ),
                            ft.Container(
                                content=self.badge_quiet,
                                bgcolor=ft.Colors.with_opacity(0.12, ACCENT_SUCCESS),
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                border_radius=RADIUS_SM,
                            ),
                            ft.Container(
                                content=self.badge_shift,
                                bgcolor=ft.Colors.with_opacity(0.12, ACCENT_PRIMARY),
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                border_radius=RADIUS_SM,
                            ),
                        ],
                        wrap=True,
                        spacing=8,
                    ),
                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=4, bottom=8)),
                    ft.Container(
                        content=self.bars_row,
                        height=140,
                    ),
                ],
                spacing=8,
            ),
            expand=True,
            **card_style(),
        )

    def set_data(self, data):
        hours = data.get("hours", []) if isinstance(data, dict) else []
        peak_hr = data.get("peak_hour", "--") if isinstance(data, dict) else "--"
        peak_cnt = data.get("peak_count", 0) if isinstance(data, dict) else 0
        quiet_hr = data.get("quiet_hour", "--") if isinstance(data, dict) else "--"
        best_sh = data.get("best_shift", "--") if isinstance(data, dict) else "--"

        self.badge_peak.value = f"🔥 Hora Pico: {peak_hr} ({peak_cnt} socios)"
        self.badge_quiet.value = f"🧘 Hora Tranquila: {quiet_hr}"
        self.badge_shift.value = f"📊 Mayor Afluencia: {best_sh}"

        if not hours:
            hours = [{"hour": h, "label": f"{h%12 or 12}{'am' if h<12 else 'pm'}", "unique": 0, "total": 0} for h in range(6, 23)]

        max_val = max([h.get("unique", 0) for h in hours], default=1) or 1
        bars = []
        for h_item in hours:
            cnt = h_item.get("unique", 0)
            is_peak = (cnt == max_val and cnt > 0)
            height = max(14, int((cnt / max_val) * 85)) if cnt > 0 else 6
            color = ACCENT_WARNING if is_peak else (ACCENT_PRIMARY if cnt > 0 else ft.Colors.with_opacity(0.2, ACCENT_PRIMARY))
            tooltip_txt = f"{h_item.get('hour_range', h_item['label'])}: {cnt} socio{'s' if cnt != 1 else ''} ({h_item.get('total', cnt)} toques)"

            bars.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            str(cnt),
                            size=10,
                            color=ACCENT_WARNING if is_peak else (TEXT_PRIMARY if cnt > 0 else TEXT_MUTED),
                            weight="w700" if is_peak else "w400",
                        ),
                        ft.Container(
                            width=24,
                            height=height,
                            bgcolor=color,
                            border_radius=RADIUS_SM,
                            opacity=1.0 if is_peak else (0.85 if cnt > 0 else 0.3),
                            tooltip=tooltip_txt,
                        ),
                        ft.Text(h_item["label"], size=9, color=TEXT_MUTED),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                )
            )
        self.bars_row.controls = bars


class POSProductRow(ft.Container):
    """Single row for POS product selection and inventory CRUD."""

    def __init__(self, producto, on_add=None, on_edit=None, on_delete=None):
        self.producto = producto
        self.qty = 1
        self._on_add = on_add
        self._on_edit = on_edit
        self._on_delete = on_delete

        stock_count = int(producto.get("stock", 0))
        stock_color = ACCENT_DANGER if stock_count <= 0 else (TEXT_MUTED if stock_count > 5 else "#f59e0b")

        action_controls = []
        if on_edit:
            action_controls.append(
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED,
                    icon_size=18,
                    icon_color=TEXT_SECONDARY,
                    tooltip="Editar producto",
                    on_click=lambda e: self._on_edit(self.producto),
                )
            )
        if on_delete:
            action_controls.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_size=18,
                    icon_color=ACCENT_DANGER,
                    tooltip="Eliminar producto",
                    on_click=lambda e: self._on_delete(self.producto),
                )
            )
        if on_add:
            action_controls.append(
                ft.IconButton(
                    icon=ft.Icons.ADD_CIRCLE,
                    icon_size=22,
                    icon_color=ACCENT_PRIMARY if stock_count > 0 else TEXT_MUTED,
                    disabled=stock_count <= 0,
                    tooltip="Agregar al carrito" if stock_count > 0 else "Sin stock",
                    on_click=self._handle_add,
                )
            )

        super().__init__(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(producto["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600"),
                            ft.Text(f"Stock: {stock_count} • {producto.get('categoria', 'General')}", size=FONT_SIZE_XS, color=stock_color),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(f"${producto['precio']:.2f}", size=FONT_SIZE_SM, color=ACCENT_PRIMARY, weight="w700"),
                    ft.Row(controls=action_controls, spacing=0),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            **card_style(padding=PADDING_MD),
        )

    def _handle_add(self, e):
        if self._on_add and self.producto.get("stock", 0) > 0:
            self._on_add(self.producto, self.qty)


class BCVRateChip(ft.Container):
    """Badge container displaying the live official BCV exchange rate."""

    def __init__(self, rate: float, updated: str = ""):
        from core.theme import ACCENT_WARNING, BG_CARD, BORDER, FONT_SIZE_XS, RADIUS_SM

        rate_str = f"Bs. {rate:,.2f} / $1".replace(",", "X").replace(".", ",").replace("X", ".")
        updated_label = f" · {updated}" if updated else ""
        super().__init__(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CURRENCY_EXCHANGE, size=13, color=ACCENT_WARNING),
                    ft.Text(f"BCV {rate_str}{updated_label}", size=FONT_SIZE_XS, color=ACCENT_WARNING, weight="w600"),
                ],
                spacing=4,
                tight=True,
            ),
            bgcolor=BG_CARD,
            border_radius=RADIUS_SM,
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border=ft.border.all(1, BORDER),
        )

