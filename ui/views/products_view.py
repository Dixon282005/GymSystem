"""POS inventory products management view.
Allows adding, modifying, activating/deactivating, and tracking stock of POS goods.
"""

from __future__ import annotations

import flet as ft

from core.event_bus import event_bus
from core.repositories import POSProductRepository
from core.theme import (
    ACCENT_DANGER,
    ACCENT_PRIMARY,
    ACCENT_SUCCESS,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FONT_SIZE_LG,
    FONT_SIZE_MD,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
    RADIUS_MD,
    RADIUS_SM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    button_outline,
    button_primary,
    card_style,
    heading_text,
    show_snack,
)


class ProductsView(ft.Column):
    def __init__(self):
        self.edit_mode = False
        self.selected_product_name = None

        self.pos_name = ft.TextField(
            label="Producto",
            hint_text="Agua 500ml",
            width=220,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
        )
        self.pos_price = ft.TextField(
            label="Precio ($)",
            hint_text="1.50",
            width=130,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^\d*\.?\d{0,2}$", replacement_string=""),
        )
        self.pos_stock = ft.TextField(
            label="Stock",
            hint_text="100",
            width=110,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.pos_is_active = ft.Switch(
            label="Activo",
            value=True,
            active_color=ACCENT_PRIMARY,
        )
        self.save_btn = button_primary("Guardar producto", on_click=self._save_pos)
        self.cancel_btn = button_outline("Cancelar", on_click=self._cancel_edit, visible=False)

        form_row = ft.Row(
            controls=[
                self.pos_name,
                self.pos_price,
                self.pos_stock,
                self.pos_is_active,
                self.save_btn,
                self.cancel_btn,
            ],
            wrap=True,
            spacing=10,
        )

        create_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Crear / Editar Producto", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                    form_row,
                ],
                spacing=12,
            ),
            **card_style(),
        )

        self.pos_list = ft.Column(spacing=6)

        list_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Productos Registrados", size=FONT_SIZE_MD, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
                    self.pos_list,
                ],
                spacing=12,
            ),
            **card_style(),
        )

        self._refresh_pos()

        super().__init__(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INVENTORY, color=ACCENT_PRIMARY, size=24),
                        heading_text("Inventario - Productos POS", size=FONT_SIZE_LG),
                    ],
                    spacing=8,
                ),
                create_card,
                list_card,
            ],
            spacing=14,
            expand=True,
            scroll=ft.ScrollMode.AUTO,
        )

    def _refresh_pos(self):
        try:
            products = POSProductRepository.list_products(active_only=False)
            if not products:
                self.pos_list.controls = [
                    ft.Text("Sin productos registrados", color=TEXT_MUTED, size=FONT_SIZE_SM)
                ]
                return

            rows = []
            for p in products:
                is_active = p.get("is_active", True)
                status_color = ACCENT_SUCCESS if is_active else ACCENT_DANGER
                status_text = "Activo" if is_active else "Inactivo"

                status_badge = ft.Container(
                    content=ft.Text(status_text, size=FONT_SIZE_XS, color="#ffffff", weight=ft.FontWeight.W_600),
                    bgcolor=status_color,
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    border_radius=RADIUS_SM,
                    alignment=ft.Alignment.CENTER,
                )

                action_text = "Desactivar" if is_active else "Activar"
                action_color = ACCENT_DANGER if is_active else ACCENT_SUCCESS

                nombre = p.get("nombre", "")
                precio = float(p.get("precio", 0.0))
                stock = int(p.get("stock", 0))

                row = ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text(nombre, color=TEXT_PRIMARY, size=FONT_SIZE_SM, weight=ft.FontWeight.W_600),
                                    ft.Text(f"Stock: {stock}", color=TEXT_SECONDARY, size=FONT_SIZE_XS),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            status_badge,
                            ft.Text(
                                f"${precio:.2f}",
                                color=ACCENT_PRIMARY,
                                size=FONT_SIZE_SM,
                                weight=ft.FontWeight.W_700,
                            ),
                            ft.TextButton(
                                "Editar",
                                on_click=self._mk_edit_pos(p),
                            ),
                            ft.TextButton(
                                action_text,
                                on_click=self._toggle_product_active(nombre, is_active),
                                style=ft.ButtonStyle(color=action_color),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    bgcolor=BG_INPUT,
                    border=ft.border.all(1, BORDER),
                    border_radius=RADIUS_SM,
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                )
                rows.append(row)

            self.pos_list.controls = rows
        except Exception as ex:
            self.pos_list.controls = [
                ft.Text(f"Error cargando productos: {ex}", color=ACCENT_DANGER, size=FONT_SIZE_SM)
            ]

    def _mk_edit_pos(self, product: dict):
        def handler(e):
            self.edit_mode = True
            self.selected_product_name = product.get("nombre")
            self.pos_name.value = product.get("nombre", "")
            self.pos_name.disabled = False
            self.pos_price.value = str(product.get("precio", 0.0))
            self.pos_stock.value = str(product.get("stock", 0))
            self.pos_is_active.value = bool(product.get("is_active", True))
            self.save_btn.text = "Actualizar producto"
            self.cancel_btn.visible = True
            self.update()
        return handler

    def _cancel_edit(self, e=None):
        self.edit_mode = False
        self.selected_product_name = None
        self.pos_name.value = ""
        self.pos_name.disabled = False
        self.pos_name.error_text = None
        self.pos_price.value = ""
        self.pos_price.error_text = None
        self.pos_stock.value = ""
        self.pos_stock.error_text = None
        self.pos_is_active.value = True
        self.save_btn.text = "Guardar producto"
        self.cancel_btn.visible = False
        self.update()

    def _toggle_product_active(self, nombre: str, current_active: bool):
        def handler(e):
            new_active = not current_active
            ok, msg = POSProductRepository.set_product_active(nombre, new_active)
            if self.page:
                show_snack(self.page, msg)
            event_bus.publish("pos_products_changed", {})
            self._refresh_pos()
            self.pos_list.update()
        return handler

    def _save_pos(self, e):
        self.pos_name.error_text = None
        self.pos_price.error_text = None
        self.pos_stock.error_text = None

        has_error = False
        name = (self.pos_name.value or "").strip()
        if not name:
            self.pos_name.error_text = "El nombre es obligatorio"
            has_error = True

        raw_price = (self.pos_price.value or "").strip()
        try:
            price = float(raw_price or 0.0)
            if price < 0:
                self.pos_price.error_text = "El precio no puede ser negativo"
                has_error = True
        except ValueError:
            self.pos_price.error_text = "Precio numérico inválido"
            has_error = True

        raw_stock = (self.pos_stock.value or "").strip()
        try:
            stock = int(raw_stock or 0)
            if stock < 0:
                self.pos_stock.error_text = "El stock no puede ser negativo"
                has_error = True
        except ValueError:
            self.pos_stock.error_text = "Stock numérico entero inválido"
            has_error = True

        if has_error:
            self.pos_name.update()
            self.pos_price.update()
            self.pos_stock.update()
            return

        old_name = self.selected_product_name if self.edit_mode else None
        ok, msg = POSProductRepository.save_product(
            nombre=name,
            precio=price,
            stock=stock,
            is_active=bool(self.pos_is_active.value),
            old_name=old_name,
        )
        if self.page:
            show_snack(self.page, msg)

        event_bus.publish("pos_products_changed", {})
        self._cancel_edit()
        self._refresh_pos()
        self.pos_list.update()
