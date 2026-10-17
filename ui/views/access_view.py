"""Live Access Feed view — real-time NFC access log with voice announcements and ACR122U reader."""

from __future__ import annotations

import flet as ft
from core.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_DANGER,
    RADIUS_SM, RADIUS_MD, PADDING_MD,
    FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    card_style, heading_text, label_text,
)
from core.mock_data import ACCESS_LOG, APP_SETTINGS
from core.business import process_nfc_scan, build_access_snapshot
from core.nfc_service import nfc_reader
from ui.components.widgets import AccessLogCard


class AccessView(ft.Column):
    """Live access feed with native ACR122U hardware listener and voice announcements."""

    def __init__(self):
        snapshot = build_access_snapshot()

        self.allowed_counter = ft.Text(str(snapshot["allowed_today"]), size=22, color=ACCENT_SUCCESS, weight="w700")
        self.denied_counter = ft.Text(str(snapshot["denied_today"]), size=22, color=ACCENT_DANGER, weight="w700")
        self.events_counter = ft.Text(str(snapshot["total_events"]), size=22, color=ACCENT_PRIMARY, weight="w700")

        # Hardware status indicator badge
        self.status_icon = ft.Icon(
            ft.Icons.NFC,
            size=18,
            color=ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER,
        )
        self.status_label = ft.Text(
            "ACR122U Conectado" if nfc_reader.is_connected else "Lector Desconectado",
            size=12,
            color=ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER,
            weight="w600",
        )
        self.reader_badge = ft.Container(
            content=ft.Row(
                controls=[self.status_icon, self.status_label],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            bgcolor=ft.Colors.with_opacity(0.12, ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER)),
            border_radius=16,
        )

        # Hero Banner for the latest scan (Visual feedback in reception)
        self.latest_scan_banner = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CONTACTLESS, size=32, color=TEXT_MUTED),
                    ft.Column(
                        controls=[
                            ft.Text("Esperando aproximación de tarjeta o llavero NFC...", size=14, color=TEXT_SECONDARY, weight="w500"),
                            ft.Text("Pase el llavero por el lector ACS ACR122U para registrar entrada", size=11, color=TEXT_MUTED),
                        ],
                        spacing=2,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=14,
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER),
            border_radius=RADIUS_MD,
            margin=ft.margin.only(bottom=8),
        )

        self.log_container = ft.Column(
            controls=[],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

        self.present_column = ft.Column(controls=[], spacing=8)
        self._refresh_present_list()

        self.filter_status = ft.Dropdown(
            label="Estado",
            value="TODOS",
            options=[
                ft.dropdown.Option("TODOS"),
                ft.dropdown.Option("ENTRADA"),
                ft.dropdown.Option("SALIDA"),
                ft.dropdown.Option("DENEGADO"),
            ],
            width=140,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            on_change=self._refresh_log_cards,
        )
        self.filter_query = ft.TextField(
            hint_text="Filtrar socio...",
            width=200,
            height=40,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            on_submit=self._refresh_log_cards,
        )

        self.sim_input = ft.TextField(
            hint_text="Escaneo manual (Cédula o UID)...",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=8,
            text_size=13,
            height=40,
            width=240,
            on_submit=self._handle_manual_scan,
        )

        self._refresh_log_cards()

        super().__init__(
            controls=[
                ft.Row(
                    controls=[
                        heading_text("Control de Acceso en Vivo"),
                        ft.Container(expand=True),
                        self.reader_badge,
                        self.filter_status,
                        self.filter_query,
                        self.sim_input,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.latest_scan_banner,
                ft.Row(
                    controls=[
                        self._counter_card("Permitidos Hoy", self.allowed_counter, ACCENT_SUCCESS),
                        self._counter_card("Denegados Hoy", self.denied_counter, ACCENT_DANGER),
                        self._counter_card("Total Eventos", self.events_counter, ACCENT_PRIMARY),
                    ],
                    spacing=12,
                ),
                ft.Container(height=4),
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            heading_text("Registro de Accesos", size=FONT_SIZE_MD),
                                            ft.Container(expand=True),
                                            ft.Text("Últimos movimientos", size=11, color=TEXT_MUTED),
                                        ],
                                    ),
                                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=4, bottom=8)),
                                    self.log_container,
                                ],
                                spacing=4,
                            ),
                            expand=2,
                            **card_style(),
                        ),
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            heading_text("En el Gimnasio", size=FONT_SIZE_MD),
                                            ft.Container(expand=True),
                                            ft.Icon(ft.Icons.FITNESS_CENTER, size=16, color=ACCENT_PRIMARY),
                                        ],
                                    ),
                                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=4, bottom=8)),
                                    self.present_column,
                                ],
                                spacing=4,
                            ),
                            expand=1,
                            **card_style(),
                        ),
                    ],
                    spacing=16,
                    expand=True,
                ),
            ],
            spacing=8,
            expand=True,
        )

        # Hook NFC service callbacks
        nfc_reader.access_callback = self._on_nfc_scan
        nfc_reader.status_callback = self._on_nfc_status_change

    def _on_nfc_status_change(self, connected: bool, message: str):
        color = ACCENT_SUCCESS if connected else ACCENT_DANGER
        self.status_icon.color = color
        self.status_label.value = "ACR122U Conectado" if connected else "Lector Desconectado"
        self.status_label.color = color
        self.reader_badge.bgcolor = ft.Colors.with_opacity(0.12, color)
        self.reader_badge.border = ft.Border.all(1, ft.Colors.with_opacity(0.3, color))
        if hasattr(self, "page") and self.page:
            try:
                self.reader_badge.update()
            except Exception:
                pass

    def did_mount(self):
        from core.event_bus import event_bus
        event_bus.subscribe("access_scan", self._on_event_bus_scan)
        event_bus.subscribe("members_changed", self._on_event_bus_members_changed)

    def will_unmount(self):
        from core.event_bus import event_bus
        event_bus.unsubscribe("access_scan", self._on_event_bus_scan)
        event_bus.unsubscribe("members_changed", self._on_event_bus_members_changed)

    def _on_event_bus_scan(self, result: dict):
        raw_id = result.get("event", {}).get("cedula", "")
        self._update_ui_with_scan_result(result, raw_id)

    def _on_event_bus_members_changed(self, member):
        self._refresh_present_list()
        self._refresh_counters()
        if hasattr(self, "page") and self.page:
            try:
                self.present_column.update()
                self.allowed_counter.update()
                self.denied_counter.update()
                self.events_counter.update()
            except Exception:
                pass

    def _on_nfc_scan(self, uid: str):
        """Dispatched from the background NFC worker thread when a tag is touched."""
        process_nfc_scan(uid)

    def _handle_manual_scan(self, e):
        raw_val = (self.sim_input.value or "").strip()
        if not raw_val:
            return
        self.sim_input.value = ""
        try:
            self.sim_input.update()
        except Exception:
            pass

        process_nfc_scan(raw_val)

    def _update_ui_with_scan_result(self, result: dict, raw_input: str):
        action = result.get("action", "ENTRADA" if result.get("allowed") else "DENEGADO")
        member = result.get("member")
        reason = result.get("reason", "")
        nombre = member["nombre"] if member else "Tarjeta No Registrada"
        first_name = nombre.split()[0] if member else "SOCIO"

        if action == "SALIDA":
            accent = "#0891b2"
            banner_icon = ft.Icons.DIRECTIONS_WALK
            status_text = f"¡HASTA LUEGO, {first_name.upper()}!"
        elif action == "ENTRADA":
            accent = ACCENT_SUCCESS
            banner_icon = ft.Icons.CHECK_CIRCLE
            status_text = f"¡BIENVENIDO, {first_name.upper()}!"
        else:
            accent = ACCENT_DANGER
            banner_icon = ft.Icons.CANCEL
            status_text = f"DENEGADO: {reason.upper()}"

        nombre = member["nombre"] if member else "Tarjeta No Registrada"
        plan = member.get("plan", "-") if member else "-"
        cedula = member.get("cedula", raw_input) if member else raw_input

        # Update Hero Banner
        self.latest_scan_banner.content = ft.Row(
            controls=[
                ft.Container(
                    content=ft.Icon(
                        banner_icon,
                        color=ft.Colors.WHITE,
                        size=28,
                    ),
                    bgcolor=accent,
                    width=48,
                    height=48,
                    border_radius=24,
                    alignment=ft.Alignment(0, 0),
                ),
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(nombre, size=16, color=TEXT_PRIMARY, weight="w700"),
                                ft.Container(
                                    content=ft.Text(status_text, size=11, color=ft.Colors.WHITE, weight="w700"),
                                    bgcolor=accent,
                                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                    border_radius=RADIUS_SM,
                                ),
                            ],
                            spacing=10,
                        ),
                        ft.Text(f"Plan: {plan} • Cédula: {cedula} • UID: {raw_input}", size=12, color=TEXT_SECONDARY),
                    ],
                    spacing=3,
                    expand=True,
                ),
            ],
            spacing=14,
            alignment=ft.MainAxisAlignment.START,
        )
        self.latest_scan_banner.border = ft.Border.all(1.5, accent)
        self.latest_scan_banner.bgcolor = ft.Colors.with_opacity(0.12, accent)

        # Refresh feed, present column and counters
        self._refresh_present_list()
        self._refresh_log_cards()
        self._refresh_counters()

        if hasattr(self, "page") and self.page:
            try:
                self.latest_scan_banner.update()
                self.present_column.update()
                self.log_container.update()
                self.allowed_counter.update()
                self.denied_counter.update()
                self.events_counter.update()
            except Exception:
                pass

    def _build_log_cards(self):
        selected_status = self.filter_status.value or "TODOS"
        query = (self.filter_query.value or "").strip().upper()

        cards = []
        for entry in ACCESS_LOG:
            status = entry.get("status", "")
            if selected_status == "ENTRADA" and status not in ("ENTRADA", "PERMITIDO"):
                continue
            elif selected_status == "SALIDA" and status != "SALIDA":
                continue
            elif selected_status == "DENEGADO" and status != "DENEGADO":
                continue
            elif selected_status not in ("TODOS", "ENTRADA", "SALIDA", "DENEGADO") and status != selected_status:
                continue

            haystack = f"{entry.get('cedula', '')} {entry.get('nombre', '')}".upper()
            if query and query not in haystack:
                continue

            cards.append(
                AccessLogCard(
                    nombre=entry.get("nombre", ""),
                    plan=entry.get("plan", ""),
                    hora=entry.get("hora", ""),
                    status=status,
                    cedula=entry.get("cedula", ""),
                )
            )

        if not cards:
            cards.append(
                ft.Container(
                    content=label_text("Sin movimientos registrados", color=TEXT_MUTED),
                    **card_style(),
                )
            )
        return cards

    def _refresh_log_cards(self, e=None):
        self.log_container.controls = self._build_log_cards()
        if e is not None and hasattr(self, "page") and self.page:
            try:
                self.log_container.update()
            except Exception:
                pass

    def _build_present_list(self):
        present = build_access_snapshot()["present"]
        items = []
        for m in present:
            items.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.PERSON, size=16, color=ACCENT_SUCCESS),
                            ft.Text(m["nombre"], size=13, color=TEXT_PRIMARY, weight="w500", expand=True),
                            ft.Container(
                                content=ft.Text(m["plan"], size=10, color=TEXT_SECONDARY),
                                bgcolor=BG_INPUT,
                                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                                border_radius=4,
                            ),
                        ],
                    ),
                    padding=ft.padding.symmetric(vertical=4),
                )
            )
        if not items:
            items.append(label_text("Nadie en el gimnasio ahora", color=TEXT_MUTED))
        return items

    def _refresh_present_list(self):
        self.present_column.controls = self._build_present_list()

    def _refresh_counters(self):
        snapshot = build_access_snapshot()
        self.allowed_counter.value = str(snapshot["allowed_today"])
        self.denied_counter.value = str(snapshot["denied_today"])
        self.events_counter.value = str(snapshot["total_events"])

    def _counter_card(self, label, value_control, color):
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(label, size=11, color=TEXT_MUTED, weight="w500"),
                    value_control,
                ],
                spacing=2,
            ),
            expand=True,
            **card_style(),
        )
