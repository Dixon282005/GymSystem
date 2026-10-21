import os
import tempfile
import unittest
from datetime import datetime, date, timedelta

os.environ.setdefault("GYMSIS_SQLITE_PATH", os.path.join(tempfile.gettempdir(), "gymsis_test_suite.db"))

from core.db_store import bootstrap_database
from core.mock_data import (
    register_member,
    find_member_by_cedula,
    deactivate_member,
    reactivate_member,
    remove_member,
    renew_member_plan,
)
from core.business import process_membership_payment, can_member_access


class TestSoftDeleteAndExpiration(unittest.TestCase):
    """Verify that daily pass expiration is calculated accurately (1 day = today)
    and that members are soft-deleted (Inactivos) without losing database records.
    """

    @classmethod
    def setUpClass(cls):
        bootstrap_database()

    def test_daily_pass_expires_today(self):
        """Pase Diario (1 day) registered today must expire today, allowing entrance today and expiring tomorrow."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula = f"V-DAY-{ts}"
        today_str = date.today().strftime("%Y-%m-%d")

        member = register_member(
            cedula=cedula,
            nombre="Cliente Pase Diario",
            plan="Pase Diario",
            dias=1,
            nfc_id="",
        )

        # Record initial payment with is_initial=True
        process_membership_payment(
            cedula=cedula,
            plan="Pase Diario",
            amount=2.5,
            days=1,
            method="Efectivo USD",
            is_initial=True,
        )

        refreshed = find_member_by_cedula(cedula)
        self.assertEqual(refreshed["vencimiento"], today_str, "Pase Diario must expire today")

        # Allowed today
        allowed, reason = can_member_access(refreshed)
        self.assertTrue(allowed)
        self.assertEqual(reason, "Acceso permitido")

    def test_soft_delete_preserves_member_and_marks_inactivo(self):
        """Deactivating a member must keep the record with estado='Inactivo' and prevent access."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula = f"V-SOFT-{ts}"

        register_member(
            cedula=cedula,
            nombre="Cliente Para Desactivar",
            plan="Mensual",
            dias=30,
        )

        ok = deactivate_member(cedula)
        self.assertTrue(ok)

        member = find_member_by_cedula(cedula)
        self.assertIsNotNone(member)
        self.assertEqual(member["estado"], "Inactivo")
        self.assertFalse(member["entrenando"])

        # Access must be denied
        allowed, reason = can_member_access(member)
        self.assertFalse(allowed)
        self.assertEqual(reason, "Miembro inactivo")

    def test_reactivate_member(self):
        """Reactivating a member must restore their status without losing any data."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula = f"V-REACT-{ts}"

        register_member(
            cedula=cedula,
            nombre="Cliente Reactivable",
            plan="Mensual",
            dias=30,
        )
        deactivate_member(cedula)
        self.assertEqual(find_member_by_cedula(cedula)["estado"], "Inactivo")

        ok = reactivate_member(cedula)
        self.assertTrue(ok)
        self.assertEqual(find_member_by_cedula(cedula)["estado"], "Activo")

    def test_remove_member_defaults_to_soft_delete(self):
        """Calling remove_member without hard_delete=True should soft delete (set Inactivo)."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula = f"V-RM-{ts}"

        register_member(
            cedula=cedula,
            nombre="Cliente Remove Soft",
            plan="Mensual",
            dias=30,
        )

        remove_member(cedula)
        member = find_member_by_cedula(cedula)
        self.assertIsNotNone(member)
        self.assertEqual(member["estado"], "Inactivo")


if __name__ == "__main__":
    unittest.main()
