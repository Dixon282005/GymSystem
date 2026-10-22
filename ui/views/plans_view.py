"""Plans view — complete CRUD for gym membership plans with bimonetary BCV calculation."""

from __future__ import annotations

import flet as ft
from core.theme import (
    BG_CARD,
    BG_INPUT,
    BORDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    ACCENT_WARNING,
    ACCENT_DANGER,
    RADIUS_SM,
    RADIUS_MD,
    PADDING_MD,
    PADDING_LG,
    FONT_SIZE_XS,
    FONT_SIZE_SM,
    FONT_SIZE_MD,
    FONT_SIZE_LG,
    FONT_SIZE_XL,
    FONT_SIZE_2XL,
    card_style,
    heading_text,
    button_primary,
    label_text,
)
from core.db_store import load_plans, save_plan, delete_plan
from core.bcv_service import bcv_service
from core.event_bus import event_bus


class PlansView(ft.Column):
    """Gym membership plans management view with bimonetary USD / VES pricing."""

    def __init__(self):
        super().__init__(spacing=10, expand=True, scroll=ft.ScrollMode.AUTO)

        self._target_plan_for_delete = None

        # Modal fields for creating / editing plan
        self.modal_title = heading_text("Nuevo Plan de Membresía", size=FONT_SIZE_LG)
        self.plan_name_field = ft.TextField(
            label="Nombre del Plan",
            hint_text="Ej: Mensual Completo, Quincenal, Pase Diario",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.plan_price_field = ft.TextField(
            label="Precio en USD ($)",
            hint_text="Ej: 30.00",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^\d*\.?\d{0,2}$", replacement_string=""),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
            on_change=self._on_modal_price_change,
        )
        self.plan_days_field = ft.TextField(
            label="Duración (Días)",
            hint_text="Ej: 30",
            value="30",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.plan_desc_field = ft.TextField(
            label="Descripción / Beneficios incluidos",
            hint_text="Ej: Acceso libre a máquinas, pesas y lockers",
            multiline=True,
            min_lines=2,
            max_lines=3,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=13,
        )
        self.modal_bs_preview = ft.Text("Equivalente Bs: 0,00", size=13, color=ACCENT_PRIMARY, weight="w600")

        # Create / Edit Dialog
        self.plan_dialog = ft.AlertDialog(
            modal=True,
            title=self.modal_title,
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.plan_name_field,
                        ft.Row(
                            controls=[self.plan_price_field, self.plan_days_field],
                            spacing=10,
                        ),
                        self.modal_bs_preview,
                        self.plan_desc_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                width=450,
                padding=PADDING_MD,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.plan_dialog)),
                ft.ElevatedButton(
                    "Guardar Plan",
                    bgcolor=ACCENT_PRIMARY,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_plan_action,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # Delete confirmation dialog
        self.delete_confirm_text = ft.Text("", size=13, color=TEXT_PRIMARY)
        self.delete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ACCENT_DANGER, size=24),
                    heading_text("Confirmar Eliminación", size=FONT_SIZE_MD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=self.delete_confirm_text,
                padding=PADDING_MD,
                width=380,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.delete_dialog)),
                ft.ElevatedButton(
                    "Eliminar Plan",
                    bgcolor=ACCENT_DANGER,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._confirm_delete_plan,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # Plans cards container
        self.plans_grid = ft.Row(
            controls=self._build_plan_cards(),
            wrap=True,
            spacing=16,
        )

        # Header with BCV badge
        self.bcv_badge = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.CURRENCY_EXCHANGE, size=16, color=ACCENT_PRIMARY),
                    ft.Text(f"Tasa BCV: {bcv_service.get_rate():.2f} Bs/$", size=12, color=TEXT_MUTED),
                ],
                spacing=6,
            ),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border_radius=RADIUS_SM,
        )

        self.controls = [
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            heading_text("Planes de Gimnasio y Membresías"),
                            ft.Text("Configura las tarifas, duración y beneficios para socios", size=12, color=TEXT_MUTED),
                        ],
                        spacing=2,
                    ),
                    ft.Container(expand=True),
                    self.bcv_badge,
                    button_primary(
                        "Nuevo Plan",
                        icon=ft.Icons.ADD_CARD,
                        on_click=self._open_new_plan_dialog,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(height=8),
            self.plans_grid,
        ]

    def did_mount(self):
        event_bus.subscribe("plans_changed", self._on_plans_changed)
        event_bus.subscribe("bcv_updated", self._on_bcv_updated)

    def will_unmount(self):
        event_bus.unsubscribe("plans_changed", self._on_plans_changed)
        event_bus.unsubscribe("bcv_updated", self._on_bcv_updated)
        self.page = None

    def _on_plans_changed(self, data=None):
        if getattr(self, "page", None) is None:
            return
        self._refresh_plans()

    def _on_bcv_updated(self, rate=None):
        if getattr(self, "page", None) is None:
            return
        curr_rate = bcv_service.get_rate()
        self.bcv_badge.content = ft.Row(
            controls=[
                ft.Icon(ft.Icons.CURRENCY_EXCHANGE, size=16, color=ACCENT_PRIMARY),
                ft.Text(f"Tasa BCV: {curr_rate:.2f} Bs/$", size=12, color=TEXT_MUTED),
            ],
            spacing=6,
        )
        self._refresh_plans()

    def _refresh_plans(self):
        self.plans_grid.controls = self._build_plan_cards()
        if hasattr(self, "page") and self.page:
            try:
                self.bcv_badge.update()
                self.plans_grid.update()
            except Exception:
                pass

    def _build_plan_cards(self):
        plans = load_plans(active_only=True)
        cards = []

        for p in plans:
            precio = float(p.get("precio", 0.0))
            dias = int(p.get("dias", 30))
            precio_bs = bcv_service.to_bs(precio)
            descripcion = p.get("descripcion") or "Acceso a instalaciones del gimnasio"

            # Duration badge formatting
            if dias == 1:
                dur_label = "1 Día"
            elif dias == 7:
                dur_label = "1 Semana"
            elif dias == 15:
                dur_label = "Quincenal (15d)"
            elif dias == 30:
                dur_label = "1 Mes (30d)"
            elif dias == 90:
                dur_label = "Trimestre (90d)"
            elif dias == 180:
                dur_label = "Semestre (180d)"
            elif dias == 365:
                dur_label = "1 Año (365d)"
            else:
                dur_label = f"{dias} Días"

            card = ft.Container(
                content=ft.Column(
                    controls=[
                        # Top row: Plan Name + Duration Badge
                        ft.Row(
                            controls=[
                                ft.Text(p["nombre"], size=16, color=TEXT_PRIMARY, weight="w700", expand=True),
                                ft.Container(
                                    content=ft.Text(dur_label, size=10, color=ACCENT_PRIMARY, weight="w700"),
                                    bgcolor=ft.Colors.with_opacity(0.15, ACCENT_PRIMARY),
                                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                                    border_radius=12,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Container(height=4),
                        # Price in USD ($)
                        ft.Row(
                            controls=[
                                ft.Text(f"${precio:.2f}", size=28, color=ACCENT_SUCCESS, weight="w800"),
                                ft.Text("/ ciclo", size=12, color=TEXT_MUTED),
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.END,
                            spacing=4,
                        ),
                        # Price in Bs (Official BCV)
                        ft.Text(
                            bcv_service.format_bs(precio_bs),
                            size=13,
                            color=ACCENT_PRIMARY,
                            weight="w600",
                        ),
                        ft.Container(height=4),
                        ft.Container(height=1, bgcolor=BORDER),
                        ft.Container(height=4),
                        # Description / Benefits
                        ft.Text(
                            descripcion,
                            size=12,
                            color=TEXT_SECONDARY,
                            max_lines=3,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Container(expand=True),
                        # Action buttons
                        ft.Row(
                            controls=[
                                ft.OutlinedButton(
                                    content=ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.EDIT_OUTLINED, size=14, color=TEXT_SECONDARY),
                                            ft.Text("Editar", size=12, color=TEXT_SECONDARY),
                                        ],
                                        spacing=4,
                                    ),
                                    style=ft.ButtonStyle(
                                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                        side=ft.BorderSide(1, BORDER),
                                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                    ),
                                    on_click=lambda e, pl=p: self._open_edit_plan_dialog(pl),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    icon_size=18,
                                    icon_color=ACCENT_DANGER,
                                    tooltip="Eliminar plan",
                                    on_click=lambda e, pl=p: self._open_delete_plan_dialog(pl),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=6,
                ),
                width=270,
                height=230,
                padding=16,
                bgcolor=BG_CARD,
                border=ft.Border.all(1, BORDER),
                border_radius=RADIUS_MD,
            )
            cards.append(card)

        if not cards:
            cards.append(
                ft.Container(
                    content=ft.Text("No hay planes configurados. Pulsa 'Nuevo Plan' para crear uno.", color=TEXT_MUTED),
                    padding=20,
                )
            )
        return cards

    def _open_modal(self, dialog):
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "show_dialog"):
                try:
                    self.page.show_dialog(dialog)
                    return
                except Exception:
                    pass
            self.page.dialog = dialog
            dialog.open = True
            self.page.update()

    def _close_modal(self, dialog):
        if hasattr(self, "page") and self.page:
            if hasattr(self.page, "pop_dialog"):
                try:
                    self.page.pop_dialog()
                    return
                except Exception:
                    pass
            dialog.open = False
            self.page.update()

    def _on_modal_price_change(self, e):
        try:
            val = float(self.plan_price_field.value or 0.0)
        except Exception:
            val = 0.0
        bs_val = bcv_service.to_bs(val)
        self.modal_bs_preview.value = f"Equivalente Bs: {bcv_service.format_bs(bs_val)} ({bcv_service.get_rate():.2f} Bs/$)"
        if hasattr(self, "page") and self.page:
            try:
                self.modal_bs_preview.update()
            except Exception:
                pass

    def _open_new_plan_dialog(self, e):
        self.modal_title.value = "Nuevo Plan de Membresía"
        self.plan_name_field.read_only = False
        self.plan_name_field.value = ""
        self.plan_name_field.error_text = None
        self.plan_price_field.value = "30.00"
        self.plan_price_field.error_text = None
        self.plan_days_field.value = "30"
        self.plan_days_field.error_text = None
        self.plan_desc_field.value = ""
        self._on_modal_price_change(None)
        self._open_modal(self.plan_dialog)

    def _open_edit_plan_dialog(self, plan: dict):
        self.modal_title.value = f"Editar Plan: {plan['nombre']}"
        self.plan_name_field.value = plan.get("nombre", "")
        self.plan_name_field.read_only = True
        self.plan_name_field.error_text = None
        self.plan_price_field.value = f"{float(plan.get('precio', 0.0)):.2f}"
        self.plan_price_field.error_text = None
        self.plan_days_field.value = str(plan.get("dias", 30))
        self.plan_days_field.error_text = None
        self.plan_desc_field.value = plan.get("descripcion", "")
        self._on_modal_price_change(None)
        self._open_modal(self.plan_dialog)

    def _save_plan_action(self, e):
        self.plan_name_field.error_text = None
        self.plan_price_field.error_text = None
        self.plan_days_field.error_text = None

        has_error = False
        nombre = (self.plan_name_field.value or "").strip()
        if not nombre or len(nombre) < 2:
            self.plan_name_field.error_text = "El nombre del plan debe tener al menos 2 letras"
            has_error = True

        raw_price = (self.plan_price_field.value or "").strip()
        try:
            precio = float(raw_price or 0.0)
            if precio < 0:
                self.plan_price_field.error_text = "El precio no puede ser negativo"
                has_error = True
        except ValueError:
            self.plan_price_field.error_text = "Precio numérico inválido (ej: 30.00)"
            has_error = True

        raw_days = (self.plan_days_field.value or "").strip()
        try:
            dias = int(raw_days or 30)
            if dias <= 0:
                self.plan_days_field.error_text = "La duración debe ser al menos 1 día"
                has_error = True
        except ValueError:
            self.plan_days_field.error_text = "La duración debe ser un número entero (ej: 30)"
            has_error = True

        if has_error:
            self.plan_name_field.update()
            self.plan_price_field.update()
            self.plan_days_field.update()
            return

        descripcion = (self.plan_desc_field.value or "").strip()

        plan_data = {
            "nombre": nombre,
            "precio": precio,
            "dias": dias,
            "descripcion": descripcion,
            "is_active": 1,
        }
        saved = save_plan(plan_data)
        if not saved:
            self._show_notification("Error al guardar el plan", ACCENT_DANGER)
            return

        # Sync in-memory PLANS
        try:
            from core import mock_data as md
            md.PLANS[nombre] = {
                "precio": precio,
                "dias": dias,
                "descripcion": descripcion,
            }
        except Exception:
            pass

        event_bus.publish("plans_changed", plan_data)
        self._refresh_plans()
        self._close_modal(self.plan_dialog)
        self._show_notification(f"Plan '{nombre}' guardado exitosamente", ACCENT_SUCCESS)

    def _open_delete_plan_dialog(self, plan: dict):
        self._target_plan_for_delete = plan
        self.delete_confirm_text.value = f"¿Está seguro de eliminar el plan '{plan.get('nombre')}'? Los socios inscritos mantendrán su vigencia."
        self._open_modal(self.delete_dialog)

    def _confirm_delete_plan(self, e):
        plan = self._target_plan_for_delete
        if not plan:
            return

        nombre = plan.get("nombre", "")
        delete_plan(nombre)

        # Remove from in-memory PLANS
        try:
            from core import mock_data as md
            md.PLANS.pop(nombre, None)
        except Exception:
            pass

        event_bus.publish("plans_changed", {"deleted": nombre})
        self._refresh_plans()
        self._close_modal(self.delete_dialog)
        self._show_notification(f"Plan '{nombre}' eliminado correctamente", ACCENT_SUCCESS)

    def _show_notification(self, message: str, color: str):
        if hasattr(self, "page") and self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=TEXT_PRIMARY),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            try:
                self.page.update()
            except Exception:
                pass
