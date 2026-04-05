"""Members management view with data table, add dialog, and payment dialog."""

import flet as ft
from core.theme import (
    BG_CARD, BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_DANGER, ACCENT_WARNING,
    RADIUS_SM, RADIUS_MD, PADDING_MD,
    FONT_SIZE_XS, FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG,
    card_style, heading_text, button_primary,
)
from core.mock_data import PLANS
from core.repositories import MemberRepository, PaymentRepository
from core.db_store import save_member

# ── Cédula types used in Venezuela ──
CEDULA_TYPES = ["V", "E", "J", "G", "P"]


def _snack(page, msg, color="#0f766e"):
    try:
        sb = ft.SnackBar(content=ft.Text(msg, color=TEXT_PRIMARY), bgcolor=color)
        page.overlay.append(sb)
        sb.open = True
        page.update()
    except Exception:
        pass


def _format_cedula(tipo: str, numero: str) -> str:
    """Build canonical cedula: 'V-12345678'."""
    t = (tipo or "V").strip().upper()
    n = "".join(c for c in (numero or "") if c.isdigit())
    return f"{t}-{n}" if n else ""


def _parse_cedula(cedula: str) -> tuple[str, str]:
    """Split 'V-12345678' into ('V', '12345678')."""
    cedula = (cedula or "").strip().upper()
    for prefix in CEDULA_TYPES:
        if cedula.startswith(prefix + "-"):
            return prefix, cedula[len(prefix) + 1:]
        if cedula.startswith(prefix) and len(cedula) > 1 and cedula[1:].isdigit():
            return prefix, cedula[1:]
    # No prefix found, assume V
    digits = "".join(c for c in cedula if c.isdigit())
    return "V", digits


def _validate_cedula_input(tipo: str, numero: str) -> tuple[bool, str]:
    """Validate cedula parts. Returns (ok, error_message)."""
    t = (tipo or "").strip().upper()
    n = "".join(c for c in (numero or "") if c.isdigit())
    if t not in CEDULA_TYPES:
        return False, f"Tipo de cedula invalido: {t}"
    if not n:
        return False, "Numero de cedula vacio"
    if len(n) < 6:
        return False, "Numero de cedula muy corto (min 6 digitos)"
    if len(n) > 10:
        return False, "Numero de cedula muy largo (max 10 digitos)"
    return True, ""


