"""End-to-end integration tests for Gymsis real-time event bus,
BCV bimonetary exchange rate, membership payments, and NFC attendance.
"""

import os
import tempfile
import unittest
from datetime import datetime, date

os.environ.setdefault("GYMSIS_SQLITE_PATH", os.path.join(tempfile.gettempdir(), "gymsis_test_suite.db"))

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

        # Test live multi-source fetch
        ok, live_rate, msg = bcv_service.fetch_official_rate()
        if ok:
            self.assertGreater(live_rate, 500.0)  # Real BCV rate is > 800 Bs
            self.assertIn("BCV", bcv_service.get_source())
        else:
            # If external network timed out or is offline in local env, service maintains safe fallback
            self.assertGreater(bcv_service.get_rate(), 0.0)


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

    def test_07_user_repository_and_auth(self):
        """Verify Sistema users, password hashing, and role permissions."""
        from core.repositories import UserRepository

        admin = UserRepository.authenticate("admin", "admin123")
        self.assertIsNotNone(admin)
        self.assertEqual(admin["username"], "admin")
        self.assertEqual(admin["role"], "admin")

        gerente = UserRepository.authenticate("gerente", "gerente123")
        self.assertIsNotNone(gerente)
        self.assertEqual(gerente["username"], "gerente")

        wrong = UserRepository.authenticate("admin", "wrong_password")
        self.assertIsNone(wrong)

        perms = UserRepository.permissions("admin")
        self.assertIn("manage_users", perms)
        self.assertIn("view_settings", perms)

        users = UserRepository.list_users()
        self.assertGreaterEqual(len(users), 2)

    def test_08_audit_logs_and_traceability(self):
        """Verify audit log creation, retrieval, and action filtering."""
        from core.business import log_action, set_active_user, get_active_user
        from core.repositories import AuditLogRepository

        set_active_user("test_auditor")
        self.assertEqual(get_active_user(), "test_auditor")

        logged = log_action("TEST_ACTION_AUDIT", {"module": "tests", "status": "ok"})
        self.assertTrue(logged)

        logs = AuditLogRepository.list_logs(limit=20, action_filter="TEST_ACTION_AUDIT")
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["username"], "test_auditor")
        self.assertEqual(logs[0]["action"], "TEST_ACTION_AUDIT")

        set_active_user("sistema")

    def test_09_pos_products_repository(self):
        """Verify POS products CRUD, active status toggling, and stock decrement."""
        from core.repositories import POSProductRepository

        ok, msg = POSProductRepository.save_product("Bebida Energetica Test", 3.50, 25, is_active=True)
        self.assertTrue(ok)

        products = POSProductRepository.list_products(active_only=False)
        target = next((p for p in products if p["nombre"] == "Bebida Energetica Test"), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["precio"], 3.50)
        self.assertEqual(target["stock"], 25)

        # Decrement stock
        POSProductRepository.decrement_stock("Bebida Energetica Test", 2)
        target_after = next((p for p in POSProductRepository.list_products() if p["nombre"] == "Bebida Energetica Test"), None)
        self.assertEqual(target_after["stock"], 23)

        # Deactivate
        POSProductRepository.set_product_active("Bebida Energetica Test", False)
        active_products = POSProductRepository.list_products(active_only=True)
        self.assertNotIn("Bebida Energetica Test", [p["nombre"] for p in active_products])

    def test_10_cash_closure_and_reports_export(self):
        """Verify financial cash closure, multi-sheet Excel generation, and retention export."""
        from core.cash_closure import perform_cash_closure
        from core.reports_export import export_inactive_members_excel

        closure = perform_cash_closure(trigger="test_suite")
        self.assertTrue(os.path.exists(closure["xlsx_path"]))
        self.assertTrue(os.path.exists(closure["txt_path"]))
        self.assertIn("reports", closure["relative_folder"])

        # Inactive members retention Excel export
        retention_path = export_inactive_members_excel(min_days=15)
        self.assertTrue(os.path.exists(retention_path))
        self.assertTrue(retention_path.endswith(".xlsx"))

    def test_11_view_instantiations(self):
        """Verify restored views instantiate without exceptions."""
        from ui.views.products_view import ProductsView
        from ui.views.reports_view import ReportsView
        from ui.views.audit_logs_view import AuditLogsView

        pv = ProductsView()
        self.assertIsNotNone(pv)

        rv = ReportsView()
        self.assertIsNotNone(rv)

        alv = AuditLogsView()
        self.assertIsNotNone(alv)

    def test_12_pbkdf2_and_security_hardening(self):
        """Verify PBKDF2 password hashing, legacy upgrade, and path traversal protection."""
        from core.local_db import _hash_password, _verify_password, create_user, authenticate_user
        from core.db_store import import_backup_json

        # 1. PBKDF2 hash format
        hashed = _hash_password("SuperSecretPass123")
        self.assertTrue(hashed.startswith("pbkdf2:sha256:100000$"))
        self.assertTrue(_verify_password("SuperSecretPass123", hashed))
        self.assertFalse(_verify_password("WrongPassword", hashed))

        # 2. Path traversal protection on backup import
        with self.assertRaises((PermissionError, FileNotFoundError, ValueError)):
            import_backup_json("../../../etc/passwd")

        with self.assertRaises((PermissionError, FileNotFoundError, ValueError)):
            import_backup_json("/etc/shadow")

    def test_13_rbac_and_role_permissions(self):
        """Verify role permissions and RBAC view structure."""
        from core.repositories import UserRepository
        from app import _ALL_VIEWS_CONFIG

        admin_perms = UserRepository.permissions("admin")
        self.assertIn("view_settings", admin_perms)
        self.assertIn("view_audit", admin_perms)
        self.assertIn("view_reports", admin_perms)

        # Staff permissions
        from core.local_db import LOCAL_ROLE_PERMISSIONS
        staff_perms = LOCAL_ROLE_PERMISSIONS["staff"]
        self.assertIn("view_pos", staff_perms)
        self.assertIn("view_members", staff_perms)
        self.assertNotIn("view_settings", staff_perms)
        self.assertNotIn("view_audit", staff_perms)

        # Viewer permissions
        viewer_perms = LOCAL_ROLE_PERMISSIONS["viewer"]
        self.assertIn("view_dashboard", viewer_perms)
        self.assertNotIn("view_pos", viewer_perms)
        self.assertNotIn("manage_users", viewer_perms)

        # All views config has permission tags
        for view_cfg in _ALL_VIEWS_CONFIG:
            self.assertIn("permission", view_cfg)
            self.assertIn("view", view_cfg)

    def test_14_nfc_anti_bounce_and_reader_robustness(self):
        """Verify NFC anti-bounce prevents instant entrance/exit state inversion on double tap."""
        from core.nfc_service import nfc_reader
        cedula = "V-99887766"
        nfc_id = "04AABBCCDD"

        register_member(
            cedula=cedula,
            nombre="Carlos DoubleTap",
            plan="Basico",
            nfc_id=nfc_id,
        )

        member = find_member_by_cedula(cedula)
        member["entrenando"] = False

        # 1. First scan with 3s min_interval -> ENTRADA
        scan1 = process_nfc_scan(nfc_id, min_interval=3.0)
        self.assertEqual(scan1["action"], "ENTRADA")
        self.assertTrue(member.get("entrenando"))

        # 2. Immediate second scan (simulating holding card or RF bounce) -> Cooldown ignored, still in gym!
        scan2 = process_nfc_scan(nfc_id, min_interval=3.0)
        self.assertTrue(scan2.get("cooldown"))
        self.assertTrue(member.get("entrenando"), "Member must remain checked-in, not bounced out!")

        # 3. Test NFC reader mode toggling
        def mock_enroll(uid):
            pass

        nfc_reader.set_enroll_mode(mock_enroll)
        self.assertEqual(nfc_reader.mode, "enroll")
        self.assertIsNotNone(nfc_reader.enroll_callback)

        nfc_reader.set_access_mode()
        self.assertEqual(nfc_reader.mode, "access")
        self.assertIsNone(nfc_reader.enroll_callback)

    def test_15_dashboard_metrics_and_metric_cards(self):
        """Verify MetricCard updates its inner Text control and weekly attendance chart works."""
        from ui.components.widgets import MetricCard, BarChartSim
        import flet as ft

        # 1. MetricCard value property test
        card = MetricCard(icon=ft.Icons.PEOPLE, icon_color="#38bdf8", value="0", label="Socios")
        self.assertEqual(card.value, "0")
        self.assertEqual(card.value_text.value, "0")

        card.value = "42"
        self.assertEqual(card.value, "42")
        self.assertEqual(card.value_text.value, "42", "Inner Text control must update when card.value is set!")

        # 2. BarChartSim data update test
        chart = BarChartSim()
        weekly_test_data = [
            {"dia": "Lun", "count": 12},
            {"dia": "Mar", "count": 25},
            {"dia": "Mie", "count": 8},
            {"dia": "Jue", "count": 0},
            {"dia": "Vie", "count": 15},
            {"dia": "Sab", "count": 30},
            {"dia": "Dom", "count": 5},
        ]
        chart.set_data(weekly_test_data)
        self.assertEqual(len(chart.bars_row.controls), 7)
        self.assertEqual(chart.bars_row.controls[1].controls[0].value, "25")

        # 3. get_dashboard_metrics return structure
        metrics = get_dashboard_metrics()
        self.assertIn("weekly_attendance", metrics)
        self.assertEqual(len(metrics["weekly_attendance"]), 7)
        self.assertIn("entrenando", metrics)
        self.assertIn("daily_income", metrics)

    def test_16_multi_nfc_keys_management(self):
        """Verify registering multiple NFC devices (phone, watch, fobs), lookups, overwrites, and deletion."""
        from core.mock_data import (
            register_member,
            remove_member,
            refresh_nfc_keys_cache,
            get_member_nfc_keys,
            find_member_by_nfc_id,
            register_member_nfc_key,
            update_member_nfc_key_entry,
            delete_member_nfc_key_entry,
        )
        from core.db_store import _connect_sqlite, get_active_engine, _connect_pg

        cedula = "V-77112233"
        remove_member(cedula)
        remove_member("V-88223344")

        # Clean database table for test entries
        engine = get_active_engine()
        if engine == "postgresql":
            conn = _connect_pg()
            if conn:
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM member_nfc_keys WHERE cedula IN (%s, %s);", (cedula, "V-88223344"))
                    conn.close()
                except Exception:
                    pass
        conn = _connect_sqlite()
        with conn:
            conn.execute("DELETE FROM member_nfc_keys WHERE cedula IN (?, ?)", (cedula, "V-88223344"))
        conn.close()
        refresh_nfc_keys_cache()

        register_member(cedula=cedula, nombre="María Dispositivos", plan="VIP", nfc_id="NFCBASE01")

        # 1. Add secondary device (iPhone NFC)
        ok, msg = register_member_nfc_key(cedula, "IPHONE15UID", alias="iPhone 15 Pro")
        self.assertTrue(ok, f"Failed adding secondary key: {msg}")

        # 2. Add tertiary device (Apple Watch)
        ok, msg = register_member_nfc_key(cedula, "WATCHSERIES9", alias="Apple Watch Ultra")
        self.assertTrue(ok, f"Failed adding tertiary key: {msg}")

        # 3. Verify get_member_nfc_keys
        keys = get_member_nfc_keys(cedula)
        uids = [k["nfc_id"] for k in keys]
        self.assertIn("IPHONE15UID", uids)
        self.assertIn("WATCHSERIES9", uids)

        # 4. Verify lookup by phone and watch resolves to María
        m_phone = find_member_by_nfc_id("IPHONE15UID")
        self.assertIsNotNone(m_phone)
        self.assertEqual(m_phone["cedula"], cedula)

        m_watch = find_member_by_nfc_id("WATCHSERIES9")
        self.assertIsNotNone(m_watch)
        self.assertEqual(m_watch["cedula"], cedula)

        # 5. Verify duplicate UID prevention across members
        register_member(cedula="V-88223344", nombre="Otro Socio", plan="Basico", nfc_id="OTRONFC01")
        ok_dup, msg_dup = register_member_nfc_key("V-88223344", "IPHONE15UID", alias="Llavero Clon")
        self.assertFalse(ok_dup, "Should disallow registering an already assigned NFC UID!")

        # 6. Verify update / overwrite alias & UID
        watch_key = next(k for k in keys if k["nfc_id"] == "WATCHSERIES9")
        ok_upd, msg_upd = update_member_nfc_key_entry(watch_key["id"], "WATCHULTRA2", "Apple Watch Ultra 2")
        self.assertTrue(ok_upd)
        self.assertIsNone(find_member_by_nfc_id("WATCHSERIES9"))
        self.assertIsNotNone(find_member_by_nfc_id("WATCHULTRA2"))

        # 7. Verify deletion
        ok_del = delete_member_nfc_key_entry(watch_key["id"])
        self.assertTrue(ok_del)
        self.assertIsNone(find_member_by_nfc_id("WATCHULTRA2"))

    def test_17_membership_urgency_color_coding(self):
        """Verify dynamic color coding and urgency badge metadata calculation."""
        from datetime import datetime, timedelta
        from core.business import compute_membership_urgency, process_nfc_scan
        from core.mock_data import register_member

        today = datetime.now().date()

        # > 12 days remaining -> green (#10B981)
        m_green = {
            "nombre": "Pedro Verde",
            "plan": "VIP",
            "vencimiento": (today + timedelta(days=20)).strftime("%Y-%m-%d"),
        }
        urg_green = compute_membership_urgency(m_green)
        self.assertEqual(urg_green["color"], "green")
        self.assertEqual(urg_green["hex"], "#10B981")
        self.assertEqual(urg_green["days_remaining"], 20)

        # 3 to 12 days remaining -> yellow (#F59E0B)
        m_yellow = {
            "nombre": "Ana Amarillo",
            "plan": "Basico",
            "vencimiento": (today + timedelta(days=5)).strftime("%Y-%m-%d"),
        }
        urg_yellow = compute_membership_urgency(m_yellow)
        self.assertEqual(urg_yellow["color"], "yellow")
        self.assertEqual(urg_yellow["hex"], "#F59E0B")
        self.assertEqual(urg_yellow["days_remaining"], 5)

        # < 3 days remaining -> red (#EF4444)
        m_red = {
            "nombre": "Juan Rojo",
            "plan": "Trimestral",
            "vencimiento": (today + timedelta(days=2)).strftime("%Y-%m-%d"),
        }
        urg_red = compute_membership_urgency(m_red)
        self.assertEqual(urg_red["color"], "red")
        self.assertEqual(urg_red["hex"], "#EF4444")
        self.assertEqual(urg_red["days_remaining"], 2)

        # Expired -> red (#EF4444)
        m_exp = {
            "nombre": "Luis Vencido",
            "plan": "Basico",
            "vencimiento": (today - timedelta(days=3)).strftime("%Y-%m-%d"),
        }
        urg_exp = compute_membership_urgency(m_exp)
        self.assertEqual(urg_exp["color"], "red")
        self.assertEqual(urg_exp["hex"], "#EF4444")

        # Test process_nfc_scan carries urgency
        from core.mock_data import remove_member
        test_cedula = "V-12998877"
        remove_member(test_cedula)
        register_member(
            cedula=test_cedula,
            nombre="Socio Urgencia",
            plan="VIP",
            nfc_id="URGNFC999",
        )
        scan = process_nfc_scan("URGNFC999")
        self.assertIn("urgency", scan)
        self.assertIn("hex", scan["urgency"])
        self.assertIn("label", scan["urgency"])


if __name__ == "__main__":
    unittest.main()



