import unittest
import threading
import time
from unittest.mock import MagicMock, patch

from core.event_bus import EventBus
from core.nfc_service import WinSCardDriver, nfc_reader
from core.audio_service import AudioService
import flet as ft
from ui.views.kiosk_view import KioskView
from ui.views.access_view import AccessView
from ui.views.dashboard_view import DashboardView


class TestNfcAudioStability(unittest.TestCase):
    def test_winscard_driver_lock_exists(self):
        driver = WinSCardDriver()
        self.assertTrue(hasattr(driver, "_lock"))
        self.assertIsInstance(driver._lock, type(threading.RLock()))

    def test_audio_service_no_blocking_sleep(self):
        audio = AudioService()
        # Test speaking runs asynchronously and doesn't block main thread
        start = time.time()
        audio.speak("Bienvenido acceso concedido")
        elapsed = time.time() - start
        self.assertLess(elapsed, 0.5, "Audio speak blocked the calling thread!")

    def test_event_bus_catches_unmounted_controls(self):
        bus = EventBus()
        # Create a mock control that raises Column Control must be added to the page first
        def faulty_callback(data):
            raise RuntimeError("Column Control must be added to the page first")

        bus.subscribe("test_event", faulty_callback)
        # Should NOT raise, and should prune the dead callback
        bus.publish("test_event", {"status": "ok"})
        self.assertEqual(len(bus._subscribers.get("test_event", [])), 0)

    def test_unmounted_views_do_not_crash_on_event_bus_scan(self):
        # Instantiate views without adding to a page
        kiosk = KioskView()
        access = AccessView()
        dashboard = DashboardView()

        # Simulate access scan event bus publish
        from core.event_bus import event_bus
        scan_data = {
            "action": "ENTRADA",
            "allowed": True,
            "member": {"cedula": "V-12345678", "nombre": "Socio Prueba", "plan": "VIP"},
            "reason": "¡Bienvenido, Socio Prueba!",
        }

        # Should execute completely without raising any exception
        try:
            event_bus.publish("access_scan", scan_data)
        except Exception as ex:
            self.fail(f"event_bus.publish crashed with unmounted views: {ex}")


if __name__ == "__main__":
    unittest.main()
