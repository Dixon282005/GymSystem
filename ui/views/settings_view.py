"""Settings view — general parameters, local SQLite/PostgreSQL persistence,
automatic migration, BCV exchange rate controls, and backup export/import tools.
"""

from __future__ import annotations

import glob
import os
import flet as ft

from core.mock_data import APP_SETTINGS, MEMBERS, ACCESS_LOG
from core.db_store import (
    bootstrap_database,
    export_access_log_csv,
    export_backup_json,
    export_members_csv,
    get_active_engine,
    get_db_health,
    import_backup_json,
    load_access_log,
    load_members,
    save_settings,
)
from core.bcv_service import bcv_service
from core.event_bus import event_bus
from core.theme import (
    ACCENT_DANGER,
    ACCENT_INFO,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    ACCENT_WARNING,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FONT_SIZE_MD,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
    PADDING_MD,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    button_primary,
    card_style,
    heading_text,
    label_text,
)


class SettingsView(ft.Column):
    """Settings panel with database management, BCV rate configuration, and backups."""

    def __init__(self):
        super().__init__(spacing=10, expand=True, scroll=ft.ScrollMode.AUTO)

        engine = get_active_engine()
        db_health = get_db_health()

        self.gym_name = ft.TextField(
            label="Nombre del Gimnasio",
            value=APP_SETTINGS.get("gym_name", "Gymsis"),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.currency = ft.Dropdown(
            label="Moneda Principal",
            value=APP_SETTINGS.get("currency", "USD"),
            options=[ft.dropdown.Option("USD"), ft.dropdown.Option("VES"), ft.dropdown.Option("EUR")],
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.expiry_days = ft.TextField(
            label="Días de alerta antes del vencimiento",
            value=str(APP_SETTINGS.get("expiry_alert_days", 7)),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.allow_inactive = ft.Switch(
            label="Permitir acceso a miembros inactivos",
            value=bool(APP_SETTINGS.get("allow_inactive_access", False)),
            active_color=ACCENT_PRIMARY,
        )
        self.enable_nfc = ft.Switch(
            label="Habilitar simulación de NFC (Modo Manual)",
            value=bool(APP_SETTINGS.get("enable_nfc_simulation", False)),
            active_color=ACCENT_PRIMARY,
        )

        # Database Engine Info Card
        engine_label = "SQLite Local (data/gymsis.db)" if engine == "sqlite" else "PostgreSQL Server"
        self.db_info_label = ft.Text(
            f"Motor Activo: {engine_label} • {len(MEMBERS)} Socios • {len(ACCESS_LOG)} Accesos",
            size=13,
            color=ACCENT_SUCCESS,
            weight="w600",
        )

        self.last_export_label = ft.Text(
            "Los respaldos se almacenan automáticamente en la carpeta /backups",
            size=12,
            color=TEXT_MUTED,
        )

        # -------------------------------------------------------------------
        # BCV Exchange Rate Controls
        # -------------------------------------------------------------------
        current_rate = bcv_service.get_rate()
        self.bcv_current_badge = ft.Text(
            f"{current_rate:.2f} Bs/USD",
            size=13,
            color=ACCENT_PRIMARY,
            weight="w700",
        )
        self.bcv_rate_field = ft.TextField(
            label="Tasa Manual USD / VES (Bs)",
            value=f"{current_rate:.2f}",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^\d*\.?\d{0,2}$", replacement_string=""),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            width=200,
        )
        self.bcv_info_text = ft.Text(
            f"Última actualización: {bcv_service.get_last_updated()} (Fuente: {bcv_service.get_source()}) • Consulta automática: Activa (al abrir y a cada :00 / :30)",
            size=12,
            color=TEXT_MUTED,
        )

        # Import Dialog
        self.import_input = ft.TextField(
            label="Ruta de archivo o JSON de respaldo",
            hint_text="ej: backups/gymsis_backup_20261016_220000.json o pega el contenido",
            multiline=True,
            min_lines=3,
            max_lines=6,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=12,
        )
        self.import_status_label = ft.Text("", size=12, color=TEXT_MUTED)

        self.import_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Restaurar / Importar Base de Datos", size=FONT_SIZE_MD),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Selecciona un respaldo anterior. Compatible con versiones anteriores: "
                            "migrará y asociará automáticamente tus socios, tags NFC, productos y asistencias.",
                            size=12,
                            color=TEXT_SECONDARY,
                        ),
                        ft.Container(height=8),
                        self.import_input,
                        self.import_status_label,
                    ],
                    spacing=8,
                    tight=True,
                ),
                width=500,
                padding=PADDING_MD,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._close_import_dialog),
                ft.ElevatedButton(
                    "Restaurar Datos",
                    bgcolor=ACCENT_PRIMARY,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._execute_import,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            bgcolor=BG_CARD,
        )

        # Assemble Main Controls
        self.controls = [
            heading_text("Configuración del Sistema"),
            ft.Container(height=4),

            # Section 1: Database & Backups
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.STORAGE, color=ACCENT_PRIMARY, size=22),
                                heading_text("Base de Datos, Migración y Respaldos", size=FONT_SIZE_MD),
                                ft.Container(expand=True),
                                ft.Container(
                                    content=self.db_info_label,
                                    bgcolor=ft.Colors.with_opacity(0.12, ACCENT_SUCCESS),
                                    padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                    border_radius=RADIUS_SM,
                                    border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ACCENT_SUCCESS)),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            "Tus datos se guardan automáticamente en tu base de datos persistente (SQLite local). "
                            "Aunque actualices el código o reinicies el equipo, tus socios y llaves NFC nunca se pierden.",
                            size=13,
                            color=TEXT_SECONDARY,
                        ),
                        ft.Container(height=8),
                        ft.Row(
                            controls=[
                                ft.ElevatedButton(
                                    "💾 Exportar Respaldo (.JSON)",
                                    bgcolor=ACCENT_PRIMARY,
                                    color=TEXT_PRIMARY,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                                    on_click=self._export_json_backup,
                                ),
                                ft.ElevatedButton(
                                    "📥 Importar / Restaurar Respaldo",
                                    bgcolor=ACCENT_INFO,
                                    color=TEXT_PRIMARY,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                                    on_click=self._open_import_dialog,
                                ),
                                ft.OutlinedButton(
                                    "📊 Socios (.CSV)",
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                        side=ft.BorderSide(1, BORDER),
                                    ),
                                    on_click=self._export_members_csv_handler,
                                ),
                                ft.OutlinedButton(
                                    "📋 Accesos (.CSV)",
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                        side=ft.BorderSide(1, BORDER),
                                    ),
                                    on_click=self._export_access_csv_handler,
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        ft.Container(height=4),
                        self.last_export_label,
                    ],
                    spacing=10,
                ),
                **card_style(),
            ),

            ft.Container(height=8),

            # Section 2: BCV Exchange Rate
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CURRENCY_EXCHANGE, color=ACCENT_PRIMARY, size=22),
                                heading_text("Tasa Oficial Dólar BCV (Venezuela)", size=FONT_SIZE_MD),
                                ft.Container(expand=True),
                                ft.Container(
                                    content=self.bcv_current_badge,
                                    bgcolor=ft.Colors.with_opacity(0.12, ACCENT_PRIMARY),
                                    padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                    border_radius=RADIUS_SM,
                                    border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ACCENT_PRIMARY)),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Text(
                            "Gestiona la tasa oficial del Banco Central de Venezuela para la conversión bimonetaria "
                            "automática en renovaciones de membresías y ventas del punto de venta.",
                            size=13,
                            color=TEXT_SECONDARY,
                        ),
                        ft.Row(
                            controls=[
                                self.bcv_rate_field,
                                ft.ElevatedButton(
                                    "💾 Guardar Tasa Manual",
                                    bgcolor=ACCENT_PRIMARY,
                                    color=TEXT_PRIMARY,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                                    on_click=self._save_manual_bcv,
                                ),
                                ft.OutlinedButton(
                                    "🔄 Sincronizar con API BCV",
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                        side=ft.BorderSide(1, BORDER),
                                    ),
                                    on_click=self._sync_bcv_api,
                                ),
                            ],
                            spacing=10,
                            wrap=True,
                        ),
                        self.bcv_info_text,
                    ],
                    spacing=10,
                ),
                **card_style(),
            ),

            ft.Container(height=8),

            # Section 3: General settings
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

            ft.Container(height=8),

            # Section 4: Business rules
            ft.Container(
                content=ft.Column(
                    controls=[
                        heading_text("Reglas de Negocio", size=FONT_SIZE_MD),
                        self.expiry_days,
                        self.allow_inactive,
                        self.enable_nfc,
                        ft.Row(
                            controls=[
                                ft.ElevatedButton(
                                    "Guardar Configuración General",
                                    on_click=self._save,
                                    bgcolor=ACCENT_PRIMARY,
                                    color=TEXT_PRIMARY,
                                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                                ),
                            ]
                        ),
                    ],
                    spacing=12,
                ),
                **card_style(),
            ),
        ]

    def did_mount(self):
        from core.event_bus import event_bus
        event_bus.subscribe("bcv_updated", self._on_bcv_updated)

    def will_unmount(self):
        from core.event_bus import event_bus
        event_bus.unsubscribe("bcv_updated", self._on_bcv_updated)
        self.page = None

    def _save_manual_bcv(self, e):
        self.bcv_rate_field.error_text = None
        raw = (self.bcv_rate_field.value or "").replace(",", ".").strip()
        try:
            val = float(raw)
            if val <= 0:
                self.bcv_rate_field.error_text = "La tasa debe ser mayor a 0"
                self.bcv_rate_field.update()
                return
        except ValueError:
            self.bcv_rate_field.error_text = "Tasa numérica inválida (ej: 52.40)"
            self.bcv_rate_field.update()
            return

        bcv_service.set_manual_rate(val)
        self.bcv_current_badge.value = f"{val:.2f} Bs/USD"
        self.bcv_info_text.value = f"Última actualización: {bcv_service.get_last_updated()} (Fuente: Manual)"
        event_bus.publish("bcv_updated", val)

        if hasattr(self, "page") and self.page:
            try:
                self.bcv_rate_field.update()
                self.bcv_current_badge.update()
                self.bcv_info_text.update()
            except Exception:
                pass

        self._show_toast(f"Tasa BCV manual establecida en {val:.2f} Bs/USD", ACCENT_SUCCESS)

    def _on_bcv_updated(self, rate=None):
        if getattr(self, "page", None) is None:
            return
        if rate is None:
            rate = bcv_service.get_rate()
        self.bcv_current_badge.value = f"{rate:.2f} Bs/USD"
        self.bcv_rate_field.value = f"{rate:.2f}"
        info_str = f"Última actualización: {bcv_service.get_last_updated()} (Fuente: {bcv_service.get_source()}) • Consulta automática: Activa (al abrir y a cada :00 / :30)"
        fv = bcv_service.get_fecha_valor()
        if fv:
            info_str += f" • Fecha Valor: {fv}"
        self.bcv_info_text.value = info_str
        if hasattr(self, "page") and self.page:
            try:
                self.bcv_current_badge.update()
                self.bcv_rate_field.update()
                self.bcv_info_text.update()
            except Exception:
                pass

    def _sync_bcv_api(self, e):
        self._show_toast("Consultando tasa oficial del BCV...", ACCENT_INFO)
        success, rate, msg = bcv_service.fetch_official_rate()
        if not success:
            rate = bcv_service.get_rate()

        self.bcv_rate_field.error_text = None
        self.bcv_rate_field.value = f"{rate:.2f}"
        self.bcv_current_badge.value = f"{rate:.2f} Bs/USD"
        info_str = f"Última actualización: {bcv_service.get_last_updated()} (Fuente: {bcv_service.get_source()})"
        fv = bcv_service.get_fecha_valor()
        if fv:
            info_str += f" • Fecha Valor: {fv}"
        self.bcv_info_text.value = info_str
        event_bus.publish("bcv_updated", rate)

        if hasattr(self, "page") and self.page:
            try:
                self.bcv_rate_field.update()
                self.bcv_current_badge.update()
                self.bcv_info_text.update()
            except Exception:
                pass

        if success:
            self._show_toast(f"Tasa sincronizada con BCV: {rate:.2f} Bs/USD", ACCENT_SUCCESS)
        else:
            self._show_toast(msg, ACCENT_WARNING)


    def _save(self, e):
        self.gym_name.error_text = None
        self.expiry_days.error_text = None

        has_error = False
        gym_name_val = (self.gym_name.value or "").strip()
        if not gym_name_val:
            self.gym_name.error_text = "El nombre del gimnasio no puede estar vacío"
            has_error = True

        raw_exp = (self.expiry_days.value or "").strip()
        try:
            exp_days = int(raw_exp)
            if exp_days < 0:
                self.expiry_days.error_text = "Los días no pueden ser negativos"
                has_error = True
        except ValueError:
            self.expiry_days.error_text = "Debe ser un número entero (ej: 7)"
            has_error = True

        if has_error:
            self.gym_name.update()
            self.expiry_days.update()
            return

        APP_SETTINGS["gym_name"] = gym_name_val
        APP_SETTINGS["currency"] = self.currency.value or "USD"
        APP_SETTINGS["expiry_alert_days"] = exp_days
        APP_SETTINGS["allow_inactive_access"] = bool(self.allow_inactive.value)
        APP_SETTINGS["enable_nfc_simulation"] = bool(self.enable_nfc.value)
        save_settings(APP_SETTINGS)

        self._show_toast("Configuración guardada en la base de datos persistente", ACCENT_SUCCESS)

    def _export_json_backup(self, e):
        try:
            path = export_backup_json()
            fname = os.path.basename(path)
            self.last_export_label.value = f"Último respaldo JSON: {path}"
            self.last_export_label.color = ACCENT_SUCCESS
            try:
                self.last_export_label.update()
            except Exception:
                pass
            self._show_toast(f"Respaldo generado con éxito: {fname}", ACCENT_SUCCESS)
        except Exception as exc:
            self._show_toast(f"Error exportando respaldo: {exc}", ACCENT_DANGER)

    def _export_members_csv_handler(self, e):
        try:
            path = export_members_csv()
            fname = os.path.basename(path)
            self.last_export_label.value = f"Archivo CSV generado: {path}"
            self.last_export_label.color = ACCENT_INFO
            try:
                self.last_export_label.update()
            except Exception:
                pass
            self._show_toast(f"Socios exportados a CSV: {fname}", ACCENT_SUCCESS)
        except Exception as exc:
            self._show_toast(f"Error exportando CSV: {exc}", ACCENT_DANGER)

    def _export_access_csv_handler(self, e):
        try:
            path = export_access_log_csv()
            fname = os.path.basename(path)
            self.last_export_label.value = f"Archivo CSV de accesos generado: {path}"
            self.last_export_label.color = ACCENT_INFO
            try:
                self.last_export_label.update()
            except Exception:
                pass
            self._show_toast(f"Historial exportado a CSV: {fname}", ACCENT_SUCCESS)
        except Exception as exc:
            self._show_toast(f"Error exportando accesos: {exc}", ACCENT_DANGER)

    def _open_import_dialog(self, e):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        backups_dir = os.path.join(base_dir, "backups")
        files = sorted(glob.glob(os.path.join(backups_dir, "*.json")), reverse=True)
        if files:
            self.import_input.value = files[0]
            self.import_status_label.value = f"Último respaldo sugerido: {os.path.basename(files[0])}"
        else:
            self.import_input.value = ""
            self.import_status_label.value = "Ingresa la ruta de un archivo .json o pega el JSON de respaldo"

        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "show_dialog"):
                try:
                    self.page.show_dialog(self.import_dialog)
                    return
                except Exception:
                    pass
            self.page.dialog = self.import_dialog
            self.import_dialog.open = True
            self.page.update()

    def _close_import_dialog(self, e):
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "pop_dialog"):
                try:
                    self.page.pop_dialog()
                    return
                except Exception:
                    pass
            self.import_dialog.open = False
            self.page.update()

    def _execute_import(self, e):
        raw_val = (self.import_input.value or "").strip()
        if not raw_val:
            self.import_status_label.value = "Por favor ingresa una ruta o contenido JSON válido"
            self.import_status_label.color = ACCENT_DANGER
            try:
                self.import_status_label.update()
            except Exception:
                pass
            return

        try:
            res = import_backup_json(raw_val)
            self._close_import_dialog(None)
            m_count = res.get("members_imported", 0)
            e_count = res.get("events_imported", 0)
            self.db_info_label.value = f"Motor: {get_active_engine()} • {len(MEMBERS)} Socios • {len(ACCESS_LOG)} Accesos"
            try:
                self.db_info_label.update()
            except Exception:
                pass
            self._show_toast(f"¡Restauración exitosa! {m_count} socios y {e_count} accesos importados.", ACCENT_SUCCESS)
        except Exception as exc:
            self.import_status_label.value = f"Error en la importación: {exc}"
            self.import_status_label.color = ACCENT_DANGER
            try:
                self.import_status_label.update()
            except Exception:
                pass

    def _show_toast(self, message: str, color: str):
        if hasattr(self, "page") and self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=TEXT_PRIMARY, weight="w500"),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            try:
                self.page.update()
            except Exception:
                pass
