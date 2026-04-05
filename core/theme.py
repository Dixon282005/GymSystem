"""Theme constants — Neo-minimalist / Shadcn UI palette."""

import flet as ft

BG_BASE = "#020617"
BG_CARD = "#0f172a"
BG_INPUT = "#1e293b"
BORDER = "#1e293b"

TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"

ACCENT_PRIMARY = "#6366f1"
ACCENT_PRIMARY_HOVER = "#818cf8"
ACCENT_DANGER = "#f43f5e"
ACCENT_SUCCESS = "#22c55e"
ACCENT_WARNING = "#eab308"
ACCENT_INFO = "#3b82f6"

RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16

PADDING_SM = 12
PADDING_MD = 20
PADDING_LG = 32

FONT_FAMILY = "Segoe UI, system-ui, sans-serif"
FONT_SIZE_XS = 11
FONT_SIZE_SM = 13
FONT_SIZE_MD = 15
FONT_SIZE_LG = 18
FONT_SIZE_XL = 24
FONT_SIZE_2XL = 32


def card_style(bg=BG_CARD, border_color=BORDER, radius=RADIUS_MD, padding=PADDING_MD):
    """Reusable card style dict."""
    return {
        "bgcolor": bg,
        "border": ft.border.all(1, border_color),
        "border_radius": radius,
        "padding": padding,
    }


def input_style():
    """Reusable input field style."""
    return {
        "bgcolor": BG_INPUT,
        "color": TEXT_PRIMARY,
        "border": ft.InputBorder.OUTLINE,
        "border_color": BORDER,
        "border_radius": RADIUS_SM,
        "text_size": FONT_SIZE_MD,
    }


def button_primary(text, on_click=None, width=None):
    """Primary button factory."""
    from flet import ElevatedButton, Text
    btn = ElevatedButton(
        content=Text(text, size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
        bgcolor=ACCENT_PRIMARY,
        color=TEXT_PRIMARY,
        on_click=on_click,
        style=ft.ButtonStyle(
            padding=12,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
        ),
    )
    if width:
        btn.width = width
    return btn


def button_danger(text, on_click=None, width=None):
    """Danger/accent button factory."""
    from flet import ElevatedButton, Text
    btn = ElevatedButton(
        content=Text(text, size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
        bgcolor=ACCENT_DANGER,
        color=TEXT_PRIMARY,
        on_click=on_click,
        style=ft.ButtonStyle(
            padding=12,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
        ),
    )
    if width:
        btn.width = width
    return btn


def button_outline(text, on_click=None, width=None):
    """Outline/ghost button factory."""
    from flet import ElevatedButton, Text
    btn = ElevatedButton(
        content=Text(text, size=FONT_SIZE_SM, weight="w500", color=TEXT_SECONDARY),
        bgcolor="transparent",
        color=TEXT_SECONDARY,
        on_click=on_click,
        style=ft.ButtonStyle(
            padding=12,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
            side=ft.BorderSide(1, BORDER),
        ),
    )
    if width:
        btn.width = width
    return btn


def label_text(text, size=FONT_SIZE_SM, color=TEXT_SECONDARY, weight="w500"):
    """Reusable label text."""
    from flet import Text
    return Text(text, size=size, color=color, weight=weight)


def heading_text(text, size=FONT_SIZE_LG, color=TEXT_PRIMARY, weight="w700"):
    """Reusable heading text."""
    from flet import Text
    return Text(text, size=size, color=color, weight=weight)
