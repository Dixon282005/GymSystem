"""Report text/Excel generation and shared report paths for Gymsis."""

from __future__ import annotations

from datetime import datetime, date
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from core.bcv_service import bcv_service
from core.paths import get_app_dir, get_reports_root


def get_base_dir() -> str:
    return get_app_dir()


def get_reports_dir(for_date: Any = None) -> str:
    """Return the folder path: reports/YYYY-MM/YYYY-MM-DD."""
    if for_date is None:
        for_date = datetime.now()
    if isinstance(for_date, datetime):
        for_date = for_date.date()

    month_folder = for_date.strftime("%Y-%m")
    date_folder = for_date.strftime("%Y-%m-%d")
    path = os.path.join(get_reports_root(), month_folder, date_folder)
    os.makedirs(path, exist_ok=True)
    return path


def get_contacts_export_dir() -> str:
    path = os.path.join(get_reports_root(), "contactos")
    os.makedirs(path, exist_ok=True)
    return path


def collect_shift_data(start_time_str: str, end_time_str: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collect payments, sales, and access logs between start_time_str and end_time_str directly via SQL."""
    from core.db_store import (
        load_membership_payments_between,
        load_sales_between,
        load_access_log_between,
    )

    payments_shift = load_membership_payments_between(start_time_str, end_time_str)
    sales_shift = load_sales_between(start_time_str, end_time_str)
    access_shift = load_access_log_between(start_time_str, end_time_str)

    return payments_shift, sales_shift, access_shift


def generate_report_text(
    target_date: Optional[date] = None,
    payments: Optional[List[Dict[str, Any]]] = None,
    sales: Optional[List[Dict[str, Any]]] = None,
    access: Optional[List[Dict[str, Any]]] = None,
    start_time_str: Optional[str] = None,
    end_time_str: Optional[str] = None,
    bcv_rate: Optional[float] = None,
) -> str:
    """Generate structured ASCII / text financial closure report."""
    if target_date is None:
        target_date = datetime.now().date()

    rate = bcv_rate if bcv_rate is not None and bcv_rate > 0 else bcv_service.get_rate()
    date_str = target_date.strftime("%Y-%m-%d")

    payments = payments or []
    sales = sales or []
    access = access or []

    total_payments_usd = sum(float(p.get("monto", 0.0)) for p in payments)
    total_payments_bs = sum(
        float(p.get("monto_bs", 0.0)) if float(p.get("monto_bs", 0.0)) > 0 else float(p.get("monto", 0.0)) * rate
        for p in payments
    )

    total_sales_usd = sum(float(s.get("monto", 0.0)) for s in sales)
    total_sales_bs = total_sales_usd * rate

    total_general_usd = total_payments_usd + total_sales_usd
    total_general_bs = total_payments_bs + total_sales_bs

    allowed_count = sum(1 for a in access if a.get("status") in ("ENTRADA", "PERMITIDO"))
    checkout_count = sum(1 for a in access if a.get("status") in ("CHECK-OUT", "SALIDA"))
    denied_count = sum(1 for a in access if a.get("status") == "DENEGADO")

    # Payment methods breakdown
    methods_totals: Dict[str, Dict[str, float]] = {}
    for p in payments:
        m = (p.get("metodo") or "efectivo").lower()
        if m not in methods_totals:
            methods_totals[m] = {"usd": 0.0, "bs": 0.0}
        m_usd = float(p.get("monto", 0.0))
        m_bs = float(p.get("monto_bs", 0.0)) or (m_usd * rate)
        methods_totals[m]["usd"] += m_usd
        methods_totals[m]["bs"] += m_bs

    lines = [
        "==========================================",
        "             CIERRE DE CAJA               ",
        f"  Desde: {start_time_str or (date_str + ' 00:00')}",
        f"  Hasta: {end_time_str or datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Fecha: {date_str}",
        f"  Tasa BCV del día: {rate:.2f} Bs/$",
        "==========================================",
        "",
        "INGRESOS POR MEMBRESÍAS:",
        "------------------------------------------",
    ]

    if not payments:
        lines.append(" (Sin cobros registrados hoy)")
    else:
        for p in payments:
            nombre = p.get("nombre") or "Desconocido"
            cedula = p.get("cedula", "")
            plan = p.get("plan", "Plan")
            monto = float(p.get("monto", 0.0))
            monto_bs = float(p.get("monto_bs", 0.0)) or (monto * rate)
            metodo = p.get("metodo", "efectivo")
            ref = f" (Ref: {p['referencia']})" if p.get("referencia") else ""
            lines.append(f"- {cedula} {nombre} - Plan: {plan} · ${monto:.2f} (Bs. {monto_bs:,.2f}) [{metodo}{ref}]")

    lines.extend([
        f"Total Membresías USD: ${total_payments_usd:.2f}",
        f"Total Membresías Bs.: Bs. {total_payments_bs:,.2f}",
        "",
        "RESUMEN DE COBROS POR MÉTODO:",
        "------------------------------------------",
    ])

    for method, totals in sorted(methods_totals.items()):
        lines.append(f"- {method.capitalize()}: ${totals['usd']:.2f} | Bs. {totals['bs']:,.2f}")

    lines.extend([
        "",
        "VENTAS POS (CANTINA):",
        "------------------------------------------",
    ])

    if not sales:
        lines.append(" (Sin ventas registradas hoy)")
    else:
        for s in sales:
            prod = s.get("producto", "Item")
            sm = float(s.get("monto", 0.0))
            lines.append(f"- {prod}: ${sm:.2f} (Bs. {sm * rate:,.2f})")

    lines.extend([
        f"Total Ventas POS USD: ${total_sales_usd:.2f}",
        f"Total Ventas POS Bs.: Bs. {total_sales_bs:,.2f}",
        "",
        "RESUMEN DE ACCESOS:",
        "------------------------------------------",
        f"- Total de accesos hoy: {len(access)}",
        f"- Accesos Permitidos: {allowed_count}",
        f"- Salidas (Check-out): {checkout_count}",
        f"- Accesos Denegados: {denied_count}",
        "==========================================",
        f"TOTAL GENERAL USD: ${total_general_usd:.2f}",
        f"TOTAL GENERAL BS. : Bs. {total_general_bs:,.2f}",
        "==========================================",
    ])

    return "\n".join(lines)


def _excel_base_styles():
    """Return styling tools for openpyxl workbooks."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    title_font = Font(name="Calibri", size=14, bold=True, color="1E293B")
    regular_font = Font(name="Calibri", size=11)
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )
    return (
        openpyxl,
        Alignment,
        Border,
        Font,
        PatternFill,
        Side,
        get_column_letter,
        header_font,
        header_fill,
        title_font,
        regular_font,
        thin_border,
    )


