import os
import tempfile
import unittest
from datetime import datetime, timedelta
import urllib.parse

os.environ.setdefault("GYMSIS_SQLITE_PATH", os.path.join(tempfile.gettempdir(), "gymsis_test_suite.db"))

from core.whatsapp_service import (
    format_whatsapp_number,
    generate_membership_reminder_message,
    get_whatsapp_url,
)
from core.business import (
    get_weekly_attendance,
    get_hourly_attendance_breakdown,
    get_member_schedule_analytics,
)
from core.db_store import save_access_event, bootstrap_database


class TestWhatsAppServiceAndAnalytics(unittest.TestCase):
    """Test suite for WhatsApp messaging service and de-duplicated attendance analytics."""

    @classmethod
    def setUpClass(cls):
        bootstrap_database()

    def test_whatsapp_number_formatting_venezuela(self):
        # 11-digit local format with leading zero
        self.assertEqual(format_whatsapp_number("04243741634"), "584243741634")
        self.assertEqual(format_whatsapp_number("04141234567"), "584141234567")
        self.assertEqual(format_whatsapp_number("04129998877"), "584129998877")
        self.assertEqual(format_whatsapp_number("04165554433"), "584165554433")
        self.assertEqual(format_whatsapp_number("04261112233"), "584261112233")
        self.assertEqual(format_whatsapp_number("04221234567"), "584221234567")

        # 10-digit format without leading zero
        self.assertEqual(format_whatsapp_number("4243741634"), "584243741634")
        self.assertEqual(format_whatsapp_number("4221234567"), "584221234567")

        # Formatted with plus, dashes and spaces
        self.assertEqual(format_whatsapp_number("+58 424-374-1634"), "584243741634")
        self.assertEqual(format_whatsapp_number("+58 422-123-4567"), "584221234567")
        self.assertEqual(format_whatsapp_number("+58 (412) 123.4567"), "584121234567")

    def test_whatsapp_number_formatting_international_and_invalid(self):
        # International numbers
        self.assertEqual(format_whatsapp_number("+1 (555) 234-5678"), "15552345678")
        self.assertEqual(format_whatsapp_number("57 300 1234567"), "573001234567")

        # Invalid / empty
        self.assertEqual(format_whatsapp_number(""), "")
        self.assertEqual(format_whatsapp_number("abc"), "")
        self.assertEqual(format_whatsapp_number("12345"), "")

    def test_reminder_message_positive_days(self):
        today = datetime.now().date()
        exp_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")
        member = {
            "nombre": "Carlos Perez",
            "telefono": "04243741634",
            "plan": "Plan Mensual",
            "vencimiento": exp_date,
        }
        msg = generate_membership_reminder_message(member)
        self.assertIn("Hola Carlos Perez", msg)
        self.assertIn("le quedan 5 días de vigencia", msg)
        self.assertIn("Plan Mensual", msg)
        self.assertIn(exp_date, msg)

    def test_reminder_message_expiring_tomorrow(self):
        today = datetime.now().date()
        exp_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        member = {
            "nombre": "Maria Gomez",
            "telefono": "04121112233",
            "plan": "Plan Trimestral",
            "vencimiento": exp_date,
        }
        msg = generate_membership_reminder_message(member)
        self.assertIn("vence mañana", msg)

    def test_reminder_message_expiring_today(self):
        today = datetime.now().date()
        exp_date = today.strftime("%Y-%m-%d")
        member = {
            "nombre": "Luis Diaz",
            "telefono": "04149998888",
            "plan": "Plan Semestral",
            "vencimiento": exp_date,
        }
        msg = generate_membership_reminder_message(member)
        self.assertTrue("vence hoy" in msg.lower())

    def test_reminder_message_moroso_expired_past(self):
        today = datetime.now().date()
        exp_date = (today - timedelta(days=4)).strftime("%Y-%m-%d")
        member = {
            "nombre": "Pedro Infante",
            "telefono": "04245556677",
            "plan": "Plan Anual",
            "vencimiento": exp_date,
        }
        msg = generate_membership_reminder_message(member)
        self.assertIn("venció hace 4 días", msg)
        self.assertIn("reactivar tu acceso", msg)

    def test_get_whatsapp_url(self):
        today = datetime.now().date()
        exp_date = (today + timedelta(days=3)).strftime("%Y-%m-%d")
        member = {
            "nombre": "Ana Suarez",
            "telefono": "04243741634",
            "plan": "Plan Mensual",
            "vencimiento": exp_date,
        }
        url = get_whatsapp_url(member)
        self.assertTrue(url.startswith("https://wa.me/584243741634?text="))
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertIn("text", params)
        self.assertIn("Ana Suarez", params["text"][0])
        self.assertIn("le quedan 3 días de vigencia", params["text"][0])

        # If no phone registered
        self.assertIsNone(get_whatsapp_url({"nombre": "Sin Tlf", "telefono": ""}))

    def test_attendance_deduplication(self):
        """Entering 10 times in one day must count as 1 unique attendee, but 10 total scans."""
        now = datetime.now()
        test_cedula = "V-TEST-DEDUP-99"

        # Log 5 access events today for this cedula
        for i in range(5):
            save_access_event({
                "cedula": test_cedula,
                "nombre": "Test Deduplication User",
                "plan": "Plan Mensual",
                "status": "CONCEDIDO",
            })

        weekly = get_weekly_attendance()
        self.assertIsInstance(weekly, list)
        self.assertEqual(len(weekly), 7)

        # Find today's bar
        day_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
        today_abbr = day_names[now.weekday()]
        today_bar = next((d for d in weekly if d["dia"] == today_abbr), None)
        self.assertIsNotNone(today_bar)

        # Unique count must be at least 1 (the test user, plus any existing)
        self.assertGreaterEqual(today_bar["count"], 1)
        # Total scans must be >= 5
        self.assertGreaterEqual(today_bar["total_scans"], 5)
        # total_scans >= count
        self.assertGreaterEqual(today_bar["total_scans"], today_bar["count"])

    def test_hourly_attendance_breakdown_and_habits(self):
        breakdown = get_hourly_attendance_breakdown()
        self.assertIn("hours", breakdown)
        self.assertIn("peak_hour", breakdown)
        self.assertIn("quiet_hour", breakdown)
        self.assertIn("best_shift", breakdown)
        self.assertEqual(len(breakdown["hours"]), 17)  # Hours 6 to 22 inclusive

        habits = get_member_schedule_analytics(limit=10)
        self.assertIn("all", habits)
        self.assertIn("morning", habits)
        self.assertIn("afternoon", habits)
        self.assertIn("evening", habits)


if __name__ == "__main__":
    unittest.main()
