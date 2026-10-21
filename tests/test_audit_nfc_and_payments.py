"""Tests for NFC duplicate protection, universal audit logging,
POS product renaming, and financial report exports.
"""

import os
import tempfile
import unittest
from datetime import datetime, date

os.environ.setdefault("GYMSIS_SQLITE_PATH", os.path.join(tempfile.gettempdir(), "gymsis_test_suite.db"))

from core.db_store import (
    bootstrap_database,
    load_audit_logs,
    load_membership_payments,
    load_sales,
    add_member_nfc_key,
    update_member_nfc_key,
)
from core.mock_data import (
    MEMBERS,
    register_member,
    update_member,
    rename_and_update_product,
    register_member_nfc_key,
)
from core.business import (
    process_membership_payment,
    register_sale_rows,
)
from core.repositories import (
    MemberRepository,
    POSProductRepository,
    SalesRepository,
    AuditLogRepository,
    PaymentRepository,
)
from core.reports_export import save_daily_report_files


class TestAuditNfcAndPayments(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        bootstrap_database()

    def test_01_nfc_duplicate_prevention_on_registration(self):
        """Registering a new member with an NFC key already assigned to another member must fail."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula_owner = f"V-NFC1-{ts}"
        nfc_shared = f"TAG1{ts}"

        # Register owner
        register_member(
            cedula=cedula_owner,
            nombre="Carlos NFC Duplicado",
            telefono="04141234567",
            plan="VIP",
            nfc_id=nfc_shared,
            dias=30,
        )

        # Attempt to register second member with same NFC
        with self.assertRaises(ValueError) as ctx:
            register_member(
                cedula=f"V-NFC2-{ts}",
                nombre="Persona Invalida",
                telefono="04147654321",
                plan="Basico",
                nfc_id=nfc_shared,
            )

        err_msg = str(ctx.exception)
        self.assertIn("ya pertenece a Carlos NFC Duplicado", err_msg)
        self.assertIn(cedula_owner, err_msg)

    def test_02_nfc_duplicate_prevention_on_update(self):
        """Updating a member's NFC key to another existing member's NFC must fail with informative error."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula_a = f"V-UPA-{ts}"
        cedula_b = f"V-UPB-{ts}"
        nfc_a = f"NFA{ts}"
        nfc_b = f"NFB{ts}"

        register_member(
            cedula=cedula_a,
            nombre="Miembro A",
            telefono="04120000001",
            plan="Basico",
            nfc_id=nfc_a,
        )
        register_member(
            cedula=cedula_b,
            nombre="Miembro B",
            telefono="04120000002",
            plan="Basico",
            nfc_id=nfc_b,
        )

        # Updating member A to use member B's NFC
        with self.assertRaises(ValueError) as ctx:
            update_member(
                cedula=cedula_a,
                nombre="Miembro A Modificado",
                telefono="04120000001",
                plan="Basico",
                nfc_id=nfc_b,
            )

        self.assertIn("ya pertenece a Miembro B", str(ctx.exception))

        # Updating member A to keep own NFC must succeed
        updated = update_member(
            cedula=cedula_a,
            nombre="Miembro A Modificado",
            telefono="04120000001",
            plan="Basico",
            nfc_id=nfc_a,
        )
        self.assertIsNotNone(updated)

    def test_03_db_store_nfc_keys_duplicate_prevention(self):
        """add_member_nfc_key must reject duplicate key assignments across different members."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula_owner = f"V-OWNER-{ts}"
        cedula_other = f"V-OTHER-{ts}"
        key_uid = f"UIDKEY{ts}"

        register_member(
            cedula=cedula_owner,
            nombre="Dueno De Llave",
            telefono="04149999999",
            plan="VIP",
        )
        register_member(
            cedula=cedula_other,
            nombre="Otro Miembro",
            telefono="04148888888",
            plan="VIP",
        )

        # Add key to owner
        ok, msg = add_member_nfc_key(cedula_owner, key_uid, "Tarjeta Principal")
        self.assertTrue(ok, f"Failed adding key to owner: {msg}")

        # Attempt to add same key to other member
        ok2, msg2 = add_member_nfc_key(cedula_other, key_uid, "Copia Ilegal")
        self.assertFalse(ok2)
        self.assertIn("ya pertenece a Dueno De Llave", msg2)

    def test_04_pos_product_rename_and_persistence(self):
        """Renaming a product in POS should update the record correctly and maintain catalog integrity."""
        ts = int(datetime.now().timestamp() * 1000)
        old_name = f"Producto Antiguo {ts}"
        new_name = f"Producto Nuevo {ts}"

        # Create original product
        ok, _ = POSProductRepository.save_product(nombre=old_name, precio=5.0, stock=20, is_active=True)
        self.assertTrue(ok)

        # Rename product
        ok, _ = POSProductRepository.save_product(nombre=new_name, precio=7.5, stock=15, is_active=True, old_name=old_name)
        self.assertTrue(ok)

        # Verify old name is gone and new name is present
        products = POSProductRepository.list_products()
        names = [p["nombre"] for p in products]
        self.assertIn(new_name, names)
        self.assertNotIn(old_name, names)

        # Check price and stock
        renamed_p = next(p for p in products if p["nombre"] == new_name)
        self.assertEqual(renamed_p["precio"], 7.5)
        self.assertEqual(renamed_p["stock"], 15)

    def test_05_universal_audit_logging(self):
        """All critical mutations must produce clear, structured audit logs."""
        ts = int(datetime.now().timestamp() * 1000)
        cedula = f"V-AUDIT-{ts}"

        # 1. Member registration with initial payment
        register_member(
            cedula=cedula,
            nombre="Usuario Con Auditoria",
            telefono="04161112233",
            plan="VIP",
            dias=30,
            initial_payment={"monto_usd": 35.0, "metodo": "pago_movil", "referencia": "REF-AUDIT-01"},
        )

        logs = AuditLogRepository.list_logs(limit=50)
        actions = [l.get("action") for l in logs]
        self.assertIn("REGISTRO_SOCIO", actions)

        # 2. Member update
        update_member(cedula=cedula, nombre="Usuario Auditado Modificado", telefono="04161112233", plan="VIP")
        logs = AuditLogRepository.list_logs(limit=50)
        actions = [l.get("action") for l in logs]
        self.assertIn("EDICION_SOCIO", actions)

        # 3. NFC key assignment
        register_member_nfc_key(cedula=cedula, nfc_uid=f"NFCTAG{ts}", label="Llavero Casa")
        logs = AuditLogRepository.list_logs(limit=50)
        actions = [l.get("action") for l in logs]
        self.assertIn("VINCULAR_LLAVE_NFC", actions)

        # 4. POS Sale
        sale_items = [{"nombre": "Agua 500ml", "qty": 2, "subtotal": 3.0}]
        register_sale_rows(sale_items)
        logs = AuditLogRepository.list_logs(limit=50)
        actions = [l.get("action") for l in logs]
        self.assertIn("VENTA_POS", actions)

        # 5. Membership Payment
        process_membership_payment(
            cedula=cedula,
            plan="VIP",
            monto=35.0,
            dias=30,
            metodo="pago_movil",
            referencia="REF-AUDIT-999",
        )
        logs = AuditLogRepository.list_logs(limit=50)
        actions = [l.get("action") for l in logs]
        self.assertIn("PAGO_MEMBRESIA", actions)

        # 5. Membership Payment
        process_membership_payment(
            cedula=cedula,
            plan="VIP",
            monto=35.0,
            dias=30,
            metodo="pago_movil",
            referencia="REF-AUDIT-999",
        )
        logs = AuditLogRepository.list_logs(limit=50)
        actions = [l.get("action") for l in logs]
        self.assertIn("PAGO_MEMBRESIA", actions)

    def test_06_reports_export_generation(self):
        """save_daily_report_files must query data and export both TXT and Excel files without error."""
        today = date.today()
        bcv_rate = 50.0

        txt_path, xlsx_path = save_daily_report_files(target_date=today, bcv_rate=bcv_rate)

        self.assertTrue(os.path.exists(txt_path), f"TXT report not found at {txt_path}")
        self.assertTrue(os.path.exists(xlsx_path), f"Excel report not found at {xlsx_path}")

        # Check content in text report
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("CIERRE DE CAJA", content)
            self.assertIn("INGRESOS POR MEMBRESÍAS", content)
            self.assertIn("VENTAS POS (CANTINA)", content)
            self.assertIn("TOTAL GENERAL USD", content)


if __name__ == "__main__":
    unittest.main()
