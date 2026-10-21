"""NFC Reader Service for Advanced Card Systems (ACS) ACR122U.

Supports two native backends:
1. Windows Native PC/SC SmartCard (via winscard.dll): Zero external drivers needed on Windows,
   communicates natively with the official Windows ACR122U CCID driver.
2. Linux / Cross-platform USB CCID (via PyUSB): Direct USB communication without pcscd.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from typing import Callable, Optional

try:
    import usb.core
    import usb.util
    USB_AVAILABLE = True
    USBError = usb.core.USBError
    USBTimeoutError = usb.core.USBTimeoutError
except (ImportError, Exception):
    usb = None
    USB_AVAILABLE = False
    class USBError(Exception): pass
    class USBTimeoutError(Exception): pass

logger = logging.getLogger("GymsisNFC")

VENDOR_ID = 0x072F
PRODUCT_ID = 0x2200

# ACS ACR122U Bi-color LED and Buzzer Control Pseudo-APDU commands:
APDU_BEEP_SUCCESS = bytes([0xFF, 0x00, 0x40, 0x50, 0x04, 0x01, 0x00, 0x01, 0x01])
APDU_BEEP_DENIED = bytes([0xFF, 0x00, 0x40, 0x50, 0x04, 0x02, 0x00, 0x02, 0x02])
APDU_BEEP_ENROLL = bytes([0xFF, 0x00, 0x40, 0x90, 0x04, 0x01, 0x00, 0x01, 0x01])
APDU_BEEP_EXIT = bytes([0xFF, 0x00, 0x40, 0x50, 0x04, 0x01, 0x01, 0x01, 0x01])

# ISO 7816-4 APDU command to retrieve the unique serial number (UID):
APDU_GET_UID = bytes([0xFF, 0xCA, 0x00, 0x00, 0x00])


SCARDCONTEXT = ctypes.c_size_t
SCARDHANDLE = ctypes.c_size_t
DWORD = ctypes.c_uint32
LONG = ctypes.c_long

SCARD_SCOPE_USER = 0
SCARD_SCOPE_TERMINAL = 1
SCARD_SCOPE_SYSTEM = 2

SCARD_SHARE_EXCLUSIVE = 1
SCARD_SHARE_SHARED = 2
SCARD_SHARE_DIRECT = 3

SCARD_PROTOCOL_T0 = 1
SCARD_PROTOCOL_T1 = 2
SCARD_PROTOCOL_TX = SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1

SCARD_LEAVE_CARD = 0
SCARD_RESET_CARD = 1
SCARD_UNPOWER_CARD = 2

SCARD_STATE_UNAWARE = 0x00000000
SCARD_STATE_EMPTY = 0x00000010
SCARD_STATE_PRESENT = 0x00000020


class SCARD_IO_REQUEST(ctypes.Structure):
    _fields_ = [
        ("dwProtocol", DWORD),
        ("cbPciLength", DWORD),
    ]


class SCARD_READERSTATEA(ctypes.Structure):
    _fields_ = [
        ("szReader", ctypes.c_char_p),
        ("pvUserData", ctypes.c_void_p),
        ("dwCurrentState", DWORD),
        ("dwEventState", DWORD),
        ("cbAtr", DWORD),
        ("rgbAtr", ctypes.c_ubyte * 36),
    ]


class WinSCardDriver:
    """Windows Native PC/SC SmartCard driver for ACS ACR122U and compatible readers."""

    def __init__(self):
        self._hContext = SCARDCONTEXT(0)
        self._winscard = None
        self.reader_name: Optional[str] = None
        self._reader_name_bytes: Optional[bytes] = None
        self.is_connected = False
        self._reader_state = SCARD_READERSTATEA()
        if sys.platform == "win32":
            try:
                self._winscard = ctypes.windll.winscard
                self._init_function_prototypes()
            except Exception as e:
                logger.error(f"[NFC] Error al cargar winscard.dll: {e}")
                self._winscard = None

    def _init_function_prototypes(self):
        if not self._winscard:
            return
        try:
            self._winscard.SCardEstablishContext.argtypes = [
                DWORD,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(SCARDCONTEXT),
            ]
            self._winscard.SCardEstablishContext.restype = LONG

            self._winscard.SCardReleaseContext.argtypes = [SCARDCONTEXT]
            self._winscard.SCardReleaseContext.restype = LONG

            self._winscard.SCardListReadersA.argtypes = [
                SCARDCONTEXT,
                ctypes.c_char_p,
                ctypes.c_char_p,
                ctypes.POINTER(DWORD),
            ]
            self._winscard.SCardListReadersA.restype = LONG

            self._winscard.SCardConnectA.argtypes = [
                SCARDCONTEXT,
                ctypes.c_char_p,
                DWORD,
                DWORD,
                ctypes.POINTER(SCARDHANDLE),
                ctypes.POINTER(DWORD),
            ]
            self._winscard.SCardConnectA.restype = LONG

            self._winscard.SCardDisconnect.argtypes = [SCARDHANDLE, DWORD]
            self._winscard.SCardDisconnect.restype = LONG

            self._winscard.SCardTransmit.argtypes = [
                SCARDHANDLE,
                ctypes.c_void_p,
                ctypes.c_char_p,
                DWORD,
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.POINTER(DWORD),
            ]
            self._winscard.SCardTransmit.restype = LONG

            self._winscard.SCardGetStatusChangeA.argtypes = [
                SCARDCONTEXT,
                DWORD,
                ctypes.POINTER(SCARD_READERSTATEA),
                DWORD,
            ]
            self._winscard.SCardGetStatusChangeA.restype = LONG
        except Exception as e:
            logger.error(f"[NFC] Error configurando prototipos winscard: {e}")

    def is_available(self) -> bool:
        return self._winscard is not None

    def connect_reader(self) -> bool:
        if not self._winscard:
            return False
        try:
            if self._hContext.value == 0:
                ret = self._winscard.SCardEstablishContext(SCARD_SCOPE_USER, None, None, ctypes.byref(self._hContext))
                if ret != 0:
                    ret = self._winscard.SCardEstablishContext(SCARD_SCOPE_SYSTEM, None, None, ctypes.byref(self._hContext))
                if ret != 0:
                    if sys.platform == "win32":
                        try:
                            import subprocess
                            subprocess.run("sc.exe start SCardSvr", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            subprocess.run("net start SCardSvr", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            ret = self._winscard.SCardEstablishContext(SCARD_SCOPE_USER, None, None, ctypes.byref(self._hContext))
                            if ret != 0:
                                ret = self._winscard.SCardEstablishContext(SCARD_SCOPE_SYSTEM, None, None, ctypes.byref(self._hContext))
                        except Exception:
                            pass
                if ret != 0:
                    self.is_connected = False
                    return False

            readers_len = DWORD(0)
            ret = self._winscard.SCardListReadersA(self._hContext, None, None, ctypes.byref(readers_len))
            if ret != 0 or readers_len.value == 0:
                # If service stopped or context invalidated, reset context
                if ret in (0x8010001E, 0x8010001D, -2146435042, -2146435043):
                    self.close()
                else:
                    self.is_connected = False
                return False

            buf = ctypes.create_string_buffer(readers_len.value)
            ret = self._winscard.SCardListReadersA(self._hContext, None, buf, ctypes.byref(readers_len))
            if ret != 0:
                self.is_connected = False
                return False

            raw = buf.raw[: readers_len.value]
            readers = [r.decode("latin1", errors="ignore") for r in raw.split(b"\x00") if r]
            if not readers:
                self.is_connected = False
                return False

            chosen = readers[0]
            for r in readers:
                if any(k in r.upper() for k in ("ACR122", "ACS", "PICC", "NFC")):
                    chosen = r
                    break

            self.reader_name = chosen
            self._reader_name_bytes = chosen.encode("latin1") + b"\x00"

            # Initialize reader state for passive monitoring
            self._reader_state = SCARD_READERSTATEA()
            self._reader_state.szReader = self._reader_name_bytes
            self._reader_state.dwCurrentState = SCARD_STATE_UNAWARE

            # Initial query (0 timeout) to initialize state
            self._winscard.SCardGetStatusChangeA(
                self._hContext,
                0,
                ctypes.byref(self._reader_state),
                1,
            )
            self._reader_state.dwCurrentState = self._reader_state.dwEventState

            self.is_connected = True
            return True
        except Exception as e:
            logger.debug(f"[NFC] Excepción en connect_reader: {e}")
            self.close()
            return False

    def poll_card(self) -> Optional[bytes]:
        """Poll for card and return UID bytes only when card is physically present."""
        if not self._winscard:
            return None
        if not self.is_connected or self._hContext.value == 0 or not self._reader_name_bytes:
            if not self.connect_reader():
                return None

        # Passively wait for state change (up to 200ms) without creating or breaking connections
        ret = self._winscard.SCardGetStatusChangeA(
            self._hContext,
            200,
            ctypes.byref(self._reader_state),
            1,
        )

        if ret != 0:
            # SCARD_E_TIMEOUT (0x8010000A / -2146435062) -> Normal timeout, no card tapped
            if ret in (0x8010000A, -2146435062) or (ret & 0xFFFFFFFF) == 0x8010000A:
                return None
            # Service died or reader unplugged
            if ret in (0x8010001E, 0x80100017, 0x8010001D, -2146435042, -2146435049, -2146435043):
                self.close()
                return None
            return None

        event_state = self._reader_state.dwEventState
        self._reader_state.dwCurrentState = event_state

        # Card is present on antenna
        if event_state & SCARD_STATE_PRESENT:
            hCard = SCARDHANDLE(0)
            active_proto = DWORD(0)
            ret_conn = self._winscard.SCardConnectA(
                self._hContext,
                self._reader_name_bytes,
                SCARD_SHARE_SHARED,
                SCARD_PROTOCOL_TX,
                ctypes.byref(hCard),
                ctypes.byref(active_proto),
            )
            if ret_conn != 0:
                return None

            try:
                io_req = SCARD_IO_REQUEST(
                    active_proto.value if active_proto.value != 0 else 1,
                    ctypes.sizeof(SCARD_IO_REQUEST),
                )
                recv_buf = ctypes.create_string_buffer(258)
                recv_len = DWORD(258)

                tx_ret = self._winscard.SCardTransmit(
                    hCard,
                    ctypes.byref(io_req),
                    APDU_GET_UID,
                    len(APDU_GET_UID),
                    None,
                    recv_buf,
                    ctypes.byref(recv_len),
                )

                if tx_ret == 0 and recv_len.value >= 2:
                    resp = bytes(recv_buf.raw[: recv_len.value])
                    if resp[-2:] == b"\x90\x00":
                        return resp[:-2]
            finally:
                self._winscard.SCardDisconnect(hCard, SCARD_LEAVE_CARD)

        return None

    def send_buzzer(self, apdu: bytes):
        """Send buzzer / LED pseudo-APDU directly to the ACR122U."""
        if not self._winscard or not self._reader_name_bytes or self._hContext.value == 0:
            return
        hCard = SCARDHANDLE(0)
        active_proto = DWORD(0)
        ret = self._winscard.SCardConnectA(
            self._hContext,
            self._reader_name_bytes,
            SCARD_SHARE_SHARED,
            SCARD_PROTOCOL_TX,
            ctypes.byref(hCard),
            ctypes.byref(active_proto),
        )
        if ret != 0:
            ret = self._winscard.SCardConnectA(
                self._hContext,
                self._reader_name_bytes,
                SCARD_SHARE_DIRECT,
                0,
                ctypes.byref(hCard),
                ctypes.byref(active_proto),
            )
        if ret == 0:
            try:
                io_req = SCARD_IO_REQUEST(
                    active_proto.value if active_proto.value != 0 else 1,
                    ctypes.sizeof(SCARD_IO_REQUEST),
                )
                recv_buf = ctypes.create_string_buffer(258)
                recv_len = DWORD(258)
                self._winscard.SCardTransmit(
                    hCard,
                    ctypes.byref(io_req),
                    apdu,
                    len(apdu),
                    None,
                    recv_buf,
                    ctypes.byref(recv_len),
                )
            except Exception:
                pass
            finally:
                self._winscard.SCardDisconnect(hCard, SCARD_LEAVE_CARD)

    def close(self):
        if self._winscard and self._hContext.value != 0:
            try:
                self._winscard.SCardReleaseContext(self._hContext)
            except Exception:
                pass
            self._hContext = SCARDCONTEXT(0)
        self.is_connected = False
        self.reader_name = None
        self._reader_name_bytes = None


class NfcService:
    """Background service managing the ACS ACR122U NFC reader on Windows and Linux."""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._device = None
        self._seq = 0
        self._lock = threading.RLock()
        self._win_driver = WinSCardDriver()

        # Listeners
        self.access_callback: Optional[Callable[[str], None]] = None
        self.enroll_callback: Optional[Callable[[str], None]] = None
        self.status_callback: Optional[Callable[[bool, str], None]] = None

        self.mode = "access"  # "access" or "enroll"
        self._last_uid = ""
        self._last_uid_time = 0.0
        self._cooldown_seconds = 3.0
        self.is_connected = False
        self._consecutive_errors = 0

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
        if self._win_driver.is_available():
            self._win_driver.close()
        self._cleanup_device()

    def _cleanup_device(self):
        with self._lock:
            self._cleanup_device_unlocked()

    def _cleanup_device_unlocked(self):
        if self._device and usb is not None:
            try:
                usb.util.release_interface(self._device, 0)
            except Exception:
                pass
            try:
                usb.util.dispose_resources(self._device)
            except Exception:
                pass
            self._device = None

        if self.is_connected:
            self.is_connected = False
            self._notify_status(False, "Lector NFC desconectado")

    def set_enroll_mode(self, callback: Callable[[str], None]):
        """Put reader in Enrollment mode: the next card scanned triggers callback and reverts to access mode."""
        with self._lock:
            self.mode = "enroll"
            self.enroll_callback = callback
            self._last_uid = ""

    def set_access_mode(self):
        """Return reader to normal access control mode."""
        with self._lock:
            self.mode = "access"
            self.enroll_callback = None

    def _init_device(self) -> bool:
        """Find ACR122U USB device via PyUSB."""
        if not USB_AVAILABLE or usb is None:
            return False
        try:
            dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
            if not dev:
                if self.is_connected:
                    self.is_connected = False
                    self._notify_status(False, "Lector NFC desconectado")
                return False

            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except Exception:
                pass

            try:
                cfg = dev.get_active_configuration()
            except Exception:
                pass

            try:
                usb.util.claim_interface(dev, 0)
            except Exception:
                pass

            self._device = dev
            self._seq = 1
            self._consecutive_errors = 0

            if not self.is_connected:
                self.is_connected = True
                self._notify_status(True, "ACR122U conectado y listo")
                logger.info("[NFC] Lector ACS ACR122U detectado y listo.")
            return True
        except Exception:
            self.is_connected = False
            self._device = None
            return False

    def _send_ccid_xfr(self, apdu: bytes, timeout_ms: int = 500) -> Optional[bytes]:
        """Send CCID PC_to_RDR_XfrBlock command to the reader."""
        if not self._device:
            return None

        with self._lock:
            if not self._device:
                return None
            try:
                try:
                    self._device.read(0x82, 64, timeout=5)
                except Exception:
                    pass

                self._seq = (self._seq + 1) % 255
                header = bytes([
                    0x6F,
                    len(apdu) & 0xFF,
                    (len(apdu) >> 8) & 0xFF,
                    0x00,
                    0x00,
                    0x00,
                    self._seq,
                    0x00,
                    0x00,
                    0x00,
                ])
                self._device.write(0x02, header + apdu, timeout=timeout_ms)
                resp = self._device.read(0x82, 64, timeout=timeout_ms)
                self._consecutive_errors = 0
                return bytes(resp)
            except USBTimeoutError:
                return None
            except USBError as ue:
                self._consecutive_errors += 1
                if self._consecutive_errors >= 2:
                    logger.warning(f"[NFC] Desconexión o error USB persistente: {ue}. Reiniciando hardware...")
                    self._cleanup_device_unlocked()
                return None
            except Exception as e:
                logger.error(f"[NFC] Error inesperado en transferencia CCID: {e}")
                return None

    def beep_success(self):
        """Emit 1 short high beep and flash green LED."""
        if self._win_driver.is_available() and self._win_driver.is_connected:
            threading.Thread(target=self._win_driver.send_buzzer, args=(APDU_BEEP_SUCCESS,), daemon=True).start()
        elif self._device:
            threading.Thread(target=self._send_ccid_xfr, args=(APDU_BEEP_SUCCESS, 300), daemon=True).start()

    def beep_exit(self):
        """Emit friendly exit tone."""
        if self._win_driver.is_available() and self._win_driver.is_connected:
            threading.Thread(target=self._win_driver.send_buzzer, args=(APDU_BEEP_EXIT,), daemon=True).start()
        elif self._device:
            threading.Thread(target=self._send_ccid_xfr, args=(APDU_BEEP_EXIT, 300), daemon=True).start()

    def beep_denied(self):
        """Emit 2 short beeps and flash red LED."""
        if self._win_driver.is_available() and self._win_driver.is_connected:
            threading.Thread(target=self._win_driver.send_buzzer, args=(APDU_BEEP_DENIED,), daemon=True).start()
        elif self._device:
            threading.Thread(target=self._send_ccid_xfr, args=(APDU_BEEP_DENIED, 500), daemon=True).start()

    def beep_enroll(self):
        """Emit confirmation beep when a tag is linked."""
        if self._win_driver.is_available() and self._win_driver.is_connected:
            threading.Thread(target=self._win_driver.send_buzzer, args=(APDU_BEEP_ENROLL,), daemon=True).start()
        elif self._device:
            threading.Thread(target=self._send_ccid_xfr, args=(APDU_BEEP_ENROLL, 300), daemon=True).start()

    def _notify_status(self, connected: bool, message: str):
        if self.status_callback:
            try:
                self.status_callback(connected, message)
            except Exception as e:
                logger.error(f"[NFC] Error en status callback: {e}")

    def _run_loop(self):
        """Main polling thread dispatcher: WinSCard on Windows, PyUSB on Linux."""
        last_state = None
        empty_cycles = 0

        while self._running:
            # 1. On Windows, use WinSCard exclusively (Native Windows Smart Card Driver)
            if sys.platform == "win32" and self._win_driver.is_available():
                if not self._win_driver.is_connected:
                    self._win_driver.connect_reader()

                if self._win_driver.is_connected:
                    if last_state is not True:
                        last_state = True
                        self.is_connected = True
                        self._notify_status(True, f"ACR122U conectado y listo ({self._win_driver.reader_name})")
                        logger.info(f"[NFC] ACR122U conectado vía Windows SmartCard: {self._win_driver.reader_name}")

                    card_uid = None
                    try:
                        card_uid = self._win_driver.poll_card()
                    except Exception as ex:
                        logger.debug(f"[NFC] Error leyendo tarjeta: {ex}")

                    if card_uid:
                        empty_cycles = 0
                        self._dispatch_tag(card_uid)
                    else:
                        empty_cycles += 1
                        if empty_cycles >= 2:
                            self._last_uid = ""

                    time.sleep(0.08)
                    continue
            # 2. PyUSB backend (Linux, or Windows if WinSCard reader not active)
            if not self._win_driver.is_connected and USB_AVAILABLE:
                if not self._device:
                    self._init_device()

                if self._device:
                    if last_state is not True:
                        last_state = True
                        self.is_connected = True
                        self._notify_status(True, "ACR122U conectado y listo")
                        logger.info("[NFC] ACR122U conectado vía PyUSB.")

                    try:
                        resp = self._send_ccid_xfr(APDU_GET_UID, timeout_ms=250)
                        if resp and len(resp) >= 12:
                            data_len = resp[1] | (resp[2] << 8)
                            data = resp[10 : 10 + data_len]
                            if len(data) >= 2 and data[-2:] == b"\x90\x00":
                                raw_uid = data[:-2]
                                if raw_uid:
                                    empty_cycles = 0
                                    self._dispatch_tag(raw_uid)
                                else:
                                    empty_cycles += 1
                                    if empty_cycles >= 2:
                                        self._last_uid = ""
                        else:
                            empty_cycles += 1
                            if empty_cycles >= 2:
                                self._last_uid = ""
                    except Exception:
                        pass
                    time.sleep(0.12)
                    continue

            # 3. Neither backend active
            if last_state is not False:
                last_state = False
                self.is_connected = False
                self._notify_status(False, "Lector NFC desconectado")

            time.sleep(1.5)

    def _dispatch_tag(self, raw_uid: bytes):
        """Handle detected card UID with cooldown debounce."""
        uid_hex = raw_uid.hex().upper()
        uid_formatted = ":".join(f"{b:02X}" for b in raw_uid)

        now = time.time()
        if uid_hex == self._last_uid and (now - self._last_uid_time) < self._cooldown_seconds:
            return

        self._last_uid = uid_hex
        self._last_uid_time = now

        logger.info(f"[NFC] Tarjeta detectada: {uid_formatted}")

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
        else:
            try:
                from core.business import process_nfc_scan
                process_nfc_scan(uid_hex, min_interval=3.0)
            except Exception as e:
                logger.error(f"[NFC] Error en scan nfc directo: {e}")


# Global singleton instance
nfc_reader = NfcService()
