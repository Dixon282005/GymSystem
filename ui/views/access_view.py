"""Live Access Feed view — real-time NFC access log for reception."""

import flet as ft
from core.theme import (
    BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_DANGER,
    FONT_SIZE_MD,
    card_style, heading_text, label_text,
)
from core.mock_data import ACCESS_LOG, APP_SETTINGS, find_member_by_cedula
from core.business import can_member_access, register_access_attempt, build_access_snapshot
from ui.components.widgets import AccessLogCard


class AccessView(ft.Column):
    """Live access feed with NFC simulation."""

    def __init__(self):
        snapshot = build_access_snapshot()

        self.allowed_counter = ft.Text(str(snapshot["allowed_today"]), size=22, color=ACCENT_SUCCESS, weight="w700")
        self.denied_counter = ft.Text(str(snapshot["denied_today"]), size=22, color=ACCENT_DANGER, weight="w700")
        self.events_counter = ft.Text(str(snapshot["total_events"]), size=22, color=ACCENT_PRIMARY, weight="w700")

        self.log_container = ft.Column(
            controls=[],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

        self.present_column = ft.Column(controls=[], spacing=8)
        self._refresh_present_list()

        self.filter_status = ft.Dropdown(
            label="Estado",
            value="TODOS",
            options=[
                ft.dropdown.Option("TODOS"),
                ft.dropdown.Option("PERMITIDO"),
                ft.dropdown.Option("DENEGADO"),
            ],
            width=150,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
        )
        self.filter_query = ft.TextField(
            hint_text="Filtrar por cedula o nombre...",
            width=260,
            height=42,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            on_submit=self._refresh_log_cards,
        )
        self.apply_filter_btn = ft.IconButton(
            icon=ft.Icons.FILTER_ALT,
            icon_color=ACCENT_PRIMARY,
            tooltip="Aplicar filtros",
            on_click=self._refresh_log_cards,
        )

        self.sim_input = ft.TextField(
            hint_text="Simular escaneo NFC (ingresa cedula)...",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=8,
            text_size=14,
            height=42,
            width=300,
            on_submit=self._simulate_scan,
            disabled=not APP_SETTINGS.get("enable_nfc_simulation", True),
        )

        self._refresh_log_cards()

        super().__init__(
            controls=[
                ft.Row(
                    controls=[
                        heading_text("Live Access Feed"),
                        ft.Container(expand=True),
                        self.filter_status,
                        self.filter_query,
                        self.apply_filter_btn,
                        label_text("Simulacion NFC", color=TEXT_MUTED),
                        self.sim_input,
                    ],
                ),
                ft.Container(height=8),
                ft.Row(
                    controls=[
                        self._counter_card("Permitidos", self.allowed_counter, ACCENT_SUCCESS),
                        self._counter_card("Denegados", self.denied_counter, ACCENT_DANGER),
                        self._counter_card("Eventos", self.events_counter, ACCENT_PRIMARY),
                    ],
                    spacing=12,
                ),
                ft.Container(height=8),
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    heading_text("Registro de Accesos", size=FONT_SIZE_MD),
                                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=12)),
                                    self.log_container,
                                ],
                                spacing=8,
                            ),
                            expand=2,
                            **card_style(),
                        ),
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    heading_text("En el Gimnasio", size=FONT_SIZE_MD),
                                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=12)),
                                    self.present_column,
                                ],
                                spacing=8,
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

    def _build_log_cards(self):
        selected_status = self.filter_status.value or "TODOS"
        query = (self.filter_query.value or "").strip().upper()

        cards = []
        for entry in ACCESS_LOG:
            if selected_status != "TODOS" and entry["status"] != selected_status:
                continue

            haystack = f"{entry['cedula']} {entry['nombre']}".upper()
            if query and query not in haystack:
                continue

            cards.append(
                AccessLogCard(
                    nombre=entry["nombre"],
                    plan=entry["plan"],
                    hora=entry["hora"],
                    status=entry["status"],
                    cedula=entry["cedula"],
                )
            )

        if not cards:
            cards.append(
                ft.Container(
                    content=label_text("Sin resultados para el filtro", color=TEXT_MUTED),
                    **card_style(),
                )
            )

        return cards

    def _refresh_log_cards(self, e=None):
        self.log_container.controls = self._build_log_cards()
        if e is not None:
            self.log_container.update()

    def _build_present_list(self):
        present = build_access_snapshot()["present"]
        items = []
        for m in present:
            items.append(
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=ACCENT_SUCCESS),
                        ft.Text(m["nombre"], size=13, color=TEXT_PRIMARY),
                        ft.Container(expand=True),
                        ft.Text(m["plan"], size=12, color=TEXT_SECONDARY),
                    ],
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
        self.allowed_counter.update()
        self.denied_counter.update()
        self.events_counter.update()

    def _counter_card(self, label, value_control, color):
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(label, size=12, color=TEXT_MUTED),
                    value_control,
                ],
                spacing=4,
            ),
            expand=True,
            **card_style(),
        )

    def _simulate_scan(self, e):
        cedula = self.sim_input.value.strip()
        if not cedula:
            return

        member = find_member_by_cedula(cedula)
        allowed, _reason = can_member_access(member)
        register_access_attempt(cedula, member, allowed)
        self.sim_input.value = ""
        self._refresh_present_list()
        self._refresh_log_cards()
        self.sim_input.update()
        self.present_column.update()
        self._refresh_counters()
