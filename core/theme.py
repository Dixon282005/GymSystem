"""Theme constants — Neo-minimalist / Shadcn UI palette."""

import flet as ft

# Cross-version compatibility shims for Flet (supporting both old <0.80 and new >=0.86)
if hasattr(ft, "Border"):
    for attr in ("all", "only", "symmetric"):
        if hasattr(ft.Border, attr) and not hasattr(ft.border, attr):
            setattr(ft.border, attr, getattr(ft.Border, attr))

if hasattr(ft, "Margin"):
    for attr in ("all", "only", "symmetric", "top", "bottom", "left", "right"):
        if hasattr(ft.Margin, attr) and not hasattr(ft.margin, attr):
            setattr(ft.margin, attr, getattr(ft.Margin, attr))

if hasattr(ft, "Padding"):
    for attr in ("all", "only", "symmetric", "top", "bottom", "left", "right"):
        if hasattr(ft.Padding, attr) and not hasattr(ft.padding, attr):
            setattr(ft.padding, attr, getattr(ft.Padding, attr))

if hasattr(ft, "BorderRadius"):
    for attr in ("all", "only", "symmetric", "horizontal", "vertical"):
        if hasattr(ft.BorderRadius, attr) and not hasattr(ft.border_radius, attr):
            setattr(ft.border_radius, attr, getattr(ft.BorderRadius, attr))


if hasattr(ft, "Alignment"):
    for attr in ("CENTER", "TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT", "CENTER_LEFT", "CENTER_RIGHT"):
        if hasattr(ft.Alignment, attr):
            lower_name = attr.lower()
            if not hasattr(ft.alignment, lower_name):
                setattr(ft.alignment, lower_name, getattr(ft.Alignment, attr))
    if not hasattr(ft.alignment, "center") and hasattr(ft.Alignment, "CENTER"):
        setattr(ft.alignment, "center", ft.Alignment.CENTER)

if hasattr(ft, "Dropdown") and hasattr(ft.Dropdown, "__init__"):
    _orig_dropdown_init = ft.Dropdown.__init__
    def _patched_dropdown_init(self, *args, **kwargs):
        if "on_change" in kwargs:
            cb = kwargs.pop("on_change")
            kwargs["on_select"] = cb
        return _orig_dropdown_init(self, *args, **kwargs)
    ft.Dropdown.__init__ = _patched_dropdown_init

# Cross-version Page dialog opening & closing shims
def _page_open_shim(self, control):
    if hasattr(self, "show_dialog"):
        try:
            return self.show_dialog(control)
        except Exception:
            pass
    self.dialog = control
    control.open = True
    self.update()

def _page_close_shim(self, control=None):
    if hasattr(self, "pop_dialog"):
        try:
            return self.pop_dialog()
        except Exception:
            pass
    if control:
        control.open = False
    elif getattr(self, "dialog", None):
        self.dialog.open = False
    self.update()

if not hasattr(ft.Page, "open"):
    setattr(ft.Page, "open", _page_open_shim)
if not hasattr(ft.Page, "close"):
    setattr(ft.Page, "close", _page_close_shim)

# Cross-version Control.page property safe getter and setter (returns None instead of raising RuntimeError when unattached)
if hasattr(ft, "Control") and hasattr(ft.Control, "page") and isinstance(getattr(ft.Control, "page", None), property):
    _orig_control_page = ft.Control.page.fget
    def _safe_control_page(self):
        if hasattr(self, "_custom_page"):
            return self._custom_page
        try:
            return _orig_control_page(self)
        except RuntimeError:
            return None

    def _safe_control_page_set(self, val):
        self._custom_page = val

    def _safe_control_page_del(self):
        if hasattr(self, "_custom_page"):
            del self._custom_page

    ft.Control.page = property(_safe_control_page, _safe_control_page_set, _safe_control_page_del)

try:
    import fastapi
    if hasattr(fastapi, "FastAPI") and hasattr(fastapi.FastAPI, "__init__"):
        _orig_fastapi_init = fastapi.FastAPI.__init__
        def _patched_fastapi_init(self, *args, **kwargs):
            kwargs.pop("openapi_prefix", None)
            return _orig_fastapi_init(self, *args, **kwargs)
        fastapi.FastAPI.__init__ = _patched_fastapi_init
except Exception:
    pass

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
    border_val = ft.Border.all(1, border_color) if hasattr(ft, "Border") and hasattr(ft.Border, "all") else ft.border.all(1, border_color)
    return {
        "bgcolor": bg,
        "border": border_val,
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


ButtonControl = getattr(ft, "Button", ft.ElevatedButton)


def button_primary(text, on_click=None, width=None, icon=None, **kwargs):
    """Primary button factory supporting optional icon."""
    from flet import Text, Row, Icon
    if icon:
        content = Row(
            controls=[
                Icon(icon, size=16, color=TEXT_PRIMARY),
                Text(text, size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        )
    else:
        content = Text(text, size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY)

    btn = ButtonControl(
        content=content,
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


def button_danger(text, on_click=None, width=None, icon=None, **kwargs):
    """Danger/accent button factory supporting optional icon."""
    from flet import Text, Row, Icon
    if icon:
        content = Row(
            controls=[
                Icon(icon, size=16, color=TEXT_PRIMARY),
                Text(text, size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        )
    else:
        content = Text(text, size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY)

    btn = ButtonControl(
        content=content,
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


def button_outline(text, on_click=None, width=None, icon=None, **kwargs):
    """Outline/ghost button factory supporting optional icon."""
    from flet import Text, Row, Icon
    if icon:
        content = Row(
            controls=[
                Icon(icon, size=16, color=TEXT_SECONDARY),
                Text(text, size=FONT_SIZE_SM, weight="w500", color=TEXT_SECONDARY),
            ],
            spacing=6,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        )
    else:
        content = Text(text, size=FONT_SIZE_SM, weight="w500", color=TEXT_SECONDARY)

    btn = ButtonControl(
        content=content,
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


def BCVRateChip(rate: float, updated: str = ""):
    from ui.components.widgets import BCVRateChip as _Chip
    return _Chip(rate=rate, updated=updated)


def show_snack(page, msg: str, color=None):
    from ui.components.widgets import show_snack as _show_snack
    return _show_snack(page, msg, color)


