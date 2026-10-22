"""Audit logs security and compliance view.
Provides full traceability for member modifications, sales, payments,
user administration, and financial shift closures.
"""

from __future__ import annotations

import json
from typing import Optional

import flet as ft

from core.repositories import AuditLogRepository
from core.theme import (
    ACCENT_DANGER,
    ACCENT_INFO,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    ACCENT_WARNING,
    BG_BASE,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FONT_SIZE_LG,
    FONT_SIZE_MD,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
    PADDING_MD,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    heading_text,
)

ButtonControl = getattr(ft, "Button", ft.ElevatedButton)

_ACTION_STYLES = {
    "CREAR_SOCIO": (ACCENT_SUCCESS, ft.Icons.PERSON_ADD),
    "REGISTRO_SOCIO": (ACCENT_SUCCESS, ft.Icons.PERSON_ADD),
    "CREAR_MIEMBRO": (ACCENT_SUCCESS, ft.Icons.PERSON_ADD),
    "ACTUALIZAR_MIEMBRO": (ACCENT_INFO, ft.Icons.EDIT),
    "EDICION_SOCIO": (ACCENT_INFO, ft.Icons.EDIT),
    "MODIFICAR_SOCIO": (ACCENT_INFO, ft.Icons.EDIT),
    "ELIMINAR_SOCIO": (ACCENT_DANGER, ft.Icons.PERSON_REMOVE),
    "CAMBIO_ESTADO_SOCIO": (ACCENT_WARNING, ft.Icons.SWAP_HORIZ),
    "CAMBIAR_ESTADO_MIEMBRO": (ACCENT_WARNING, ft.Icons.SWAP_HORIZ),
    "VINCULAR_LLAVE_NFC": (ft.Colors.CYAN_ACCENT, ft.Icons.CONTACTLESS),
    "EDITAR_LLAVE_NFC": (ft.Colors.CYAN_ACCENT, ft.Icons.EDIT_NOTE),
    "ELIMINAR_LLAVE_NFC": (ACCENT_DANGER, ft.Icons.DELETE_OUTLINE),
    "PAGO_MEMBRESIA": (ACCENT_SUCCESS, ft.Icons.PAYMENTS),
    "REGISTRAR_PAGO": (ACCENT_SUCCESS, ft.Icons.PAYMENTS),
    "VENTA_POS": (ACCENT_SUCCESS, ft.Icons.POINT_OF_SALE),
    "GUARDAR_PRODUCTO_POS": (ACCENT_INFO, ft.Icons.INVENTORY),
    "GUARDAR_PRODUCTO": (ACCENT_INFO, ft.Icons.INVENTORY),
    "ELIMINAR_PRODUCTO_POS": (ACCENT_DANGER, ft.Icons.DELETE),
    "ELIMINAR_PRODUCTO": (ACCENT_DANGER, ft.Icons.DELETE),
    "ESTADO_PRODUCTO_POS": (ACCENT_WARNING, ft.Icons.TOGGLE_ON),
    "GUARDAR_PLAN": (ACCENT_INFO, ft.Icons.CARD_MEMBERSHIP),
    "ELIMINAR_PLAN": (ACCENT_DANGER, ft.Icons.DELETE_FOREVER),
    "ESTADO_PLAN": (ACCENT_WARNING, ft.Icons.TOGGLE_ON),
    "CAMBIAR_ESTADO_PLAN": (ACCENT_WARNING, ft.Icons.TOGGLE_ON),
    "CREAR_USUARIO": (ACCENT_SUCCESS, ft.Icons.PERSON_ADD),
    "MODIFICAR_USUARIO": (ACCENT_INFO, ft.Icons.MANAGE_ACCOUNTS),
    "ELIMINAR_USUARIO": (ACCENT_DANGER, ft.Icons.PERSON_REMOVE),
    "ESTADO_USUARIO": (ACCENT_WARNING, ft.Icons.TOGGLE_ON),
    "CAMBIAR_ESTADO_USUARIO": (ACCENT_WARNING, ft.Icons.TOGGLE_ON),
    "INICIO_SESION": (ACCENT_PRIMARY, ft.Icons.LOGIN),
    "CIERRE_SESION": (ACCENT_WARNING, ft.Icons.LOGOUT),
    "CONFIGURACION_MODIFICADA": (ACCENT_INFO, ft.Icons.SETTINGS),
    "GUARDAR_CONFIGURACION": (ACCENT_INFO, ft.Icons.SETTINGS),
    "CIERRE_DE_CAJA": (ACCENT_SUCCESS, ft.Icons.MONETIZATION_ON),
}

