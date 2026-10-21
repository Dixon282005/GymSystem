from __future__ import annotations
import os
from datetime import datetime, timedelta

from core.business import log_action, register_access_attempt
from core.reports_export import (
    collect_shift_data,
    generate_excel_report,
    generate_report_text,
    get_reports_dir,
)
from core.repositories import MemberRepository, SettingsRepository


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _format_timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def _next_midnight_after(last_close: datetime) -> datetime:
    return datetime.combine(last_close.date() + timedelta(days=1), datetime.min.time())


def checkout_all_members_inside() -> int:
    count = 0
    for member in MemberRepository.list_all():
        if member.get("entrenando"):
            register_access_attempt(
                member["cedula"],
                member=member,
                allowed=True,
                action="checkout",
            )
            count += 1
    return count


def perform_cash_closure(
    end_time: datetime | None = None,
    auto_checkout: bool = False,
    trigger: str = "manual",
) -> dict:
    if end_time is None:
        end_time = datetime.now()

    settings = SettingsRepository.get_all()
    start_time_str = settings.get("last_close_timestamp", "")
    if not start_time_str:
        start_time_str = f"{end_time.date().isoformat()} 00:00"
    end_time_str = _format_timestamp(end_time)

    payments_shift, sales_shift, access_shift = collect_shift_data(start_time_str, end_time_str)

    checkout_count = 0
    if auto_checkout:
        checkout_count = checkout_all_members_inside()

    reports_dir = get_reports_dir(end_time)
    os.makedirs(reports_dir, exist_ok=True)

    month_folder = end_time.strftime("%Y-%m")
    date_folder = end_time.strftime("%Y-%m-%d")
    timestamp_file = end_time.strftime("%Y%m%d_%H%M%S")

    report_text = generate_report_text(
        target_date=end_time.date(),
        payments=payments_shift,
        sales=sales_shift,
        access=access_shift,
        start_time_str=start_time_str,
        end_time_str=end_time_str,
    )

    file_path_txt = os.path.join(reports_dir, f"cierre_turno_{timestamp_file}.txt")
    with open(file_path_txt, "w", encoding="utf-8") as f:
        f.write(report_text)

    file_path_xlsx = os.path.join(reports_dir, f"cierre_turno_{timestamp_file}.xlsx")
    generate_excel_report(
        file_path_xlsx,
        target_date=end_time.date(),
        payments=payments_shift,
        sales=sales_shift,
        access=access_shift,
        start_time_str=start_time_str,
        end_time_str=end_time_str,
    )

    settings["last_close_timestamp"] = end_time_str
    SettingsRepository.save_all(settings)

    log_action(
        "CIERRE_DE_CAJA",
        {
            "trigger": trigger,
            "desde": start_time_str,
            "hasta": end_time_str,
            "checkout_automatico": auto_checkout,
            "personas_expulsadas": checkout_count,
            "archivo": f"reports/{month_folder}/{date_folder}/cierre_turno_{timestamp_file}.xlsx",
        },
    )

    return {
        "start_time_str": start_time_str,
        "end_time_str": end_time_str,
        "checkout_count": checkout_count,
        "txt_path": file_path_txt,
        "xlsx_path": file_path_xlsx,
        "relative_folder": f"reports/{month_folder}/{date_folder}",
    }


def run_pending_daily_closures(max_iterations: int = 60) -> list[dict]:
    now = datetime.now()
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    settings = SettingsRepository.get_all()
    last_close_str = settings.get("last_close_timestamp", "")
    auto_checkout = bool(settings.get("auto_checkout_on_close", False))

    if not last_close_str:
        settings["last_close_timestamp"] = _format_timestamp(today_midnight)
        SettingsRepository.save_all(settings)
        return []

    results = []
    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        settings = SettingsRepository.get_all()
        last_close_str = settings.get("last_close_timestamp", "")
        if not last_close_str:
            return results
        try:
            last_close_dt = _parse_timestamp(last_close_str)
        except Exception:
            settings["last_close_timestamp"] = _format_timestamp(today_midnight)
            SettingsRepository.save_all(settings)
            return results

        if last_close_dt >= today_midnight:
            return results
        next_midnight = _next_midnight_after(last_close_dt)
        if now < next_midnight:
            return results
        result = perform_cash_closure(next_midnight, auto_checkout=auto_checkout, trigger="auto")
        results.append(result)
        print(f"[Cash Closure] Cierre automático completado: {result['start_time_str']} → {result['end_time_str']}")

    return results


def seconds_until_next_midnight() -> float:
    now = datetime.now()
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(30.0, (next_midnight - now).total_seconds())
