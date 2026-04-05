"""POS view — quick sales point for daily cash register."""

import flet as ft
from core.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS,
    RADIUS_SM, RADIUS_MD, PADDING_MD, PADDING_LG,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG, FONT_SIZE_XL,
    card_style, heading_text, label_text,
)
from core.mock_data import POS_PRODUCTS, DAILY_SALES
from core.business import compute_sales_summary, register_sale_rows
from ui.components.widgets import POSProductRow


class POSView(ft.Column):
    """Point of sale with product grid and cart."""

    def __init__(self):
        self.cart_items = []
        self.cart_total = 0.0

        self.cart_list = ft.Column(
            controls=self._build_cart_rows(),
            spacing=8,
        )

        self.total_text = ft.Text("$0.00", size=FONT_SIZE_XL, color=TEXT_PRIMARY, weight="w700")

        self.sales_log = ft.Column(
            controls=self._build_sales_log(),
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        super().__init__(
            controls=[
                heading_text("Punto de Venta"),
                ft.Container(height=8),
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    heading_text("Productos", size=FONT_SIZE_MD),
                                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=12)),
                                    *[POSProductRow(p, on_add=self._add_to_cart) for p in POS_PRODUCTS],
                                ],
                                spacing=8,
                            ),
                            expand=1,
                            **card_style(),
                        ),
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    heading_text("Carrito", size=FONT_SIZE_MD),
                                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.only(top=8, bottom=12)),
                                    self.cart_list,
                                    ft.Container(height=1, bgcolor=BORDER),
                                    ft.Row(
                                        controls=[
                                            label_text("Total"),
                                            ft.Container(expand=True),
                                            self.total_text,
                                        ],
                                    ),
                                    ft.Container(height=8),
                                    ft.ElevatedButton(
                                        content=ft.Row(
                                            controls=[
                                                ft.Icon(ft.Icons.RECEIPT_LONG, size=18, color=TEXT_PRIMARY),
                                                ft.Text("Cobrar", size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
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
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    heading_text("Ventas del Dia", size=FONT_SIZE_MD),
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
            ],
            spacing=8,
            expand=True,
        )

    def _build_cart_rows(self):
        if not self.cart_items:
            return [label_text("Carrito vacio", color=TEXT_MUTED)]
        rows = []
        for item in self.cart_items:
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(item["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, expand=True),
                        ft.Text(f"x{item['qty']}", size=FONT_SIZE_SM, color=TEXT_SECONDARY),
                        ft.Text(f"${item['subtotal']:.2f}", size=FONT_SIZE_SM, color=ACCENT_PRIMARY, weight="w600"),
                    ],
                )
            )
        return rows

    def _build_sales_log(self):
        rows = []
        for sale in DAILY_SALES:
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(sale["producto"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, expand=True),
                        ft.Text(sale["hora"], size=FONT_SIZE_XS, color=TEXT_MUTED),
                        ft.Text(f"${sale['monto']:.2f}", size=FONT_SIZE_SM, color=ACCENT_SUCCESS, weight="w600"),
                    ],
                )
            )
        return rows

    def _add_to_cart(self, producto, qty):
        existing = next((c for c in self.cart_items if c["nombre"] == producto["nombre"]), None)
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

        self.cart_total = compute_sales_summary(self.cart_items)["total"]
        self.total_text.value = f"${self.cart_total:.2f}"
        self.cart_list.controls = self._build_cart_rows()
        self.cart_list.update()
        self.total_text.update()

    def _checkout(self, e):
        if not self.cart_items:
            return

        for item in register_sale_rows(self.cart_items):
            self.sales_log.controls.append(
                ft.Row(
                    controls=[
                        ft.Text(item["producto"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, expand=True),
                        ft.Text(item["hora"], size=FONT_SIZE_XS, color=TEXT_MUTED),
                        ft.Text(f"${item['monto']:.2f}", size=FONT_SIZE_SM, color=ACCENT_SUCCESS, weight="w600"),
                    ],
                )
            )

        self.cart_items = []
        self.cart_total = 0.0
        self.total_text.value = "$0.00"
        self.cart_list.controls = self._build_cart_rows()
        self.cart_list.update()
        self.total_text.update()
        self.sales_log.update()
