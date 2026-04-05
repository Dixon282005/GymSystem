"""Live Access Feed view — real-time NFC access log."""

import flet as ft
from core.theme import (
    BG_INPUT, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    ACCENT_PRIMARY, ACCENT_SUCCESS, ACCENT_DANGER, FONT_SIZE_MD,
    card_style, heading_text, label_text,
)
from core.mock_data import APP_SETTINGS
from core.business import can_member_access, register_access_attempt, build_access_snapshot
from core.repositories import AccessRepository, MemberRepository
from ui.components.widgets import AccessLogCard

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


class AccessView(ft.Column):
    def __init__(self):
        self._running = False
        try:
            snap = build_access_snapshot()
            allowed = str(snap["allowed_today"])
            denied = str(snap["denied_today"])
            events = str(snap["total_events"])
        except Exception:
            allowed = "0"
            denied = "0"
            events = "0"

        self.last_status = ft.Text("Listo para check-in", color=TEXT_MUTED, size=13)
        self.allowed_counter = ft.Text(allowed, size=22, color=ACCENT_SUCCESS, weight="w700")
        self.denied_counter = ft.Text(denied, size=22, color=ACCENT_DANGER, weight="w700")
        self.events_counter = ft.Text(events, size=22, color=ACCENT_PRIMARY, weight="w700")

        self.log_container = ft.Column(controls=[], spacing=12, scroll=ft.ScrollMode.AUTO)
        self.present_column = ft.Column(controls=[], spacing=8, scroll=ft.ScrollMode.AUTO)
        self._refresh_present()

        nfc_on = APP_SETTINGS.get("enable_nfc_simulation", True)
        self.filter_status = ft.Dropdown(
            label="Estado", value="TODOS",
            options=[ft.dropdown.Option("TODOS"), ft.dropdown.Option("PERMITIDO"), ft.dropdown.Option("DENEGADO")],
            width=140, bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
        )
        self.filter_query = ft.TextField(
            hint_text="Filtrar cedula/nombre...", width=200, height=42,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER, on_submit=self._refresh_log,
        )
        
        self.sim_tipo = ft.Dropdown(
            options=[ft.dropdown.Option(t) for t in CEDULA_TYPES],
            value="V", width=70, height=42,
            bgcolor=BG_INPUT, color=TEXT_PRIMARY, border_color=BORDER,
            disabled=not nfc_on
        )
        self.sim_numero = ft.TextField(
            hint_text="12345678", bgcolor=BG_INPUT, color=TEXT_PRIMARY,
            border_color=BORDER, border_radius=8, text_size=14, height=42, width=130,
            on_submit=self._scan, disabled=not nfc_on,
            input_filter=ft.NumbersOnlyInputFilter(),
        )

        self.checkin_btn = ft.ElevatedButton(
            "Check-in", on_click=self._scan, bgcolor=ACCENT_PRIMARY, color=TEXT_PRIMARY, disabled=not nfc_on,
        )

        self._refresh_log()

        super().__init__(controls=[
            ft.Row(controls=[
                heading_text("Check-in"),
                ft.Container(expand=True),
                self.sim_tipo, self.sim_numero, self.checkin_btn,
            ]),
            self.last_status,
            ft.Row(controls=[
                self.filter_status, self.filter_query,
                ft.IconButton(icon=ft.Icons.FILTER_ALT, icon_color=ACCENT_PRIMARY, on_click=self._refresh_log),
            ]),
            ft.Container(height=4),
            ft.Row(controls=[
                self._cc("Permitidos", self.allowed_counter, ACCENT_SUCCESS),
                self._cc("Denegados", self.denied_counter, ACCENT_DANGER),
                self._cc("Eventos", self.events_counter, ACCENT_PRIMARY),
            ], spacing=12),
            ft.Container(height=8),
            ft.Row(controls=[
                ft.Container(content=ft.Column(controls=[
                    heading_text("Registro de Accesos", size=FONT_SIZE_MD),
                    ft.Container(height=1, bgcolor=BORDER),
                    self.log_container,
                ], spacing=8), expand=2, **card_style()),
                ft.Container(content=ft.Column(controls=[
                    heading_text("En el Gimnasio", size=FONT_SIZE_MD),
                    ft.Container(height=1, bgcolor=BORDER),
                    self.present_column,
                ], spacing=8), expand=1, **card_style()),
            ], spacing=16, expand=True),
        ], spacing=8, expand=True)

    def did_mount(self):
        self._running = True
        if self.page:
            self.page.run_task(self._auto_refresh)

    def will_unmount(self):
        self._running = False

    async def _auto_refresh(self):
        import asyncio
        while self._running:
            try:
                self._refresh_present()
                self._refresh_log()
                self._refresh_counters()
                self.present_column.update()
            except Exception:
                self._running = False
                break
            await asyncio.sleep(2)

    def _refresh_log(self, e=None):
        try:
            st = self.filter_status.value or "TODOS"
            q = (self.filter_query.value or "").strip().upper()
            cards = []
            for entry in AccessRepository.list_recent(limit=100):
                if st != "TODOS" and entry["status"] != st:
                    continue
                if q and q not in f"{entry['cedula']} {entry['nombre']}".upper():
                    continue
                cards.append(AccessLogCard(
                    nombre=entry["nombre"], plan=entry["plan"],
                    hora=entry["hora"], status=entry["status"], cedula=entry["cedula"],
                ))
            if not cards:
                cards = [ft.Container(content=label_text("Sin resultados", color=TEXT_MUTED), **card_style())]
            self.log_container.controls = cards
            try:
                if self.log_container.page is not None:
                    self.log_container.update()
            except RuntimeError:
                pass
        except Exception as ex:
            _snack(self.page, f"Error cargando logs: {ex}", "#7f1d1d")

    def _refresh_present(self):
        try:
            present = build_access_snapshot()["present"]
            items = [ft.Row(controls=[
                ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=ACCENT_SUCCESS),
                ft.Text(m["nombre"], size=13, color=TEXT_PRIMARY),
                ft.Container(expand=True),
                ft.Text(m["plan"], size=12, color=TEXT_SECONDARY),
            ]) for m in present]
            if not items:
                items = [label_text("Nadie en el gimnasio", color=TEXT_MUTED)]
            self.present_column.controls = items
        except Exception:
            pass

    def _refresh_counters(self):
        try:
            s = build_access_snapshot()
            self.allowed_counter.value = str(s["allowed_today"])
            self.denied_counter.value = str(s["denied_today"])
            self.events_counter.value = str(s["total_events"])
            self.allowed_counter.update()
            self.denied_counter.update()
            self.events_counter.update()
        except Exception:
            pass

    def _cc(self, label, ctrl, color):
        return ft.Container(content=ft.Column(controls=[
            ft.Text(label, size=12, color=TEXT_MUTED), ctrl,
        ], spacing=4), expand=True, **card_style())

    def _scan(self, e):
        try:
            tipo = (self.sim_tipo.value or "V").strip().upper()
            numero = (self.sim_numero.value or "").strip()
            
            if not numero:
                self.last_status.value = "Ingresa el numero de cedula"
                self.last_status.color = ACCENT_DANGER
                self.last_status.update()
                return
                
            cedula = _format_cedula(tipo, numero)
            member = MemberRepository.find_by_cedula(cedula)
            
            allowed, reason = can_member_access(member)
            ev = register_access_attempt(cedula, member, allowed)
            
            if allowed:
                self.last_status.value = f"OK: {ev['nombre']} ({ev['cedula']})"
                self.last_status.color = ACCENT_SUCCESS
                _snack(self.page, f"Acceso Permitido: {ev['nombre']}", "#0f766e")
            else:
                name = ev['nombre'] if ev['nombre'] != "Desconocido" else "No registrado"
                self.last_status.value = f"DENEGADO: {cedula} - {reason}"
                self.last_status.color = ACCENT_DANGER
                _snack(self.page, f"Acceso Denegado: {name} - {reason}", "#7f1d1d")
                
            self.sim_numero.value = ""
            self._refresh_present()
            self._refresh_log()
            self.sim_numero.update()
            self.last_status.update()
            self.present_column.update()
            self._refresh_counters()
            
        except Exception as ex:
            self.last_status.value = f"Error al procesar: {ex}"
            self.last_status.color = ACCENT_DANGER
            self.last_status.update()
            _snack(self.page, f"Error: {ex}", "#7f1d1d")
