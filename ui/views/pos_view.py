"""POS view — quick sales point with persistent product inventory CRUD and bimonetary BCV calculations."""

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
    card_style,
    heading_text,
    label_text,
)
from core.mock_data import (
    POS_PRODUCTS,
    DAILY_SALES,
    add_or_update_product,
    remove_product,
)
from core.bcv_service import bcv_service
from core.business import compute_sales_summary, register_sale_rows
from core.event_bus import event_bus
from ui.components.widgets import POSProductRow


class POSView(ft.Column):
    """Point of sale with product inventory CRUD, form validations, and bimonetary USD/Bs. checkout."""

    def __init__(self):
        super().__init__(spacing=8, expand=True)

        self.cart_items = []
        self.cart_total = 0.0
        self._target_product_for_delete = None

        # Product management dialog fields
        self.prod_name_field = ft.TextField(
            label="Nombre del Producto",
            hint_text="Ej: Batido de Proteína 500ml",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )
        self.prod_price_field = ft.TextField(
            label="Precio ($)",
            hint_text="Ej: 2.50",
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.prod_stock_field = ft.TextField(
            label="Cantidad en Stock",
            hint_text="Ej: 20",
            keyboard_type=ft.KeyboardType.NUMBER,
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
            expand=1,
        )
        self.prod_cat_field = ft.Dropdown(
            label="Categoría",
            options=[
                ft.dropdown.Option("Bebidas"),
                ft.dropdown.Option("Suplementos"),
                ft.dropdown.Option("Snacks"),
                ft.dropdown.Option("Accesorios"),
                ft.dropdown.Option("General"),
            ],
            value="General",
            bgcolor=BG_INPUT,
            color=TEXT_PRIMARY,
            border_color=BORDER,
            border_radius=RADIUS_SM,
            text_size=14,
        )

        # Dialog for creating / editing product
        self.product_dialog_title = heading_text("Nuevo Producto", size=FONT_SIZE_LG)
        self.product_dialog = ft.AlertDialog(
            modal=True,
            title=self.product_dialog_title,
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        self.prod_name_field,
                        ft.Row(
                            controls=[self.prod_price_field, self.prod_stock_field],
                            spacing=10,
                        ),
                        self.prod_cat_field,
                    ],
                    spacing=12,
                    tight=True,
                ),
                padding=PADDING_MD,
                width=420,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.product_dialog)),
                ft.ElevatedButton(
                    "Guardar Producto",
                    bgcolor=ACCENT_PRIMARY,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_product_action,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # Dialog for deleting product
        self.delete_confirm_text = ft.Text("", size=13, color=TEXT_PRIMARY)
        self.delete_product_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Eliminar Producto", size=FONT_SIZE_LG),
            content=ft.Container(
                content=self.delete_confirm_text,
                padding=PADDING_MD,
                width=380,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._close_modal(self.delete_product_dialog)),
                ft.ElevatedButton(
                    "Eliminar",
                    bgcolor=ACCENT_DANGER,
                    color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._confirm_delete_product,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        # UI columns
        self.products_column = ft.Column(
            controls=self._build_product_rows(),
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        self.cart_list = ft.Column(
            controls=self._build_cart_rows(),
            spacing=8,
        )

        # Bimonetary total controls
        self.total_text = ft.Text("$0.00", size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w700")
        self.total_bs_text = ft.Text("Bs. 0,00", size=13, color=ACCENT_PRIMARY, weight="w600")

        self.sales_log = ft.Column(
            controls=self._build_sales_log(),
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        self.controls = [
            ft.Row(
                controls=[
                    heading_text("Punto de Venta e Inventario"),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.ADD_BOX, size=18, color=TEXT_PRIMARY),
                                ft.Text("Nuevo Producto", size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600"),
                            ],
                            spacing=6,
                        ),
                        bgcolor=ACCENT_PRIMARY,
                        style=ft.ButtonStyle(
                            padding=ft.padding.symmetric(horizontal=14, vertical=10),
                            shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                        ),
                        on_click=self._open_new_product_dialog,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(height=8),
            ft.Row(
                controls=[
                    # Column 1: Products in Stock
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        heading_text("Inventario / Stock", size=FONT_SIZE_MD),
                                        ft.Container(expand=True),
                                        ft.Text(f"{len(POS_PRODUCTS)} ítems", size=11, color=TEXT_MUTED),
                                    ],
                                ),
                                ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=4, bottom=8)),
                                self.products_column,
                            ],
                            spacing=8,
                        ),
                        expand=1,
                        **card_style(),
                    ),
                    # Column 2: Shopping Cart
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                heading_text("Carrito de Compra", size=FONT_SIZE_MD),
                                ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=12)),
                                self.cart_list,
                                ft.Container(height=1, bgcolor=BORDER),
                                ft.Row(
                                    controls=[
                                        ft.Column(
                                            controls=[
                                                label_text("Total a Cobrar"),
                                                self.total_bs_text,
                                            ],
                                            spacing=2,
                                        ),
                                        ft.Container(expand=True),
                                        self.total_text,
                                    ],
                                ),
                                ft.Container(height=8),
                                ft.ElevatedButton(
                                    content=ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.PAYMENTS_OUTLINED, size=18, color=TEXT_PRIMARY),
                                            ft.Text("Cobrar Venta", size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
                                        ],
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        spacing=8,
                                    ),
                                    bgcolor=ACCENT_SUCCESS,
                                    color=TEXT_PRIMARY,
                                    on_click=self._checkout,
                                    width=280,
                                    style=ft.ButtonStyle(
                                        padding=14,
                                        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
                                    ),
                                ),
                            ],
                            spacing=12,
                        ),
                        expand=1,
                        **card_style(),
                    ),
                    # Column 3: Daily Sales Log
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                heading_text("Ventas del Día", size=FONT_SIZE_MD),
                                ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=12)),
                                self.sales_log,
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
        ]

    def did_mount(self):
        event_bus.subscribe("sales_changed", self._on_sales_changed)
        event_bus.subscribe("bcv_updated", self._on_bcv_updated)

    def will_unmount(self):
        event_bus.unsubscribe("sales_changed", self._on_sales_changed)
        event_bus.unsubscribe("bcv_updated", self._on_bcv_updated)

    def _on_sales_changed(self, data=None):
        self._refresh_product_list()
        self.sales_log.controls = self._build_sales_log()
        if hasattr(self, "page") and self.page:
            try:
                self.sales_log.update()
            except Exception:
                pass

    def _on_bcv_updated(self, data=None):
        self._update_cart_totals()

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

    def _build_product_rows(self):
        rows = []
        for p in POS_PRODUCTS:
            stock = p.get("stock", 0)
            stock_color = ACCENT_SUCCESS if stock > 5 else (ACCENT_DANGER if stock == 0 else "#f59e0b")
            stock_badge = f"{stock} disp." if stock > 0 else "Agotado"

            rows.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                getattr(ft.Icons, p.get("icono", "INVENTORY"), ft.Icons.INVENTORY),
                                size=20,
                                color=ACCENT_PRIMARY,
                            ),
                            ft.Column(
                                controls=[
                                    ft.Text(p["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w600"),
                                    ft.Row(
                                        controls=[
                                            ft.Text(f"${p['precio']:.2f}", size=FONT_SIZE_XS, color=TEXT_SECONDARY),
                                            ft.Text("•", size=10, color=TEXT_MUTED),
                                            ft.Text(bcv_service.format_bs(bcv_service.to_bs(p["precio"])), size=11, color=ACCENT_PRIMARY),
                                            ft.Text("•", size=10, color=TEXT_MUTED),
                                            ft.Text(stock_badge, size=11, color=stock_color, weight="w600"),
                                        ],
                                        spacing=4,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            # Action buttons
                            ft.Row(
                                controls=[
                                    ft.IconButton(
                                        icon=ft.Icons.EDIT_OUTLINED,
                                        icon_size=16,
                                        icon_color=TEXT_SECONDARY,
                                        tooltip="Editar producto",
                                        on_click=lambda e, prod=p: self._open_edit_product_dialog(prod),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.DELETE_OUTLINE,
                                        icon_size=16,
                                        icon_color=ACCENT_DANGER,
                                        tooltip="Eliminar producto",
                                        on_click=lambda e, prod=p: self._open_delete_product_dialog(prod),
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.ADD_SHOPPING_CART,
                                        icon_size=18,
                                        icon_color=ACCENT_SUCCESS if stock > 0 else TEXT_MUTED,
                                        disabled=stock <= 0,
                                        tooltip="Agregar al carrito" if stock > 0 else "Sin stock",
                                        on_click=lambda e, prod=p: self._add_to_cart(prod, 1),
                                    ),
                                ],
                                spacing=0,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.padding.symmetric(horizontal=8, vertical=6),
                    bgcolor=BG_INPUT,
                    border_radius=RADIUS_SM,
                )
            )

        if not rows:
            rows.append(
                ft.Container(
                    content=label_text("Inventario vacío. Pulsa 'Nuevo Producto' para agregar uno.", color=TEXT_MUTED),
                    padding=PADDING_MD,
                )
            )
        return rows

    def _refresh_product_list(self):
        self.products_column.controls = self._build_product_rows()
        if hasattr(self, "page") and self.page:
            try:
                self.products_column.update()
            except Exception:
                pass

    def _open_new_product_dialog(self, e):
        self.product_dialog_title.value = "Nuevo Producto"
        self.prod_name_field.read_only = False
        self.prod_name_field.value = ""
        self.prod_price_field.value = ""
        self.prod_stock_field.value = ""
        self.prod_cat_field.value = "General"
        self._open_modal(self.product_dialog)

    def _open_edit_product_dialog(self, product: dict):
        self.product_dialog_title.value = f"Editar: {product['nombre']}"
        self.prod_name_field.value = product.get("nombre", "")
        self.prod_name_field.read_only = True
        self.prod_price_field.value = str(product.get("precio", 0.0))
        self.prod_stock_field.value = str(product.get("stock", 0))
        self.prod_cat_field.value = product.get("categoria", "General")
        self._open_modal(self.product_dialog)

    def _save_product_action(self, e):
        nombre = (self.prod_name_field.value or "").strip()
        if not nombre or len(nombre) < 2:
            self._show_notification("El nombre del producto debe tener al menos 2 letras", ACCENT_DANGER)
            return

        try:
            precio = float(self.prod_price_field.value or 0.0)
            if precio <= 0:
                self._show_notification("El precio debe ser mayor a 0.00", ACCENT_DANGER)
                return
        except ValueError:
            self._show_notification("El precio debe ser un número válido (ej: 2.50)", ACCENT_DANGER)
            return

        try:
            stock = int(self.prod_stock_field.value or 0)
            if stock < 0:
                self._show_notification("El stock no puede ser negativo", ACCENT_DANGER)
                return
        except ValueError:
            self._show_notification("El stock debe ser un número entero (ej: 10)", ACCENT_DANGER)
            return

        cat = (self.prod_cat_field.value or "General").strip()

        add_or_update_product({
            "nombre": nombre,
            "precio": precio,
            "stock": stock,
            "categoria": cat,
        })

        self._refresh_product_list()
        self._close_modal(self.product_dialog)
        self._show_notification(f"Producto '{nombre}' guardado exitosamente.", ACCENT_SUCCESS)

    def _open_delete_product_dialog(self, product: dict):
        self._target_product_for_delete = product
        self.delete_confirm_text.value = f"¿Está seguro de eliminar '{product['nombre']}' del inventario?"
        self._open_modal(self.delete_product_dialog)

    def _confirm_delete_product(self, e):
        prod = self._target_product_for_delete
        if not prod:
            return

        nombre = prod.get("nombre", "")
        remove_product(nombre)
        self._refresh_product_list()
        self._close_modal(self.delete_product_dialog)
        self._show_notification(f"Producto '{nombre}' eliminado del inventario", ACCENT_DANGER)

    def _build_cart_rows(self):
        if not self.cart_items:
            return [label_text("Carrito vacío", color=TEXT_MUTED)]
        rows = []
        for item in self.cart_items:
            bs_subtotal = bcv_service.to_bs(item["subtotal"])
            rows.append(
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(item["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500"),
                                ft.Text(f"x{item['qty']} · {bcv_service.format_bs(bs_subtotal)}", size=11, color=TEXT_MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Text(f"${item['subtotal']:.2f}", size=FONT_SIZE_SM, color=ACCENT_PRIMARY, weight="w600"),
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                            icon_size=18,
                            icon_color=ACCENT_DANGER,
                            tooltip="Quitar 1",
                            on_click=lambda e, it=item: self._remove_from_cart(it),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
        return rows

    def _build_sales_log(self):
        rows = []
        for sale in DAILY_SALES:
            monto = float(sale.get("monto", 0))
            rows.append(
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(sale["producto"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500"),
                                ft.Text(bcv_service.format_bs(bcv_service.to_bs(monto)), size=11, color=TEXT_MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Text(sale.get("hora", ""), size=FONT_SIZE_XS, color=TEXT_MUTED),
                        ft.Text(f"${monto:.2f}", size=FONT_SIZE_SM, color=ACCENT_SUCCESS, weight="w600"),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
        if not rows:
            rows.append(label_text("Sin ventas hoy todavía", color=TEXT_MUTED))
        return rows

    def _add_to_cart(self, producto, qty):
        prod_stock = producto.get("stock", 0)
        existing = next((c for c in self.cart_items if c["nombre"] == producto["nombre"]), None)
        current_cart_qty = existing["qty"] if existing else 0

        if current_cart_qty + qty > prod_stock:
            self._show_notification(f"Stock insuficiente. Solo quedan {prod_stock} unidades.", ACCENT_DANGER)
            return

        if existing:
            existing["qty"] += qty
            existing["subtotal"] = existing["qty"] * producto["precio"]
        else:
            self.cart_items.append({
                "nombre": producto["nombre"],
                "qty": qty,
                "precio": producto["precio"],
                "subtotal": qty * producto["precio"],
            })

        self._update_cart_totals()

    def _remove_from_cart(self, item: dict):
        if item["qty"] > 1:
            item["qty"] -= 1
            item["subtotal"] = item["qty"] * item["precio"]
        else:
            self.cart_items.remove(item)

        self._update_cart_totals()

    def _update_cart_totals(self):
        self.cart_total = compute_sales_summary(self.cart_items)["total"]
        rate = bcv_service.get_rate()
        total_bs = bcv_service.to_bs(self.cart_total)
        self.total_text.value = f"${self.cart_total:.2f}"
        self.total_bs_text.value = f"Bs. {total_bs:,.2f} ({rate:.2f} Bs/$)"
        self.cart_list.controls = self._build_cart_rows()
        if hasattr(self, "page") and self.page:
            try:
                self.cart_list.update()
                self.total_text.update()
                self.total_bs_text.update()
            except Exception:
                pass

    def _checkout(self, e):
        if not self.cart_items:
            self._show_notification("El carrito está vacío", ACCENT_DANGER)
            return

        total_sold = self.cart_total
        total_bs = bcv_service.to_bs(total_sold)

        for item in register_sale_rows(self.cart_items):
            self.sales_log.controls.insert(
                0,
                ft.Row(
                    controls=[
                        ft.Column(
                            controls=[
                                ft.Text(item["producto"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500"),
                                ft.Text(bcv_service.format_bs(bcv_service.to_bs(item["monto"])), size=11, color=TEXT_MUTED),
                            ],
                            spacing=1,
                            expand=True,
                        ),
                        ft.Text(item["hora"], size=FONT_SIZE_XS, color=TEXT_MUTED),
                        ft.Text(f"${item['monto']:.2f}", size=FONT_SIZE_SM, color=ACCENT_SUCCESS, weight="w600"),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            )

        self.cart_items = []
        self.cart_total = 0.0
        self.total_text.value = "$0.00"
        self.total_bs_text.value = "Bs. 0,00"
        self.cart_list.controls = self._build_cart_rows()

        # Update product inventory stock display
        self._refresh_product_list()

        if hasattr(self, "page") and self.page:
            try:
                self.cart_list.update()
                self.total_text.update()
                self.total_bs_text.update()
                self.sales_log.update()
            except Exception:
                pass

        self._show_notification(
            f"Venta procesada con éxito: ${total_sold:.2f} / {bcv_service.format_bs(total_bs)}",
            ACCENT_SUCCESS,
        )

    def _show_notification(self, message: str, color: str):
        if hasattr(self, "page") and self.page:
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(message, color=TEXT_PRIMARY),
                bgcolor=color,
            )
            self.page.snack_bar.open = True
            self.page.update()