class MembersView(ft.Column):
    """Members table with add member and payment modals."""

    def __init__(self):
        self._members = MemberRepository.list_all()
        self._dialogs_attached = False

        # ── New member fields ──
        self.ced_tipo = ft.Dropdown(
            label="Tipo",
            options=[ft.dropdown.Option(t) for t in CEDULA_TYPES],
            value="V", width=90,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )
        self.ced_numero = ft.TextField(
            label="Nro. Cedula", hint_text="12345678", width=200,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.nombre_field = ft.TextField(
            label="Nombre Completo",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )
        self.plan_field = ft.Dropdown(
            label="Plan",
            options=[ft.dropdown.Option(k) for k in PLANS.keys()],
            value="Basico",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )
        self.nfc_field = ft.TextField(
            label="ID Tarjeta NFC (opcional)", hint_text="NFC-XXXX",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )

        # ── Payment fields ──
        self.pay_ced_tipo = ft.Dropdown(
            label="Tipo",
            options=[ft.dropdown.Option(t) for t in CEDULA_TYPES],
            value="V", width=90,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )
        self.pay_ced_numero = ft.TextField(
            label="Nro. Cedula", hint_text="12345678", width=200,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.pay_plan = ft.Dropdown(
            label="Plan",
            options=[ft.dropdown.Option(k) for k in PLANS.keys()],
            value="Basico",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )
        self.pay_monto = ft.TextField(
            label="Monto ($)", hint_text="25.00",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
            input_filter=ft.InputFilter(regex_string=r"[0-9.]", allow=True),
        )
        self.pay_dias = ft.TextField(
            label="Dias de membresia", value="30",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        self.pay_metodo = ft.Dropdown(
            label="Metodo de pago",
            options=[
                ft.dropdown.Option("efectivo"),
                ft.dropdown.Option("transferencia"),
                ft.dropdown.Option("punto"),
                ft.dropdown.Option("pago_movil"),
            ],
            value="efectivo",
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            border_radius=RADIUS_SM, text_size=14,
        )

        # ── Table body ──
        self.table_body = ft.Column(
            controls=self._build_rows(),
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )

        # ── Dialogs ──
        self.new_member_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Nuevo Miembro", size=FONT_SIZE_LG),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(controls=[self.ced_tipo, self.ced_numero], spacing=8),
                        self.nombre_field,
                        self.plan_field,
                        self.nfc_field,
                    ],
                    spacing=12, tight=True,
                ),
                padding=PADDING_MD, width=380,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._close_new),
                ft.ElevatedButton(
                    "Registrar", bgcolor=ACCENT_PRIMARY, color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_member,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        self.payment_dialog = ft.AlertDialog(
            modal=True,
            title=heading_text("Registrar Pago de Membresia", size=FONT_SIZE_LG),
            content=ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Row(controls=[self.pay_ced_tipo, self.pay_ced_numero], spacing=8),
                        self.pay_plan,
                        self.pay_monto,
                        self.pay_dias,
                        self.pay_metodo,
                    ],
                    spacing=12, tight=True,
                ),
                padding=PADDING_MD, width=380,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=self._close_pay),
                ft.ElevatedButton(
                    "Registrar Pago", bgcolor=ACCENT_SUCCESS, color=TEXT_PRIMARY,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    on_click=self._save_payment,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_MD),
            bgcolor=BG_CARD,
        )

        super().__init__(
            controls=[
                ft.Row(controls=[
                    heading_text("Gestion de Miembros"),
                    ft.Container(expand=True),
                    button_primary("+ Nuevo Ingreso", on_click=self._open_new),
                    ft.ElevatedButton(
                        content=ft.Row(controls=[
                            ft.Icon(ft.Icons.PAYMENT, size=16, color=TEXT_PRIMARY),
                            ft.Text("Pago Membresia", size=FONT_SIZE_SM, weight="w600", color=TEXT_PRIMARY),
                        ], spacing=6, tight=True),
                        bgcolor=ACCENT_SUCCESS, color=TEXT_PRIMARY, on_click=self._open_pay,
                        style=ft.ButtonStyle(padding=12, shape=ft.RoundedRectangleBorder(radius=RADIUS_SM)),
                    ),
                ]),
                ft.Container(height=12),
                ft.Container(
                    content=ft.Column(controls=[
                        self._build_header(),
                        ft.Container(height=1, bgcolor=BORDER),
                        self.table_body,
                    ], spacing=0),
                    **card_style(), expand=True,
                ),
            ],
            spacing=8, expand=True,
        )

    # ── Lifecycle ──
    def did_mount(self):
        try:
            if self.page and not self._dialogs_attached:
                self.page.overlay.append(self.new_member_dialog)
                self.page.overlay.append(self.payment_dialog)
                self._dialogs_attached = True
                self.page.update()
        except Exception:
            pass

    def will_unmount(self):
        try:
            if self.page and self._dialogs_attached:
                for dlg in (self.new_member_dialog, self.payment_dialog):
                    if dlg in self.page.overlay:
                        self.page.overlay.remove(dlg)
                self._dialogs_attached = False
        except Exception:
            pass

    # ── Dialog open/close (safe) ──
    def _open_new(self, e):
        try:
            self.new_member_dialog.open = True
            self.page.update()
        except Exception as ex:
            _snack(self.page, f"Error abriendo formulario: {ex}", "#7f1d1d")

    def _close_new(self, e):
        try:
            self.new_member_dialog.open = False
            self.page.update()
        except Exception:
            pass

    def _open_pay(self, e):
        try:
            self.payment_dialog.open = True
            self.page.update()
        except Exception as ex:
            _snack(self.page, f"Error abriendo formulario: {ex}", "#7f1d1d")

    def _close_pay(self, e):
        try:
            self.payment_dialog.open = False
            self.page.update()
        except Exception:
            pass

    # ── Table header ──
    def _build_header(self):
        return ft.Container(
            content=ft.Row(controls=[
                ft.Text("Cedula", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=110),
                ft.Text("Nombre", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", expand=True),
                ft.Text("Plan", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=70),
                ft.Text("Vence", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=100),
                ft.Text("Estado", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=80),
                ft.Text("Acciones", size=FONT_SIZE_XS, color=TEXT_MUTED, weight="w600", width=160),
            ]),
            padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=10),
        )

    def _build_rows(self):
        rows = []
        for m in self._members:
            sc = ACCENT_SUCCESS if m["estado"] == "Activo" else (ACCENT_DANGER if m["estado"] == "Moroso" else TEXT_MUTED)
            rows.append(ft.Container(
                content=ft.Row(controls=[
                    ft.Text(m["cedula"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=110),
                    ft.Text(m["nombre"], size=FONT_SIZE_SM, color=TEXT_PRIMARY, weight="w500", expand=True),
                    ft.Text(m["plan"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=70),
                    ft.Text(m["vencimiento"], size=FONT_SIZE_SM, color=TEXT_SECONDARY, width=100),
                    ft.Container(
                        content=ft.Text(m["estado"], size=FONT_SIZE_XS, color=TEXT_PRIMARY, weight="w600"),
                        bgcolor=sc, padding=ft.padding.symmetric(horizontal=8, vertical=4),
                        border_radius=RADIUS_SM, width=80, alignment=ft.Alignment(0, 0),
                    ),
                    ft.Row(controls=[
                        ft.TextButton(
                            "Moroso" if m["estado"] == "Activo" else "Activar",
                            on_click=self._mk_toggle(m["cedula"], m["estado"]),
                            style=ft.ButtonStyle(padding=4),
                        ),
                        ft.TextButton(
                            "Inactivar", on_click=self._mk_deact(m["cedula"]),
                            style=ft.ButtonStyle(padding=4),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.PAYMENT, icon_size=16, icon_color=ACCENT_SUCCESS,
                            tooltip="Pago rapido", on_click=self._mk_qpay(m["cedula"], m["plan"]),
                        ),
                    ], width=160, spacing=0),
                ]),
                padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=6),
                border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
            ))
        return rows

    # ── Save new member ──
    def _save_member(self, e):
        try:
            tipo = (self.ced_tipo.value or "V").strip()
            numero = (self.ced_numero.value or "").strip()

            ok, err = _validate_cedula_input(tipo, numero)
            if not ok:
                _snack(self.page, err, "#7f1d1d")
                return

            cedula = _format_cedula(tipo, numero)
            nombre = (self.nombre_field.value or "").strip()
            plan = (self.plan_field.value or "Basico").strip()
            nfc_id = (self.nfc_field.value or "").strip()

            if not nombre:
                _snack(self.page, "El nombre es obligatorio", "#7f1d1d")
                return
            if len(nombre) < 3:
                _snack(self.page, "Nombre muy corto (min 3 caracteres)", "#7f1d1d")
                return

            member = MemberRepository.create_member(cedula=cedula, nombre=nombre, plan=plan, nfc_id=nfc_id)

            self._members = MemberRepository.list_all()
            self.table_body.controls = self._build_rows()
            self.table_body.update()

            # Clear form
            self.ced_tipo.value = "V"
            self.ced_numero.value = ""
            self.nombre_field.value = ""
            self.plan_field.value = "Basico"
            self.nfc_field.value = ""

            self.new_member_dialog.open = False
            self.page.update()
            _snack(self.page, f"Miembro registrado: {nombre}")

        except ValueError as exc:
            _snack(self.page, str(exc), "#7f1d1d")
        except Exception as exc:
            _snack(self.page, f"Error inesperado: {exc}", "#7f1d1d")

    # ── Payment ──
    def _mk_qpay(self, cedula, plan):
        def handler(e):
            try:
                tipo, numero = _parse_cedula(cedula)
                self.pay_ced_tipo.value = tipo
                self.pay_ced_numero.value = numero
                plan_info = PLANS.get(plan, {})
                self.pay_plan.value = plan
                self.pay_monto.value = str(plan_info.get("precio", 25.00))
                self.pay_dias.value = str(plan_info.get("dias", 30))
                self.payment_dialog.open = True
                self.page.update()
            except Exception as ex:
                _snack(self.page, f"Error: {ex}", "#7f1d1d")
        return handler

    def _save_payment(self, e):
        try:
            tipo = (self.pay_ced_tipo.value or "V").strip()
            numero = (self.pay_ced_numero.value or "").strip()

            ok, err = _validate_cedula_input(tipo, numero)
            if not ok:
                _snack(self.page, err, "#7f1d1d")
                return

            cedula = _format_cedula(tipo, numero)
            plan = (self.pay_plan.value or "Basico").strip()

            member = MemberRepository.find_by_cedula(cedula)
            if not member:
                _snack(self.page, "Miembro no encontrado. Registralo primero.", "#7f1d1d")
                return

            try:
                monto = float(self.pay_monto.value or "0")
            except (ValueError, TypeError):
                _snack(self.page, "Monto invalido (use formato: 25.00)", "#7f1d1d")
                return

            if monto <= 0:
                _snack(self.page, "El monto debe ser mayor a 0", "#7f1d1d")
                return

            try:
                dias = int(self.pay_dias.value or "30")
            except (ValueError, TypeError):
                _snack(self.page, "Dias invalido (use un numero entero)", "#7f1d1d")
                return

            if dias <= 0 or dias > 365:
                _snack(self.page, "Dias debe ser entre 1 y 365", "#7f1d1d")
                return

            metodo = (self.pay_metodo.value or "efectivo").strip()

            ok2, msg = PaymentRepository.register_payment(
                cedula=cedula, plan=plan, monto=monto, dias=dias, metodo=metodo,
            )
            if not ok2:
                _snack(self.page, msg, "#7f1d1d")
                return

            self._members = MemberRepository.list_all()
            self.table_body.controls = self._build_rows()
            self.table_body.update()

            # Clear form
            self.pay_ced_tipo.value = "V"
            self.pay_ced_numero.value = ""
            self.pay_monto.value = ""
            self.pay_dias.value = "30"

            self.payment_dialog.open = False
            self.page.update()
            _snack(self.page, f"Pago {plan} ${monto:.2f} ({dias}d) → {member['nombre']}")

        except Exception as exc:
            _snack(self.page, f"Error inesperado: {exc}", "#7f1d1d")

    # ── Status toggles ──
    def _mk_toggle(self, cedula, estado):
        def handler(e):
            try:
                nuevo = "Moroso" if estado == "Activo" else "Activo"
                self._upd_status(cedula, nuevo)
            except Exception as ex:
                _snack(self.page, f"Error: {ex}", "#7f1d1d")
        return handler

    def _mk_deact(self, cedula):
        def handler(e):
            try:
                self._upd_status(cedula, "Inactivo")
            except Exception as ex:
                _snack(self.page, f"Error: {ex}", "#7f1d1d")
        return handler

    def _upd_status(self, cedula, new_status):
        for m in self._members:
            if m["cedula"] == cedula:
                m["estado"] = new_status
                save_member(m)
                break
        self.table_body.controls = self._build_rows()
        self.table_body.update()
        _snack(self.page, f"Estado → {new_status}")
