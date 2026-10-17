"""Gymsis — Entry point."""

import os
import traceback

import flet as ft
import core.theme  # Apply cross-version Flet shims early
from app import GymsisApp
from core.db_store import bootstrap_database, hydrate_mock_data_from_db
from core.env_loader import load_env_file


def main(page: ft.Page):
    try:
        bootstrap_database()
        hydrate_mock_data_from_db()
        app = GymsisApp(page)
        app.start()
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
    run_mode = os.getenv("GYMSIS_RUN_MODE", "auto").lower()

    if run_mode in ("desktop", "auto"):
        try:
            import flet_desktop  # noqa: F401
            run_mode = "desktop"
        except ImportError:
            run_mode = "web"

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
            web_renderer = ft.WebRenderer.AUTO

        print(f"[Gymsis] Servidor web iniciado en http://localhost:{port}")
        ft.run(
            main,
            view=ft.AppView.WEB_BROWSER,
            host=host,
            port=port,
            web_renderer=web_renderer,
        )
    else:
        ft.run(main)

