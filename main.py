"""Gymsis — Entry point."""

import os
import traceback

import flet as ft
from app import GymsisApp
from core.db_store import bootstrap_database, hydrate_mock_data_from_db
from core.env_loader import load_env_file


def main(page: ft.Page):
    try:
        bootstrap_database()
        hydrate_mock_data_from_db()
        app = GymsisApp(page)
        app.show_login()
    except Exception as exc:
        error_text = traceback.format_exc()
        print(error_text)
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column(
                    controls=[
                        ft.Text("Error iniciando Gymsis", size=22, color="#ef4444", weight="w700"),
                        ft.Text(str(exc), size=14, color="#f8fafc"),
                        ft.Text(error_text, size=12, color="#94a3b8", selectable=True),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    spacing=10,
                ),
                padding=20,
                expand=True,
            )
        )
        page.update()


if __name__ == "__main__":
    load_env_file()
    run_mode = os.getenv("GYMSIS_RUN_MODE", "desktop").lower()

    if run_mode == "web":
        host = os.getenv("GYMSIS_HOST", "0.0.0.0")
        port = int(os.getenv("GYMSIS_PORT", "8550"))
        renderer_name = os.getenv("GYMSIS_WEB_RENDERER", "canvaskit").lower()
        if renderer_name in ("canvaskit", "canvas_kit"):
            web_renderer = ft.WebRenderer.CANVAS_KIT
        elif renderer_name == "skwasm":
            web_renderer = ft.WebRenderer.SKWASM
        elif renderer_name == "auto":
            web_renderer = ft.WebRenderer.AUTO
        else:
            # Flet 0.84 has no HTML renderer; AUTO is the widest-compatible fallback.
            web_renderer = ft.WebRenderer.AUTO

        ft.run(
            main,
            view=ft.AppView.WEB_BROWSER,
            host=host,
            port=port,
            web_renderer=web_renderer,
        )
    else:
        ft.run(main)
