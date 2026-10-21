import os
import signal
import sys
import atexit
import traceback

import flet as ft
import core.theme  # Apply cross-version Flet shims early
from app import GymsisApp
from core.db_store import bootstrap_database, hydrate_mock_data_from_db
from core.env_loader import load_env_file


def _on_system_exit():
    try:
        from core.db_store import _connect_sqlite, get_active_engine
        if get_active_engine() == "sqlite":
            conn = _connect_sqlite()
            conn.execute("PRAGMA wal_checkpoint(FULL);")
            conn.close()
        print("[Gymsis] Estado de base de datos sincronizado correctamente al salir.")
    except Exception as ex:
        print(f"[Gymsis] Aviso al cerrar: {ex}")


atexit.register(_on_system_exit)


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


def _kill_conflicting_processes(port: int = 8550):
    try:
        import subprocess
        if sys.platform == "win32":
            cmd = f'netstat -ano | findstr ":{port}"'
            try:
                out = subprocess.check_output(cmd, shell=True).decode("utf-8", errors="ignore")
                for line in out.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and f":{port}" in parts[1]:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != os.getpid():
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            try:
                subprocess.run(["fuser", "-k", f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        bundled_app = os.path.join(meipass, "flet_desktop", "app")
        if os.path.exists(os.path.join(bundled_app, "flet.exe")):
            os.environ["FLET_VIEW_PATH"] = bundled_app

    load_env_file()
    run_mode = os.getenv("GYMSIS_RUN_MODE", "desktop").lower()

    if run_mode in ("desktop", "auto"):
        try:
            import flet_desktop  # noqa: F401
            run_mode = "desktop"
        except ImportError:
            print("[Gymsis] flet-desktop no disponible, iniciando en modo navegador...")
            run_mode = "web"

    if run_mode == "web":
        host = os.getenv("GYMSIS_HOST", "0.0.0.0")
        port = int(os.getenv("GYMSIS_PORT", "8550"))
        _kill_conflicting_processes(port)
        renderer_name = os.getenv("GYMSIS_WEB_RENDERER", "auto").lower()
        if renderer_name in ("canvaskit", "canvas_kit"):
            web_renderer = ft.WebRenderer.CANVAS_KIT
        elif renderer_name == "skwasm":
            web_renderer = ft.WebRenderer.SKWASM
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
        print("[Gymsis] Iniciando Gymsis como aplicacion de escritorio nativa...")
        ft.run(main)

