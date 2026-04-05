"""POS view — quick sales point."""

import flet as ft
from core.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, RADIUS_SM, PADDING_MD,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_XL,
    card_style, heading_text, label_text,
)
from core.business import compute_sales_summary, register_sale_rows
from core.repositories import SalesRepository, POSProductRepository
from ui.components.widgets import POSProductRow


def _snack(page, msg, color="#0f766e"):
    try:
        sb = ft.SnackBar(content=ft.Text(msg, color=TEXT_PRIMARY), bgcolor=color)
        page.overlay.append(sb)
        sb.open = True
        page.update()
    except Exception:
        pass


class POSView(ft.Column):
    def __init__(self):
        self.cart_items = []
        self.cart_total = 0.0
        self.cart_list = ft.Column(controls=[label_text("Carrito vacio", color=TEXT_MUTED)], spacing=8)
        self.total_text = ft.Text("$0.00", size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w700")
        self.sales_log = ft.Column(controls=self._build_sales(), spacing=8, scroll=ft.ScrollMode.AUTO)

        try:
            products = POSProductRepository.list_products()
            product_rows = [POSProductRow(p, on_add=self._add_to_cart) for p in products]
            if not product_rows:
                product_rows = [ft.Text("No hay productos disponibles.", color=TEXT_MUTED, size=FONT_SIZE_SM)]
        except Exception:
            product_rows = [ft.Text("Error cargando productos.", color="#7f1d1d", size=FONT_SIZE_SM)]

        super().__init__(controls=[
            heading_text("Punto de Venta"),
            ft.Container(height=8),
            ft.Row(controls=[
                ft.Container(content=ft.Column(controls=[
                    heading_text("Productos", size=FONT_SIZE_MD),
                    ft.Container(height=1, bgcolor=BORDER),
                    *product_rows,
                ], spacing=8, scroll=ft.ScrollMode.AUTO), expand=1, **card_style()),
                ft.Container(content=ft.Column(controls=[
                    heading_text("Carrito", size=FONT_SIZE_MD),
                    ft.Container(height=1, bgcolor=BORDER),
                    self.cart_list,
                    ft.Container(height=1, bgcolor=BORDER),
                    ft.Row(controls=[label_text("Total"), ft.Container(expand=True), self.total_text]),
                    ft.Container(height=8),
                    ft.ElevatedButton(
                        content=ft.Row(controls=[
                            ft.Icon(ft.Icons.RECEIPT_LONG, size=18, color=TEXT_PRIMARY),
                            ft.Text("Cobrar", size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
                        ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                        bgcolor=ACCENT_SUCCESS, color=TEXT_PRIMARY, on_click=self._checkout, width=280,
                        style=ft.ButtonStyle(padding=14, shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    ),
                ], spacing=12, scroll=ft.ScrollMode.AUTO), expand=1, **card_style()),
                ft.Container(content=ft.Column(controls=[
                    heading_text("Ventas del Dia", size=FONT_SIZE_MD),
                    ft.Container(height=1, bgcolor=BORDER),
                    self.sales_log,
                ], spacing=8), expand=1, **card_style()),
            ], spacing=16, expand=True),
        ], spacing=8, expand=True)

    def _build_sales(self):
        try:
            sales = SalesRepository.list_recent(limit=100)
            if not sales:
                return [ft.Text("No hay ventas hoy.", color=TEXT_MUTED, size=FONT_SIZE_SM)]
            return [ft.Row(controls=[
                ft.Text(s["producto"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, expand=True),
                ft.Text(s["hora"], size=FONT_SIZE_XS, color=TEXT_MUTED),
                ft.Text(f"${s['monto']:.2f}", size=FONT_SIZE_SM, color=ACCENT_SUCCESS, weight="w600"),
            ]) for s in sales]
        except Exception:
            return [ft.Text("Error cargando ventas.", color="#7f1d1d", size=FONT_SIZE_SM)]

    def _build_cart(self):
        if not self.cart_items:
            return [label_text("Carrito vacio", color=TEXT_MUTED)]
        return [ft.Row(controls=[
            ft.Text(i["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, expand=True),
            ft.Text(f"x{i['qty']}", size=FONT_SIZE_SM, color=TEXT_SECONDARY),
            ft.Text(f"${i['subtotal']:.2f}", size=FONT_SIZE_SM, color=ACCENT_PRIMARY, weight="w600"),
        ]) for i in self.cart_items]

    def _add_to_cart(self, producto, qty):
        try:
            ex = next((c for c in self.cart_items if c["nombre"] == producto["nombre"]), None)
            if ex:
                ex["qty"] += qty
                ex["subtotal"] = ex["qty"] * producto["precio"]
            else:
                self.cart_items.append({"nombre": producto["nombre"], "qty": qty, "precio": producto["precio"], "subtotal": qty * producto["precio"]})
            self.cart_total = compute_sales_summary(self.cart_items)["total"]
            self.total_text.value = f"${self.cart_total:.2f}"
            self.cart_list.controls = self._build_cart()
            self.cart_list.update()
            self.total_text.update()
        except Exception as ex:
            _snack(self.page, f"Error agregando al carrito: {ex}", "#7f1d1d")

    def _checkout(self, e):
        try:
            if not self.cart_items:
                _snack(self.page, "El carrito esta vacio", "#7f1d1d")
                return
            
            rows_added = register_sale_rows(self.cart_items)
            
            # Rebuild sales log completely to ensure it's up to date and correct types
            self.sales_log.controls = self._build_sales()

            self.cart_items = []
            self.cart_total = 0.0
            self.total_text.value = "$0.00"
            self.cart_list.controls = self._build_cart()
            
            self.cart_list.update()
            self.total_text.update()
            self.sales_log.update()
            _snack(self.page, "Venta registrada exitosamente", "#0f766e")
        except Exception as ex:
            _snack(self.page, f"Error al procesar venta: {ex}", "#7f1d1d")
