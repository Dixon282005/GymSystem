"""Kiosk view — dedicated client entrance display for gyms.
Always listens for NFC tags from the ACS ACR122U reader, displays hero feedback,
and triggers high-definition voice greetings exclusively for client events.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
import flet as ft

from core.audio_service import audio
from core.business import build_access_snapshot, process_nfc_scan
from core.mock_data import ACCESS_LOG, MEMBERS
from core.nfc_service import nfc_reader
from core.theme import (
    ACCENT_DANGER,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    BG_BASE,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FONT_SIZE_2XL,
    FONT_SIZE_LG,
    FONT_SIZE_MD,
    FONT_SIZE_SM,
    FONT_SIZE_XL,
    FONT_SIZE_XS,
    PADDING_LG,
    PADDING_MD,
    PADDING_SM,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    card_style,
    heading_text,
    label_text,
)
from ui.components.widgets import LiveClock


class KioskView(ft.Container):
    """Fullscreen entrance kiosk for gym members."""

    def __init__(self, on_admin_click=None):
        self.on_admin_click = on_admin_click
        self._reset_timer = None

        # Reader hardware status badge
        self.reader_icon = ft.Icon(
            ft.Icons.NFC,
            size=18,
            color=ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER,
        )
        self.reader_label = ft.Text(
            "ACR122U Activo" if nfc_reader.is_connected else "Lector Desconectado",
            size=12,
            weight="w600",
            color=ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER,
        )
        self.reader_badge = ft.Container(
            content=ft.Row(
                controls=[self.reader_icon, self.reader_label],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            bgcolor=ft.Colors.with_opacity(0.12, ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ACCENT_SUCCESS if nfc_reader.is_connected else ACCENT_DANGER)),
            border_radius=16,
        )

        # Discrete manual input for testing or reception override
        self.manual_input = ft.TextField(
            hint_text="Cédula o UID manual + Enter",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=12,
            height=38,
            width=220,
            on_submit=self._handle_manual_input,
        )

        # Hero Scanner Feedback Container
        self.hero_container = ft.Container(
            content=self._build_idle_hero(),
            width=680,
            padding=PADDING_LG,
            bgcolor=BG_CARD,
            border=ft.Border.all(1.5, BORDER),
            border_radius=RADIUS_LG,
            alignment=ft.Alignment(0, 0),
            animate=ft.Animation(duration=250, curve=ft.AnimationCurve.EASE_OUT),
        )

        # Real-time attendance counters
        self.active_now_label = ft.Text("0", size=FONT_SIZE_2XL, color=TEXT_PRIMARY, weight="w800")
        self.total_today_label = ft.Text("0", size=FONT_SIZE_2XL, color=TEXT_PRIMARY, weight="w800")
        self._refresh_counters()

        # Recent entrances list
        self.recent_list = ft.Row(
            controls=self._build_recent_chips(),
            spacing=10,
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
        )

        # Hook NFC service
        nfc_reader.access_callback = self._on_nfc_scan
        nfc_reader.status_callback = self._on_nfc_status_change

        super().__init__(
            content=ft.Column(
                controls=[
                    # Header
                    self._build_kiosk_header(),
                    ft.Container(expand=True),
                    # Center Hero Display
                    ft.Row(
                        controls=[self.hero_container],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(height=16),
                    # Bottom Status & Recent Entrants
                    self._build_kiosk_footer(),
                    ft.Container(expand=True),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            expand=True,
            bgcolor=BG_BASE,
            padding=24,
            alignment=ft.Alignment(0, 0),
        )

    def _build_kiosk_header(self):
        return ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FITNESS_CENTER, color=ACCENT_PRIMARY, size=28),
                        ft.Text("Gymsis", size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w800"),
                        ft.Container(
                            content=ft.Text("ACCESO DE SOCIOS", size=11, color=ACCENT_PRIMARY, weight="w700"),
                            bgcolor=ft.Colors.with_opacity(0.15, ACCENT_PRIMARY),
                            padding=ft.padding.symmetric(horizontal=8, vertical=4),
                            border_radius=6,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Container(expand=True),
                self.reader_badge,
                ft.Container(width=8),
                LiveClock(),
                ft.Container(width=12),
                ft.ElevatedButton(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS, size=18, color=TEXT_PRIMARY),
                            ft.Text("Administración", size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600"),
                        ],
                        spacing=6,
                    ),
                    bgcolor=BG_INPUT,
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                        side=ft.BorderSide(1, BORDER),
                    ),
                    on_click=self.on_admin_click,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_idle_hero(self):
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.CONTACTLESS, size=72, color=ACCENT_PRIMARY),
                    padding=20,
                    bgcolor=ft.Colors.with_opacity(0.12, ACCENT_PRIMARY),
                    border_radius=60,
                ),
                ft.Container(height=16),
                ft.Text(
                    "Acerque su Llavero o Tarjeta al Lector",
                    size=FONT_SIZE_XL,
                    color=TEXT_PRIMARY,
                    weight="w700",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Control de acceso automático por proximidad NFC (ACR122U)",
                    size=FONT_SIZE_SM,
                    color=TEXT_SECONDARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=24),
                ft.Row(
                    controls=[self.manual_input],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            tight=True,
        )

    def _build_granted_hero(self, member: dict):
        from core.business import compute_membership_urgency
        nombre = member.get("nombre", "Socio")
        first_name = nombre.split()[0] if nombre else "SOCIO"
        plan = member.get("plan", "Básico")
        venc = member.get("vencimiento", "")
        urgency = member.get("urgency") or compute_membership_urgency(member)
        urg_hex = urgency.get("hex", "#10B981")
        urg_label = urgency.get("label", "Vigente")

        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.CHECK_CIRCLE, size=76, color=ACCENT_SUCCESS),
                    padding=16,
                    bgcolor=ft.Colors.with_opacity(0.18, ACCENT_SUCCESS),
                    border_radius=60,
                ),
                ft.Container(height=10),
                ft.Text(
                    f"¡BIENVENIDO, {first_name.upper()}!",
                    size=FONT_SIZE_2XL,
                    color=ACCENT_SUCCESS,
                    weight="w800",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    nombre,
                    size=26,
                    color=TEXT_PRIMARY,
                    weight="w700",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=10),
                # Prominent Plan & Days Remaining Card with Color Highlighting
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.CARD_MEMBERSHIP, size=18, color=urg_hex),
                                    ft.Text(f"Plan: {plan.upper()}", size=14, color=TEXT_PRIMARY, weight="w700"),
                                    ft.Container(expand=True),
                                    ft.Container(
                                        content=ft.Text(
                                            urg_label.upper(),
                                            size=12,
                                            color=ft.Colors.WHITE,
                                            weight="w800",
                                        ),
                                        bgcolor=urg_hex,
                                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                                        border_radius=RADIUS_SM,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Container(height=4),
                            ft.Text(
                                f"Fecha de vencimiento: {venc}",
                                size=12,
                                color=TEXT_SECONDARY,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                    ),
                    bgcolor=ft.Colors.with_opacity(0.15, urg_hex),
                    border=ft.Border.all(1.5, urg_hex),
                    padding=ft.padding.symmetric(horizontal=20, vertical=12),
                    border_radius=RADIUS_MD,
                    width=420,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            tight=True,
        )

    def _build_exit_hero(self, member: dict):
        nombre = member.get("nombre", "Socio")
        first_name = nombre.split()[0] if nombre else "SOCIO"
        plan = member.get("plan", "Básico")

        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.DIRECTIONS_WALK, size=76, color=ft.Colors.CYAN_ACCENT),
                    padding=16,
                    bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.CYAN_ACCENT),
                    border_radius=60,
                ),
                ft.Container(height=12),
                ft.Text(
                    f"¡HASTA LUEGO, {first_name.upper()}!",
                    size=FONT_SIZE_2XL,
                    color=ft.Colors.CYAN_ACCENT,
                    weight="w800",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    nombre,
                    size=26,
                    color=TEXT_PRIMARY,
                    weight="w700",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Text(
                        "Salida registrada con éxito · ¡Buen descanso!",
                        size=13,
                        color=ft.Colors.CYAN_ACCENT,
                        weight="w600",
                    ),
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.CYAN_ACCENT),
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                    border_radius=RADIUS_SM,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            tight=True,
        )

    def _build_denied_hero(self, member: dict | None, reason: str):
        nombre = member.get("nombre", "Tarjeta No Registrada") if member else "Llavero Desconocido"
        return ft.Column(
            controls=[
                ft.Container(
                    content=ft.Icon(ft.Icons.CANCEL, size=76, color=ACCENT_DANGER),
                    padding=16,
                    bgcolor=ft.Colors.with_opacity(0.18, ACCENT_DANGER),
                    border_radius=60,
                ),
                ft.Container(height=12),
                ft.Text(
                    "ACCESO DENEGADO",
                    size=FONT_SIZE_2XL,
                    color=ACCENT_DANGER,
                    weight="w800",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    nombre,
                    size=24,
                    color=TEXT_PRIMARY,
                    weight="w700",
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Text(
                        f"Motivo: {reason.upper()}",
                        size=13,
                        color=ACCENT_DANGER,
                        weight="w600",
                    ),
                    bgcolor=ft.Colors.with_opacity(0.15, ACCENT_DANGER),
                    padding=ft.padding.symmetric(horizontal=16, vertical=8),
                    border_radius=RADIUS_SM,
                ),
                ft.Text(
                    "Por favor acérquese a recepción para regularizar su membresía",
                    size=12,
                    color=TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
            tight=True,
        )

    def _build_kiosk_footer(self):
        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        # Counter 1
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.DIRECTIONS_RUN, color=ACCENT_SUCCESS, size=24),
                                    ft.Column(
                                        controls=[
                                            ft.Text("ENTRENANDO AHORA", size=10, color=TEXT_MUTED, weight="w600"),
                                            self.active_now_label,
                                        ],
                                        spacing=1,
                                    ),
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.symmetric(horizontal=20, vertical=10),
                            bgcolor=BG_CARD,
                            border=ft.Border.all(1, BORDER),
                            border_radius=RADIUS_MD,
                        ),
                        # Counter 2
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.LOGIN, color=ACCENT_PRIMARY, size=24),
                                    ft.Column(
                                        controls=[
                                            ft.Text("ACCESOS HOY", size=10, color=TEXT_MUTED, weight="w600"),
                                            self.total_today_label,
                                        ],
                                        spacing=1,
                                    ),
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.symmetric(horizontal=20, vertical=10),
                            bgcolor=BG_CARD,
                            border=ft.Border.all(1, BORDER),
                            border_radius=RADIUS_MD,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=16,
                ),
                ft.Container(height=12),
                ft.Text("ÚLTIMOS MOVIMIENTOS", size=11, color=TEXT_MUTED, weight="w700"),
                ft.Container(height=6),
                self.recent_list,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
            tight=True,
        )

    def _build_recent_chips(self):
        chips = []
        recent_events = [e for e in ACCESS_LOG if e.get("status") in ("ENTRADA", "PERMITIDO", "SALIDA")][:5]
        for e in recent_events:
            is_exit = e.get("status") == "SALIDA"
            chip_color = ft.Colors.CYAN_ACCENT if is_exit else ACCENT_SUCCESS
            chip_icon = ft.Icons.DIRECTIONS_WALK if is_exit else ft.Icons.CHECK
            prefix = "Salida: " if is_exit else ""

            chips.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(chip_icon, size=14, color=chip_color),
                            ft.Text(f"{prefix}{e.get('nombre', '')}", size=12, color=TEXT_PRIMARY, weight="w500"),
                            ft.Text(e.get("hora", ""), size=11, color=TEXT_MUTED),
                        ],
                        spacing=6,
                    ),
                    bgcolor=BG_CARD,
                    border=ft.Border.all(1, BORDER),
                    padding=ft.padding.symmetric(horizontal=12, vertical=6),
                    border_radius=20,
                )
            )
        if not chips:
            chips.append(ft.Text("Esperando primeros movimientos del día...", size=12, color=TEXT_MUTED))
        return chips

    def _on_nfc_status_change(self, connected: bool, message: str):
        color = ACCENT_SUCCESS if connected else ACCENT_DANGER
        self.reader_icon.color = color
        self.reader_label.value = "ACR122U Activo" if connected else "Lector Desconectado"
        self.reader_label.color = color
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
        if nfc_reader.is_connected:
            self._on_nfc_status_change(True, "ACR122U Activo")

    def will_unmount(self):
        from core.event_bus import event_bus
        event_bus.unsubscribe("access_scan", self._on_event_bus_scan)
        event_bus.unsubscribe("members_changed", self._on_event_bus_members_changed)

    def _on_event_bus_scan(self, result: dict):
        self._display_scan_result(result)

    def _on_event_bus_members_changed(self, member):
        self._refresh_counters()
        if hasattr(self, "page") and self.page:
            try:
                self.active_now_label.update()
                self.total_today_label.update()
            except Exception:
                pass

    def _on_nfc_scan(self, uid: str):
        """Dispatched from the background NFC thread when a tag touches the ACR122U."""
        process_nfc_scan(uid, min_interval=3.0)

    def _handle_manual_input(self, e):
        raw = (self.manual_input.value or "").strip()
        if not raw:
            return
        self.manual_input.value = ""
        try:
            self.manual_input.update()
        except Exception:
            pass

        process_nfc_scan(raw)

    def _display_scan_result(self, result: dict):
        action = result.get("action", "ENTRADA" if result.get("allowed") else "DENEGADO")
        member = result.get("member")
        reason = result.get("reason", "")

        if action == "SALIDA":
            accent = ft.Colors.CYAN_ACCENT
            self.hero_container.content = self._build_exit_hero(member)
        elif action == "ENTRADA":
            accent = ACCENT_SUCCESS
            self.hero_container.content = self._build_granted_hero(member)
        else:
            accent = ACCENT_DANGER
            self.hero_container.content = self._build_denied_hero(member, reason)

        self.hero_container.border = ft.Border.all(2, accent)
        self.hero_container.bgcolor = ft.Colors.with_opacity(0.12, accent)

        self._refresh_counters()
        self.recent_list.controls = self._build_recent_chips()

        if hasattr(self, "page") and self.page:
            try:
                self.hero_container.update()
                self.active_now_label.update()
                self.total_today_label.update()
                self.recent_list.update()
            except Exception:
                pass

        # Schedule automatic reset back to idle state after 5 seconds
        if self._reset_timer and self._reset_timer.is_alive():
            self._reset_timer.cancel()

        self._reset_timer = threading.Timer(5.0, self._reset_to_idle)
        self._reset_timer.daemon = True
        self._reset_timer.start()

    def _reset_to_idle(self):
        self.hero_container.content = self._build_idle_hero()
        self.hero_container.border = ft.Border.all(1.5, BORDER)
        self.hero_container.bgcolor = BG_CARD
        if hasattr(self, "page") and self.page:
            try:
                self.hero_container.update()
            except Exception:
                pass

    def _refresh_counters(self):
        snap = build_access_snapshot()
        self.active_now_label.value = str(len(snap["present"]))
        self.total_today_label.value = str(snap["allowed_today"])
