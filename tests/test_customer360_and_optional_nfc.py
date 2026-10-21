import os
import tempfile
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("GYMSIS_SQLITE_PATH", os.path.join(tempfile.gettempdir(), "gymsis_test_suite.db"))

from core.mock_data import register_member, find_member_by_cedula
from core.business import process_membership_payment, get_member_full_profile
from core.db_store import save_access_event, bootstrap_database
from core.cash_closure import perform_cash_closure


class TestCustomer360AndOptionalNFC(unittest.TestCase):
    """Test suite for optional NFC registration, customer 360 profile, and manual shift closures."""

    @classmethod
    def setUpClass(cls):
        bootstrap_database()

    def test_register_member_without_nfc(self):
        """Members without NFC card must be registered cleanly with empty nfc_id."""
        ts = int(datetime.now().timestamp() * 1000)
        test_cedula = f"V-OPT-{ts}"
        m = register_member(
            cedula=test_cedula,
            nombre="Socio Sin NFC",
            plan="Semanal",
            nfc_id="",
            telefono="04241112233",
        )
        self.assertIsNotNone(m)
        self.assertEqual(m["cedula"], test_cedula)
        self.assertEqual(m["nfc_id"], "")

        # Verify from in-memory search
        found = find_member_by_cedula(test_cedula)
        self.assertIsNotNone(found)
        self.assertEqual(found["nfc_id"], "")

    def test_duplicate_cedula_raises_error(self):
        """Registering an existing cédula must raise ValueError with clear message."""
        ts = int(datetime.now().timestamp() * 1000)
        test_cedula = f"V-DUP-{ts}"
        register_member(
            cedula=test_cedula,
            nombre="Socio Original",
            plan="Semanal",
            nfc_id="",
        )
        with self.assertRaises(ValueError) as ctx:
            register_member(
                cedula=test_cedula,
                nombre="Socio Duplicado",
                plan="Mensual",
                nfc_id="",
            )
        self.assertIn("ya existe", str(ctx.exception).lower())

    def test_get_member_full_profile(self):
        """get_member_full_profile must aggregate personal info, attendance metrics and payments."""
        ts = int(datetime.now().timestamp() * 1000)
        test_cedula = f"V-P360-{ts}"
        register_member(
            cedula=test_cedula,
            nombre="Maria 360 Test",
            plan="Semanal",
            nfc_id="",
            telefono="04123334455",
        )

        # Process a payment
        process_membership_payment(
            cedula=test_cedula,
            plan="Semanal",
            amount=7.00,
            days=7,
            method="Efectivo USD",
            note="Ref Test 360",
        )

        # Record access events
        save_access_event({
            "cedula": test_cedula,
            "nombre": "Maria 360 Test",
            "plan": "Semanal",
            "status": "CONCEDIDO",
        })

        profile = get_member_full_profile(test_cedula)
        self.assertNotIn("error", profile)
        self.assertEqual(profile["member"]["cedula"], test_cedula)
        self.assertGreaterEqual(len(profile["payments"]), 1)
        self.assertGreaterEqual(len(profile["access_logs"]), 1)

        stats = profile["stats"]
        self.assertGreaterEqual(stats["total_visits"], 1)
        self.assertGreaterEqual(stats["total_paid_usd"], 7.00)
        self.assertIsNotNone(stats["usual_hour"])

    def test_manual_shift_closure(self):
        """perform_cash_closure with trigger='manual' must update last_close_timestamp and return file paths."""
        closure = perform_cash_closure(trigger="manual")
        self.assertIn("txt_path", closure)
        self.assertIn("xlsx_path", closure)
        self.assertIn("relative_folder", closure)


if __name__ == "__main__":
    unittest.main()
