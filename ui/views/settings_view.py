"""Settings view for local mock configuration."""

import flet as ft

from core.mock_data import APP_SETTINGS
from core.db_store import save_settings
from core.theme import (
    ACCENT_PRIMARY,
    BG_INPUT,
    BORDER,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    FONT_SIZE_MD,
    card_style,
    heading_text,
)


class SettingsView(ft.Column):
    """Simple local settings panel for mock mode."""

    def __init__(self):
        self.gym_name = ft.TextField(
            label="Gym name",
            value=APP_SETTINGS.get("gym_name", "Gymsis"),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.currency = ft.Dropdown(
            label="Currency",
            value=APP_SETTINGS.get("currency", "USD"),
            options=[ft.dropdown.Option("USD"), ft.dropdown.Option("VES"), ft.dropdown.Option("EUR")],
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.expiry_days = ft.TextField(
            label="Expiry alert days",
            value=str(APP_SETTINGS.get("expiry_alert_days", 7)),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.allow_inactive = ft.Switch(
            label="Allow inactive access",
            value=bool(APP_SETTINGS.get("allow_inactive_access", False)),
            active_color=ACCENT_PRIMARY,
        )
        self.enable_nfc = ft.Switch(
            label="Enable NFC simulation",
            value=bool(APP_SETTINGS.get("enable_nfc_simulation", True)),
            active_color=ACCENT_PRIMARY,
        )

        super().__init__(
            controls=[
                heading_text("Configuration"),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            heading_text("General", size=FONT_SIZE_MD),
                            self.gym_name,
                            self.currency,
                        ],
                        spacing=12,
                    ),
                    **card_style(),
                ),
                ft.Container(height=12),
                ft.Container(
                    content=ft.Column(
                        controls=[
                            heading_text("Business rules", size=FONT_SIZE_MD),
                            self.expiry_days,
                            self.allow_inactive,
                            self.enable_nfc,
                            ft.Row(
                                controls=[
                                    ft.ElevatedButton(
                                        "Save",
                                        on_click=self._save,
                                        bgcolor=ACCENT_PRIMARY,
                                        color=TEXT_PRIMARY,
                                    ),
                                    ft.Text("Mock mode only", color=TEXT_MUTED, size=12),
                                ]
                            ),
                            ft.Text("", color=TEXT_MUTED, size=12),
                        ],
                        spacing=12,
                    ),
                    **card_style(),
                ),
            ],
            spacing=8,
            expand=True,
        )

    def _save(self, e):
        APP_SETTINGS["gym_name"] = (self.gym_name.value or "Gymsis").strip() or "Gymsis"
        APP_SETTINGS["currency"] = self.currency.value or "USD"

        try:
            APP_SETTINGS["expiry_alert_days"] = max(0, int(self.expiry_days.value or "7"))
        except ValueError:
            APP_SETTINGS["expiry_alert_days"] = 7
            self.expiry_days.value = "7"
            self.expiry_days.update()

        APP_SETTINGS["allow_inactive_access"] = bool(self.allow_inactive.value)
        APP_SETTINGS["enable_nfc_simulation"] = bool(self.enable_nfc.value)
        save_settings(APP_SETTINGS)

        self.page.snack_bar = ft.SnackBar(
            content=ft.Text("Configuration saved in mock memory", color=TEXT_PRIMARY),
            bgcolor="#0f766e",
        )
        self.page.snack_bar.open = True
        self.page.update()