_DEFAULT_ACTION_STYLE = (TEXT_MUTED, ft.Icons.INFO_OUTLINE)


class AuditLogsView(ft.Column):
    def __init__(self):
        self._logs = []
        self._dialog_attached = False

        self.search_field = ft.TextField(
            hint_text="Buscar en logs...",
            hint_style=ft.TextStyle(color=TEXT_MUTED, size=FONT_SIZE_SM),
            text_size=FONT_SIZE_SM,
            color=TEXT_PRIMARY,
            bgcolor=BG_INPUT,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            prefix_icon=ft.Icons.SEARCH,
            width=260,
            height=38,
            on_submit=self._apply_filters,
        )

        self.action_dropdown = ft.Dropdown(
            hint_text="Filtrar por Acción",
            hint_style=ft.TextStyle(color=TEXT_MUTED, size=FONT_SIZE_SM),
            text_size=FONT_SIZE_SM,
            color=TEXT_PRIMARY,
            bgcolor=BG_INPUT,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            width=220,
            height=38,
            options=[ft.dropdown.Option("Todas las Acciones")],
            value="Todas las Acciones",
            on_select=self._apply_filters,
        )

        self.user_dropdown = ft.Dropdown(
            hint_text="Filtrar por Usuario",
            hint_style=ft.TextStyle(color=TEXT_MUTED, size=FONT_SIZE_SM),
            text_size=FONT_SIZE_SM,
            color=TEXT_PRIMARY,
            bgcolor=BG_INPUT,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            width=180,
            height=38,
            options=[ft.dropdown.Option("Todos los Usuarios")],
            value="Todos los Usuarios",
            on_select=self._apply_filters,
        )

        self.count_label = ft.Text(
            "0 registros",
            size=FONT_SIZE_SM,
            color=TEXT_MUTED,
            weight=ft.FontWeight.W_500,
        )

        self.logs_table = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

        self.detail_content = ft.TextField(
            multiline=True,
            read_only=True,
            value="",
            text_size=FONT_SIZE_XS,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            min_lines=12,
            max_lines=20,
        )

        self.detail_dialog = ft.AlertDialog(
            modal=False,
            title=heading_text("Detalles de Auditoría", size=FONT_SIZE_LG),
            content=ft.Container(content=self.detail_content, width=500, padding=0),
            actions=[
                ft.TextButton(
                    "Cerrar",
                    on_click=self._close_detail_dialog,
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        header_row = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.SECURITY, color=ACCENT_PRIMARY, size=24),
                        heading_text("Auditoría / Logs de Seguridad", size=FONT_SIZE_LG),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    controls=[
                        self.count_label,
                        ft.IconButton(
                            icon=ft.Icons.REFRESH,
                            icon_color=TEXT_MUTED,
                            tooltip="Refrescar logs",
                            on_click=self._refresh,
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        filter_row = ft.Row(
            controls=[
                self.search_field,
                self.action_dropdown,
                self.user_dropdown,
                ButtonControl(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.FILTER_ALT_OFF, size=16),
                            ft.Text("Limpiar Filtros", size=FONT_SIZE_XS),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    bgcolor=BG_INPUT,
                    color=TEXT_PRIMARY,
                    on_click=self._clear_filters,
                    style=ft.ButtonStyle(
                        padding=ft.padding.symmetric(horizontal=12, vertical=10),
                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                    ),
                ),
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )

        table_header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text("Fecha / Hora", size=FONT_SIZE_XS, color=TEXT_MUTED, weight=ft.FontWeight.W_600, width=140),
                    ft.Text("Usuario", size=FONT_SIZE_XS, color=TEXT_MUTED, weight=ft.FontWeight.W_600, width=100),
                    ft.Text("Acción", size=FONT_SIZE_XS, color=TEXT_MUTED, weight=ft.FontWeight.W_600, width=180),
                    ft.Text("Detalles", size=FONT_SIZE_XS, color=TEXT_MUTED, weight=ft.FontWeight.W_600, expand=True),
                    ft.Text("IP", size=FONT_SIZE_XS, color=TEXT_MUTED, weight=ft.FontWeight.W_600, width=90),
                    ft.Container(width=40),
                ]
            ),
            padding=ft.padding.symmetric(horizontal=14, vertical=10),
            bgcolor=BG_BASE,
            border_radius=ft.BorderRadius.only(top_left=RADIUS_MD, top_right=RADIUS_MD) if hasattr(ft, "BorderRadius") else ft.border_radius.only(top_left=RADIUS_MD, top_right=RADIUS_MD),
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),

        )

        table_container = ft.Container(
            content=ft.Column([table_header, ft.Container(content=self.logs_table, expand=True)], spacing=0, expand=True),
            bgcolor=BG_CARD,
            border=ft.border.all(1, BORDER),
            border_radius=RADIUS_MD,
            expand=True,
            padding=0,
        )

        super().__init__(
            controls=[
                header_row,
                ft.Container(content=filter_row, padding=ft.padding.only(bottom=10)),
                table_container,
            ],
            spacing=10,
            expand=True,
        )
        self._load_filter_options()
        self._load_logs()

    def did_mount(self):
        try:
            if self.page and not self._dialog_attached:
                if self.detail_dialog not in self.page.overlay:
                    self.page.overlay.append(self.detail_dialog)
                self._dialog_attached = True
                self.page.update()
            self._load_filter_options()
            self._load_logs()
        except Exception as ex:
            print(f"[AuditLogsView.did_mount] Error: {ex}")

    def will_unmount(self):
        try:
            if self.page and self._dialog_attached:
                if self.detail_dialog in self.page.overlay:
                    self.page.overlay.remove(self.detail_dialog)
                self._dialog_attached = False
        except Exception:
            pass

    def _load_filter_options(self):
        try:
            actions = AuditLogRepository.list_actions()
            self.action_dropdown.options = [ft.dropdown.Option("Todas las Acciones")]
            for a in actions:
                self.action_dropdown.options.append(ft.dropdown.Option(a))

            users = AuditLogRepository.list_users()
            self.user_dropdown.options = [ft.dropdown.Option("Todos los Usuarios")]
            for u in users:
                self.user_dropdown.options.append(ft.dropdown.Option(u))

            self.action_dropdown.update()
            self.user_dropdown.update()
        except Exception:
            pass

    def _load_logs(self):
        try:
            action_val = self.action_dropdown.value
            user_val = self.user_dropdown.value
            search_val = (self.search_field.value or "").strip()

            action_filter = None if (not action_val or action_val == "Todas las Acciones") else action_val
            user_filter = None if (not user_val or user_val == "Todos los Usuarios") else user_val
            query_search = None if not search_val else search_val

            self._logs = AuditLogRepository.list_logs(
                limit=500,
                action_filter=action_filter,
                user_filter=user_filter,
                query_search=query_search,
            )
            self._render_logs()
        except Exception as ex:
            self.logs_table.controls = [
                ft.Container(
                    content=ft.Text(f"Error cargando logs: {ex}", size=FONT_SIZE_SM, color=ACCENT_DANGER),
                    padding=20,
                )
            ]
            if getattr(self, "page", None) is not None:
                try:
                    self.logs_table.update()
                except Exception:
                    pass

    def _render_logs(self):
        if not self._logs:
            self.logs_table.controls = [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.SECURITY, size=40, color=TEXT_MUTED),
                            ft.Text("No hay registros de auditoría", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight=ft.FontWeight.W_500),
                            ft.Text("Las acciones del sistema se registrarán aquí automáticamente", size=FONT_SIZE_SM, color=TEXT_MUTED),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    padding=40,
                    alignment=ft.Alignment.CENTER,
                )
            ]
            self.count_label.value = "0 registros"
            if getattr(self, "page", None) is not None:
                try:
                    self.logs_table.update()
                    self.count_label.update()
                except Exception:
                    pass
            return

        rows = []
        for log in self._logs:
            action = log.get("action", "")
            color, icon = _ACTION_STYLES.get(action, _DEFAULT_ACTION_STYLE)

            details_raw = log.get("details", "{}")
            details_preview = ""
            try:
                details_dict = json.loads(details_raw)
                if isinstance(details_dict, dict):
                    summary_parts = []
                    for k, v in list(details_dict.items())[:3]:
                        summary_parts.append(f"{k}: {v}")
                    details_preview = " · ".join(summary_parts)
                    if len(details_dict) > 3:
                        details_preview += "..."
                else:
                    details_preview = str(details_dict)
            except (json.JSONDecodeError, TypeError):
                details_preview = str(details_raw)

            if len(details_preview) > 80:
                details_preview = details_preview[:77] + "..."

            row = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            log.get("timestamp", "")[:19],
                            size=FONT_SIZE_XS,
                            color=TEXT_SECONDARY,
                            width=140,
                            font_family="Consolas, monospace",
                        ),
                        ft.Text(
                            log.get("username", "sistema"),
                            size=FONT_SIZE_SM,
                            color=TEXT_PRIMARY,
                            weight=ft.FontWeight.W_600,
                            width=100,
                        ),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Icon(icon, size=14, color=color),
                                    ft.Text(
                                        action.replace("_", " ").title(),
                                        size=FONT_SIZE_XS,
                                        color=color,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                ],
                                spacing=6,
                                tight=True,
                            ),
                            width=180,
                        ),
                        ft.Text(
                            details_preview,
                            size=FONT_SIZE_XS,
                            color=TEXT_MUTED,
                            expand=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            max_lines=1,
                        ),
                        ft.Text(
                            log.get("ip_address", "127.0.0.1"),
                            size=FONT_SIZE_XS,
                            color=TEXT_MUTED,
                            width=90,
                            font_family="Consolas, monospace",
                        ),
                        ft.IconButton(
                            icon=ft.Icons.VISIBILITY,
                            icon_size=16,
                            icon_color=ACCENT_PRIMARY,
                            tooltip="Ver detalles completos",
                            on_click=lambda e, l=log: self._show_detail(l),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                padding=ft.padding.symmetric(horizontal=14, vertical=6),
                border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                on_hover=self._on_row_hover,
            )
            rows.append(row)

        self.logs_table.controls = rows
        self.count_label.value = f"{len(self._logs)} registros"
        if getattr(self, "page", None) is not None:
            try:
                self.logs_table.update()
                self.count_label.update()
            except Exception:
                pass

    def _on_row_hover(self, e):
        try:
            e.control.bgcolor = BG_INPUT if e.data == "true" else None
            e.control.update()
        except Exception:
            pass

    def _show_detail(self, log: dict):
        try:
            details_raw = log.get("details", "{}")
            try:
                details_dict = json.loads(details_raw)
                formatted = json.dumps(details_dict, indent=2, ensure_ascii=False, default=str)
            except (json.JSONDecodeError, TypeError):
                formatted = str(details_raw)

            header = (
                f"Registro #{log.get('id', '?')}\n"
                f"Fecha: {log.get('timestamp', '')}\n"
                f"Usuario: {log.get('username', '')}\n"
                f"Acción: {log.get('action', '')}\n"
                f"IP: {log.get('ip_address', '')}\n"
                f"────────────────────────────────────────\n"
                f"Detalles:\n"
            )
            self.detail_content.value = header + formatted
            self.detail_content.update()

            if self._dialog_attached and self.page:
                self.detail_dialog.open = True
                self.page.update()
        except Exception as ex:
            print(f"[AuditLogsView._show_detail] Error: {ex}")

    def _close_detail_dialog(self, e):
        if self._dialog_attached and self.page:
            self.detail_dialog.open = False
            self.page.update()

    def _apply_filters(self, e):
        self._load_logs()

    def _clear_filters(self, e):
        try:
            self.search_field.value = ""
            self.action_dropdown.value = "Todas las Acciones"
            self.user_dropdown.value = "Todos los Usuarios"
            self.search_field.update()
            self.action_dropdown.update()
            self.user_dropdown.update()
            self._load_logs()
        except Exception:
            pass

    def _refresh(self, e):
        self._load_filter_options()
        self._load_logs()
