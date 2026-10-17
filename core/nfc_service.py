"""NFC Reader Service for Advanced Card Systems (ACS) ACR122U.

Communicates directly via CCID over PyUSB on Linux without requiring pcscd
or root permissions. Handles tag polling, UID extraction, LED and buzzer control,
and thread-safe dispatching for Access Control and Member Enrollment.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import usb.core
import usb.util

logger = logging.getLogger("GymsisNFC")

VENDOR_ID = 0x072F
PRODUCT_ID = 0x2200

# ACS ACR122U Bi-color LED and Buzzer Control Pseudo-APDU commands:
# [0xFF, 0x00, 0x40, [P2: LED State], 0x04, [T1 Duration], [T2 Duration], [Number of Repetitions], [Buzzer Output]]
# Green light on, 1 short beep (Access Granted)
APDU_BEEP_SUCCESS = bytes([0xFF, 0x00, 0x40, 0x50, 0x04, 0x01, 0x00, 0x01, 0x01])
# Red light on, 2 beeps (Access Denied / Invalid)
APDU_BEEP_DENIED = bytes([0xFF, 0x00, 0x40, 0x50, 0x04, 0x02, 0x00, 0x02, 0x02])
# Quick yellow/orange confirmation beep (Tag Linked/Enrollment)
APDU_BEEP_ENROLL = bytes([0xFF, 0x00, 0x40, 0x90, 0x04, 0x01, 0x00, 0x01, 0x01])

# ISO 7816-4 APDU command to retrieve the unique serial number (UID) from contactless cards:
APDU_GET_UID = bytes([0xFF, 0xCA, 0x00, 0x00, 0x00])


class NfcService:
    """Background service managing the ACS ACR122U NFC reader."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._device = None
        self._seq = 0
        self._lock = threading.Lock()

        # Listeners
        self.access_callback: Optional[Callable[[str], None]] = None
        self.enroll_callback: Optional[Callable[[str], None]] = None
        self.status_callback: Optional[Callable[[bool, str], None]] = None

        self.mode = "access"  # "access" or "enroll"
        self._last_uid = ""
        self._last_uid_time = 0.0
        self._cooldown_seconds = 2.5
        self.is_connected = False

    def start(self):
        """Start the background NFC scanner thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="GymsisNFCScanner",
        )
        self._thread.start()
        logger.info("[NFC] Servicio iniciado en segundo plano.")

    def stop(self):
        """Stop the background reader thread and release USB device."""
        self._running = False
        if self._device:
            try:
                usb.util.dispose_resources(self._device)
            except Exception:
                pass
            self._device = None
        self.is_connected = False

    def set_enroll_mode(self, callback: Callable[[str], None]):
        """Put reader in Enrollment mode: the next card scanned triggers callback and reverts to access mode."""
        with self._lock:
            self.mode = "enroll"
            self.enroll_callback = callback
            self._last_uid = ""  # reset debouncing

    def set_access_mode(self):
        """Return reader to normal access control mode."""
        with self._lock:
            self.mode = "access"
            self.enroll_callback = None

    def _init_device(self) -> bool:
        """Find ACR122U USB device, detach Linux kernel driver if active, and set configuration."""
        try:
            dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
            if not dev:
                if self.is_connected:
                    self.is_connected = False
                    self._notify_status(False, "Lector NFC desconectado")
                return False

            if dev.is_kernel_driver_active(0):
                try:
                    dev.detach_kernel_driver(0)
                except Exception as ex:
                    logger.warning(f"[NFC] No se pudo desasociar driver del kernel: {ex}")

            dev.set_configuration()
            self._device = dev
            self._seq = 1

            if not self.is_connected:
                self.is_connected = True
                self._notify_status(True, "ACR122U conectado y listo")
                logger.info("[NFC] Lector ACS ACR122U detectado y configurado correctamente.")
            return True
        except Exception as e:
            self.is_connected = False
            self._device = None
            return False

    def _send_ccid_xfr(self, apdu: bytes, timeout_ms: int = 1000) -> Optional[bytes]:
        """Send CCID PC_to_RDR_XfrBlock command to the reader."""
        if not self._device:
            return None

        with self._lock:
            try:
                self._seq = (self._seq + 1) % 255
                # CCID header: msg_type (0x6F), len (4 bytes), slot (0), seq, RFU 3 bytes
                header = bytes([0x6F, len(apdu), 0x00, 0x00, 0x00, 0x00, self._seq, 0x00, 0x00, 0x00])
                self._device.write(0x02, header + apdu)
                resp = self._device.read(0x82, 64, timeout=timeout_ms)
                return bytes(resp)
            except Exception:
                return None

    def beep_success(self):
        """Emit 1 short high beep and flash green LED."""
        self._send_ccid_xfr(APDU_BEEP_SUCCESS, timeout_ms=500)

    def beep_denied(self):
        """Emit 2 short beeps and flash red LED."""
        self._send_ccid_xfr(APDU_BEEP_DENIED, timeout_ms=1000)

    def beep_enroll(self):
        """Emit confirmation beep when a tag is linked."""
        self._send_ccid_xfr(APDU_BEEP_ENROLL, timeout_ms=500)

    def _notify_status(self, connected: bool, message: str):
        if self.status_callback:
            try:
                self.status_callback(connected, message)
            except Exception as e:
                logger.error(f"[NFC] Error en status callback: {e}")

    def _run_loop(self):
        """Main polling thread."""
        while self._running:
            if not self._device:
                if not self._init_device():
                    time.sleep(1.0)
                    continue

            # Poll for contactless card presence by attempting ICC Power On (CCID 0x62)
            try:
                with self._lock:
                    self._seq = (self._seq + 1) % 255
                    power_on_cmd = bytes([0x62, 0x00, 0x00, 0x00, 0x00, 0x00, self._seq, 0x00, 0x00, 0x00])
                    self._device.write(0x02, power_on_cmd)
                    resp = self._device.read(0x82, 64, timeout=120)

                # Card responded with ATR!
                if resp and len(resp) >= 10 and resp[0] == 0x80:
                    self._handle_card_present()

            except usb.core.USBTimeoutError:
                # No card on reader antenna, normal polling idle
                pass
            except usb.core.USBError as ue:
                logger.warning(f"[NFC] Error USB: {ue}. Intentando reconectar...")
                self._device = None
                self.is_connected = False
                time.sleep(1.0)
            except Exception as e:
                time.sleep(0.2)

            time.sleep(0.08)

    def _handle_card_present(self):
        """Read UID from the detected card and route to current mode."""
        resp = self._send_ccid_xfr(APDU_GET_UID, timeout_ms=500)
        if not resp or len(resp) < 10:
            return

        data_len = resp[1] | (resp[2] << 8)
        data = resp[10 : 10 + data_len]

        # Valid response ends with status word 0x90 0x00
        if len(data) >= 2 and data[-2:] == b"\x90\x00":
            raw_uid = data[:-2]
            uid_hex = raw_uid.hex().upper()
            uid_formatted = ":".join(f"{b:02X}" for b in raw_uid)

            now = time.time()
            # Debounce: avoid duplicate reads if tag remains on reader
            if uid_hex == self._last_uid and (now - self._last_uid_time) < self._cooldown_seconds:
                return

            self._last_uid = uid_hex
            self._last_uid_time = now

            logger.info(f"[NFC] Tarjeta leída: {uid_formatted}")

            # Route based on current mode
            if self.mode == "enroll" and self.enroll_callback:
                callback = self.enroll_callback
                self.set_access_mode()
                self.beep_enroll()
                try:
                    callback(uid_hex)
                except Exception as e:
                    logger.error(f"[NFC] Error en callback de registro: {e}")
            elif self.access_callback:
                try:
                    self.access_callback(uid_hex)
                except Exception as e:
                    logger.error(f"[NFC] Error en callback de acceso: {e}")


# Global singleton instance
nfc_reader = NfcService()