def _autosize_worksheet(ws, get_column_letter):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            v_str = str(cell.value or "")
            if len(v_str) > max_len:
                max_len = len(v_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)


def generate_excel_report(
    filepath: str,
    target_date: Optional[date] = None,
    payments: Optional[List[Dict[str, Any]]] = None,
    sales: Optional[List[Dict[str, Any]]] = None,
    access: Optional[List[Dict[str, Any]]] = None,
    start_time_str: Optional[str] = None,
    end_time_str: Optional[str] = None,
    bcv_rate: Optional[float] = None,
) -> str:
    """Generate full 5-sheet financial Excel workbook."""
    styles = _excel_base_styles()
    (
        openpyxl,
        Alignment,
        Border,
        Font,
        PatternFill,
        Side,
        get_column_letter,
        header_font,
        header_fill,
        title_font,
        regular_font,
        thin_border,
    ) = styles

    wb = openpyxl.Workbook()
    target_date = target_date or datetime.now().date()
    rate = bcv_rate if bcv_rate is not None and bcv_rate > 0 else bcv_service.get_rate()

    payments = payments or []
    sales = sales or []
    access = access or []

    # Sheet 1: Membresias y Pagos
    ws1 = wb.active
    ws1.title = "Membresias y Pagos"
    ws1.cell(1, 1, f"Reporte de Membresías - Turno: {start_time_str or ''} a {end_time_str or ''}").font = title_font
    ws1.cell(2, 1, f"Tasa BCV del día: {rate:.2f} Bs/$").font = regular_font

    headers1 = [
        "Cédula", "Nombre", "Plan", "Monto ($)", "Monto (Bs.)", "Método", "Referencia", "Nota", "Fecha Pago", "Registrador"
    ]
    for col_idx, h in enumerate(headers1, 1):
        c = ws1.cell(4, col_idx, h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    row_idx = 5
    for p in payments:
        m_usd = float(p.get("monto", 0.0))
        m_bs = float(p.get("monto_bs", 0.0)) or (m_usd * rate)
        ws1.cell(row_idx, 1, p.get("cedula", ""))
        ws1.cell(row_idx, 2, p.get("nombre", "Desconocido"))
        ws1.cell(row_idx, 3, p.get("plan", ""))
        c4 = ws1.cell(row_idx, 4, m_usd)
        c4.number_format = "$#,##0.00"
        c5 = ws1.cell(row_idx, 5, m_bs)
        c5.number_format = "Bs #,##0.00"
        ws1.cell(row_idx, 6, p.get("metodo", "efectivo"))
        ws1.cell(row_idx, 7, p.get("referencia", ""))
        ws1.cell(row_idx, 8, p.get("nota", ""))
        ws1.cell(row_idx, 9, str(p.get("fecha_pago", "")))
        ws1.cell(row_idx, 10, p.get("registrado_por", "sistema"))
        row_idx += 1

    # Totals
    ws1.cell(row_idx, 3, "TOTAL GENERAL").font = Font(bold=True)
    c_tot_usd = ws1.cell(row_idx, 4, f"=SUM(D5:D{row_idx - 1})" if row_idx > 5 else 0.0)
    c_tot_usd.font = Font(bold=True)
    c_tot_usd.number_format = "$#,##0.00"
    c_tot_bs = ws1.cell(row_idx, 5, f"=SUM(E5:E{row_idx - 1})" if row_idx > 5 else 0.0)
    c_tot_bs.font = Font(bold=True)
    c_tot_bs.number_format = "Bs #,##0.00"

    _autosize_worksheet(ws1, get_column_letter)

    # Sheet 2: Ventas Cantina
    ws2 = wb.create_sheet(title="Ventas Cantina")
    ws2.cell(1, 1, "Reporte de Ventas de Cantina (POS)").font = title_font
    headers2 = ["Producto", "Monto ($)", "Monto (Bs.)", "Hora / Fecha"]
    for col_idx, h in enumerate(headers2, 1):
        c = ws2.cell(3, col_idx, h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    r2 = 4
    for s in sales:
        sm = float(s.get("monto", 0.0))
        ws2.cell(r2, 1, s.get("producto", ""))
        c_sm = ws2.cell(r2, 2, sm)
        c_sm.number_format = "$#,##0.00"
        c_bs = ws2.cell(r2, 3, sm * rate)
        c_bs.number_format = "Bs #,##0.00"
        time_display = s.get("hora") or s.get("sold_at") or ""
        ws2.cell(r2, 4, str(time_display))
        r2 += 1

    ws2.cell(r2, 1, "TOTAL VENTAS").font = Font(bold=True)
    ws2.cell(r2, 2, f"=SUM(B4:B{r2 - 1})" if r2 > 4 else 0.0).font = Font(bold=True)
    ws2.cell(r2, 3, f"=SUM(C4:C{r2 - 1})" if r2 > 4 else 0.0).font = Font(bold=True)
    _autosize_worksheet(ws2, get_column_letter)

    # Sheet 3: Accesos del Dia
    ws3 = wb.create_sheet(title="Accesos del Dia")
    ws3.cell(1, 1, "Log de Accesos de Clientes").font = title_font
    headers3 = ["Cédula", "Nombre", "Plan", "Estado / Acción", "Hora"]
    for col_idx, h in enumerate(headers3, 1):
        c = ws3.cell(3, col_idx, h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    r3 = 4
    for a in access:
        ws3.cell(r3, 1, a.get("cedula", ""))
        ws3.cell(r3, 2, a.get("nombre", ""))
        ws3.cell(r3, 3, a.get("plan", ""))
        ws3.cell(r3, 4, a.get("status", ""))
        ws3.cell(r3, 5, str(a.get("hora") or a.get("event_time") or ""))
        r3 += 1
    _autosize_worksheet(ws3, get_column_letter)

    # Sheet 4: Resumen General
    ws4 = wb.create_sheet(title="Resumen General")
    ws4.cell(1, 1, "Resumen Consolidado de Caja").font = title_font
    ws4.cell(2, 1, f"Tasa BCV: {rate:.2f} Bs/$").font = regular_font

    ws4.cell(4, 1, "Concepto").font = header_font
    ws4.cell(4, 1).fill = header_fill
    ws4.cell(4, 2, "Total ($)").font = header_font
    ws4.cell(4, 2).fill = header_fill
    ws4.cell(4, 3, "Total (Bs.)").font = header_font
    ws4.cell(4, 3).fill = header_fill

    ws4.cell(5, 1, "Membresías y Renovaciones")
    ws4.cell(5, 2, f"='Membresias y Pagos'!D{row_idx}")
    ws4.cell(5, 3, f"='Membresias y Pagos'!E{row_idx}")

    ws4.cell(6, 1, "Ventas de Cantina (POS)")
    ws4.cell(6, 2, f"='Ventas Cantina'!B{r2}")
    ws4.cell(6, 3, f"='Ventas Cantina'!C{r2}")

    ws4.cell(7, 1, "TOTAL GENERAL CAJA").font = Font(bold=True)
    ws4.cell(7, 2, "=SUM(B5:B6)").font = Font(bold=True)
    ws4.cell(7, 3, "=SUM(C5:C6)").font = Font(bold=True)
    _autosize_worksheet(ws4, get_column_letter)

    # Save to disk
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb.save(filepath)
    return filepath


def export_contacts_excel() -> str:
    """Export member contacts list to Excel."""
    styles = _excel_base_styles()
    (
        openpyxl,
        Alignment,
        Border,
        Font,
        PatternFill,
        Side,
        get_column_letter,
        header_font,
        header_fill,
        title_font,
        regular_font,
        thin_border,
    ) = styles

    from core.repositories import MemberRepository, AccessRepository

    members = MemberRepository.list_all()
    cedulas = [m["cedula"] for m in members]
    checkins = AccessRepository.get_last_checkins_map(cedulas)

    export_dir = get_contacts_export_dir()
    os.makedirs(export_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(export_dir, f"contactos_{timestamp}.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Contactos"

    ws.cell(1, 1, "Gymsis — Lista de Contactos").font = title_font
    ws.cell(2, 1, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font = regular_font

    headers = ["Cédula", "Nombre", "Teléfono", "Plan", "Estado", "Vencimiento", "Último ingreso"]
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(4, col_idx, h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    for row_idx, m in enumerate(members, 5):
        ced = m.get("cedula", "")
        last_checkin = checkins.get(ced)
        last_str = AccessRepository.format_last_checkin_short(ced, last_checkin) if last_checkin else "Nunca"

        ws.cell(row_idx, 1, ced)
        ws.cell(row_idx, 2, m.get("nombre", ""))
        ws.cell(row_idx, 3, m.get("telefono", ""))
        ws.cell(row_idx, 4, m.get("plan", ""))
        ws.cell(row_idx, 5, m.get("estado", ""))
        ws.cell(row_idx, 6, str(m.get("vencimiento", "")))
        ws.cell(row_idx, 7, last_str)

    _autosize_worksheet(ws, get_column_letter)
    wb.save(filepath)
    return filepath


def export_inactive_members_excel(min_days: int = 15, members: Optional[List[Dict[str, Any]]] = None) -> str:
    """Export members with low attendance (retention analysis) to Excel."""
    styles = _excel_base_styles()
    (
        openpyxl,
        Alignment,
        Border,
        Font,
        PatternFill,
        Side,
        get_column_letter,
        header_font,
        header_fill,
        title_font,
        regular_font,
        thin_border,
    ) = styles

    from core.repositories import MemberRepository

    if members is None:
        members = MemberRepository.list_low_attendance(min_days=min_days)

    export_dir = os.path.join(get_reports_root(), "retencion")
    os.makedirs(export_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(export_dir, f"inactivos_{min_days}d_{timestamp}.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Retención"

    ws.cell(1, 1, f"Gymsis — Miembros sin ingreso ({min_days}+ días)").font = title_font
    ws.cell(2, 1, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}").font = regular_font

    headers = ["Cédula", "Nombre", "Teléfono", "Plan", "Estado", "Vencimiento", "Días sin ingreso", "Último ingreso"]
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(4, col_idx, h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center")

    for row_idx, m in enumerate(members, 5):
        ws.cell(row_idx, 1, m.get("cedula", ""))
        ws.cell(row_idx, 2, m.get("nombre", ""))
        ws.cell(row_idx, 3, m.get("telefono", ""))
        ws.cell(row_idx, 4, m.get("plan", ""))
        ws.cell(row_idx, 5, m.get("estado", ""))
        ws.cell(row_idx, 6, str(m.get("vencimiento", "")))
        ws.cell(row_idx, 7, m.get("dias_sin_ingreso", "Nunca"))
        ws.cell(row_idx, 8, m.get("ultimo_ingreso", "Nunca"))

    _autosize_worksheet(ws, get_column_letter)
    wb.save(filepath)
    return filepath


def save_daily_report_files(
    target_date: date,
    bcv_rate: float,
    payments: list[dict] | None = None,
    sales: list[dict] | None = None,
    access: list[dict] | None = None,
    start_time_str: str | None = None,
    end_time_str: str | None = None,
    txt_prefix: str = "reporte_diario",
    xlsx_prefix: str = "reporte_diario",
    timestamp_suffix: str | None = None,
) -> tuple[str, str]:
    reports_dir = get_reports_dir(target_date)
    os.makedirs(reports_dir, exist_ok=True)
    target_date_str = target_date.isoformat()

    if payments is None:
        from core.db_store import load_membership_payments
        all_p = load_membership_payments(limit=2000)
        payments = [p for p in all_p if str(p.get("fecha_pago", ""))[:10] == target_date_str]

    if sales is None:
        from core.db_store import load_sales
        all_s = load_sales(limit=2000)
        sales = [s for s in all_s if (s.get("fecha") or str(s.get("sold_at", ""))[:10]) == target_date_str]

    if access is None:
        from core.db_store import load_access_log
        all_a = load_access_log(limit=2000)
        access = [a for a in all_a if (a.get("fecha") or str(a.get("event_time", ""))[:10]) == target_date_str]

    if timestamp_suffix:
        file_path_txt = os.path.join(reports_dir, f"{txt_prefix}_{timestamp_suffix}.txt")
        file_path_xlsx = os.path.join(reports_dir, f"{xlsx_prefix}_{timestamp_suffix}.xlsx")
    else:
        file_path_txt = os.path.join(reports_dir, f"{txt_prefix}_{target_date_str}.txt")
        file_path_xlsx = os.path.join(reports_dir, f"{xlsx_prefix}_{target_date_str}.xlsx")

    report_text = generate_report_text(
        target_date=target_date,
        bcv_rate=bcv_rate,
        payments=payments,
        sales=sales,
        access=access,
        start_time_str=start_time_str,
        end_time_str=end_time_str,
    )

    with open(file_path_txt, "w", encoding="utf-8") as f:
        f.write(report_text)

    generate_excel_report(
        file_path_xlsx,
        target_date=target_date,
        bcv_rate=bcv_rate,
        payments=payments,
        sales=sales,
        access=access,
        start_time_str=start_time_str,
        end_time_str=end_time_str,
    )

    return file_path_txt, file_path_xlsx

