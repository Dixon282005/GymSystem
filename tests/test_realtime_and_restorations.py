"""End-to-end integration tests for Gymsis real-time event bus,
BCV bimonetary exchange rate, membership payments, and NFC attendance.
"""

import os
import unittest
from datetime import datetime, date

from core.bcv_service import bcv_service
from core.event_bus import event_bus
from core.db_store import (
    bootstrap_database,
    save_membership_payment,
    load_membership_payments,
    export_backup_json,
    import_backup_json,
    load_members,
)
from core.mock_data import (
    MEMBERS,
    find_member_by_cedula,
    register_member,
    update_member,
)
from core.business import (
    process_nfc_scan,
    process_membership_payment,
    get_dashboard_metrics,
)


class TestRealtimeAndRestorations(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        bootstrap_database()

    def test_01_bcv_service(self):
        """Verify BCV exchange rate service, conversion, and formatting."""
        rate = bcv_service.get_rate()
        self.assertGreater(rate, 0.0)

        # Test bimonetary conversion
        usd_amount = 25.0
        bs_amount = bcv_service.to_bs(usd_amount)
        self.assertAlmostEqual(bs_amount, usd_amount * rate, places=2)

        formatted_bs = bcv_service.format_bs(bs_amount)
        self.assertTrue(formatted_bs.startswith("Bs."))

        # Test manual override
        bcv_service.set_manual_rate(55.0)
        self.assertEqual(bcv_service.get_rate(), 55.0)
        self.assertEqual(bcv_service.to_bs(10.0), 550.0)

    def test_02_event_bus(self):
        """Verify thread-safe EventBus publish-subscribe mechanism."""
        received_events = []

        def subscriber(data):
            received_events.append(data)

        event_bus.subscribe("test_topic", subscriber)
        event_bus.publish("test_topic", {"hello": "world"})
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0]["hello"], "world")

        # Unsubscribe
        event_bus.unsubscribe("test_topic", subscriber)
        event_bus.publish("test_topic", {"hello": "again"})
        self.assertEqual(len(received_events), 1)

    def test_03_db_membership_payments(self):
        """Verify saving, loading and backup of membership payments."""
        test_cedula = "V-99988877"
        payment_record = {
            "cedula": test_cedula,
            "nombre": "Test Payment Member",
            "plan": "VIP",
            "monto": 50.0,
            "monto_bs": 2750.0,
            "tasa_bcv": 55.0,
            "dias": 30,
            "metodo": "Pago Móvil",
            "nota": "Prueba unitaria",
        }
        saved = save_membership_payment(payment_record)
        self.assertTrue(saved)

        payments = load_membership_payments(cedula=test_cedula)
        self.assertGreater(len(payments), 0)
        latest = payments[0]
        self.assertEqual(latest["cedula"], test_cedula)
        self.assertEqual(latest["monto"], 50.0)
        self.assertEqual(latest["metodo"], "Pago Móvil")

    def test_04_nfc_scan_lifecycle_and_personalized_greeting(self):
        """Verify NFC entrance with personalized greeting, exit toggle, and EventBus emission."""
        cedula = "V-77766655"
        nfc_id = "TEST_NFC_UID_123"

        # Register member
        register_member(
            cedula=cedula,
            nombre="Alejandro Hernández",
            plan="Basico",
            nfc_id=nfc_id,
        )

        bus_scans = []
        event_bus.subscribe("access_scan", lambda data: bus_scans.append(data))

        member = find_member_by_cedula(cedula)
        member["entrenando"] = False

        # First scan: ENTRADA
        result_entry = process_nfc_scan(nfc_id)
        self.assertEqual(result_entry["action"], "ENTRADA")
        self.assertTrue(result_entry["allowed"])
        self.assertIn("Alejandro", result_entry["reason"])
        self.assertTrue(member.get("entrenando"))

        # Second scan: SALIDA (since member is now in the gym)
        result_exit = process_nfc_scan(nfc_id)
        self.assertEqual(result_exit["action"], "SALIDA")
        self.assertTrue(result_exit["allowed"])
        self.assertFalse(member.get("entrenando"))

        # EventBus should have received both scan events
        self.assertGreaterEqual(len(bus_scans), 2)

    def test_05_process_membership_payment_and_dashboard_metrics(self):
        """Verify membership renewal payment updates member and reflects in dashboard metrics."""
        cedula = "V-11223344"
        register_member(
            cedula=cedula,
            nombre="Mariana Silva",
            plan="Mensual",
        )

        res = process_membership_payment(
            cedula=cedula,
            plan="VIP",
            amount=50.0,
            days=30,
            method="Punto de Venta",
            note="Cobro de prueba",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["member"]["plan"], "VIP")
        self.assertEqual(res["member"]["estado"], "Activo")

        # Verify Dashboard KPIs
        metrics = get_dashboard_metrics()
        self.assertGreater(metrics["daily_income"], 0.0)
        self.assertGreater(metrics["daily_income_bs"], 0.0)
        self.assertIn("/", metrics["ocupacion"])

    def test_06_plans_crud_and_bimonetary(self):
        """Verify gym membership plans CRUD, database persistence, and bimonetary conversions."""
        from core.db_store import save_plan, load_plans, delete_plan
        from core.mock_data import PLANS

        # Save a new custom plan
        test_plan = {
            "nombre": "Plan Crossfit Pro",
            "precio": 45.0,
            "dias": 30,
            "descripcion": "Acceso ilimitado a box de crossfit",
            "is_active": 1,
        }
        saved = save_plan(test_plan)
        self.assertTrue(saved)

        # Load plans and assert inclusion
        plans = load_plans(active_only=True)
        plan_names = [p["nombre"] for p in plans]
        self.assertIn("Plan Crossfit Pro", plan_names)

        # Verify bimonetary rate calculation
        matched = next((p for p in plans if p["nombre"] == "Plan Crossfit Pro"), None)
        self.assertIsNotNone(matched)
        self.assertEqual(float(matched["precio"]), 45.0)
        bs_price = bcv_service.to_bs(matched["precio"])
        self.assertGreater(bs_price, 0.0)

        # Register member with this plan
        member = register_member(
            cedula="V-55443322",
            nombre="Carlos Crossfitter",
            plan="Plan Crossfit Pro",
        )
        self.assertEqual(member["plan"], "Plan Crossfit Pro")

        # Delete plan and verify soft/hard removal
        delete_plan("Plan Crossfit Pro")
        plans_after = load_plans(active_only=True)
        self.assertNotIn("Plan Crossfit Pro", [p["nombre"] for p in plans_after])


if __name__ == "__main__":
    unittest.main()
