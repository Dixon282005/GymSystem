"""BCV & Parallel Exchange Rate Service for Venezuelan Bolívares (VES / USD).

Provides real-time official exchange rates directly scraped from the Banco Central de
Venezuela (BCV) portal, resilient fallback to public JSON APIs (ve.dolarapi.com),
support for both Official and Parallel rates, local persistence in database settings,
offline fallback, manual override, and bimonetary formatting for POS and memberships.
Zero dirty dependencies: built strictly on Python's standard library (urllib, ssl, re, json).
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import re
import ssl
import threading
import urllib.request
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("GymsisBCV")

DEFAULT_FALLBACK_RATE = 880.00


class BCVService:
    """Manages official and parallel USD/VES exchange rates with zero dirty dependencies."""

    def __init__(self):
        self._current_rate: float = DEFAULT_FALLBACK_RATE
        self._paralelo_rate: Optional[float] = None
        self._last_updated: Optional[str] = None
        self._fecha_valor: Optional[str] = None
        self._source: str = "Inicial"
        self._lock = threading.Lock()
        self._load_from_db()

    def _load_from_db(self):
        try:
            from core.db_store import load_settings

            settings = load_settings()
            stored_rate = settings.get("bcv_rate")
            if stored_rate:
                self._current_rate = float(stored_rate)
            stored_paralelo = settings.get("paralelo_rate")
            if stored_paralelo:
                self._paralelo_rate = float(stored_paralelo)
            self._last_updated = settings.get("bcv_last_updated", "Inicial")
            self._fecha_valor = settings.get("bcv_fecha_valor", "")
            self._source = settings.get("bcv_source", "Almacenado")
        except Exception as e:
            logger.debug(f"[BCV] Could not load stored rate from DB: {e}")

    def get_rate(self) -> float:
        """Return the current official BCV exchange rate in Bs. per USD."""
        with self._lock:
            return self._current_rate

    def get_paralelo_rate(self) -> Optional[float]:
        """Return the current parallel dollar exchange rate in Bs. per USD if available."""
        with self._lock:
            return self._paralelo_rate

    def get_last_updated(self) -> str:
        """Return the timestamp of the last rate update."""
        with self._lock:
            return self._last_updated or "No sincronizado"

    def get_fecha_valor(self) -> str:
        """Return the official BCV Fecha Valor string if available."""
        with self._lock:
            return self._fecha_valor or ""

    def get_source(self) -> str:
        """Return the source of the rate (e.g. 'BCV Oficial (Web)', 'DolarApi', 'Manual')."""
        with self._lock:
            return self._source

    def set_manual_rate(self, new_rate: float) -> bool:
        """Explicitly set a manual rate override."""
        self._source = "Manual"
        return self.set_rate(new_rate)

    def set_rate(self, new_rate: float, source: Optional[str] = None, fecha_valor: str = "") -> bool:
        """Manually override or update the BCV rate and persist to database."""
        if new_rate <= 0:
            return False

        with self._lock:
            self._current_rate = round(float(new_rate), 4)
            self._last_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
            if source:
                self._source = source
            if fecha_valor:
                self._fecha_valor = fecha_valor

        try:
            from core.db_store import save_settings
            from core.event_bus import event_bus

            save_settings({
                "bcv_rate": self._current_rate,
                "paralelo_rate": self._paralelo_rate,
                "bcv_last_updated": self._last_updated,
                "bcv_fecha_valor": self._fecha_valor,
                "bcv_source": self._source,
            })
            event_bus.publish("bcv_updated", self._current_rate)
            event_bus.publish("bcv_rate_updated", {
                "rate": self._current_rate,
                "paralelo": self._paralelo_rate,
                "updated": self._last_updated,
                "fecha_valor": self._fecha_valor,
                "source": self._source,
            })
            return True
        except Exception as e:
            logger.error(f"[BCV] Error saving rate to DB: {e}")
            return False

    def _scrape_bcv_direct(self) -> Tuple[Optional[float], Optional[str]]:
        """Directly scrape official rate and Fecha Valor from bcv.org.ve with secure SSL."""
        url = "https://www.bcv.org.ve"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }

        try:
            ctx = ssl.create_default_context()
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except ssl.SSLError as ssl_err:
            logger.warning(f"[BCV] Verificación SSL con bcv.org.ve falló ({ssl_err}). Recurriendo a DolarApi.")
            return None, None
        except Exception as exc:
            logger.debug(f"[BCV] Conexión directa no disponible: {exc}")
            return None, None

        # Container id="dolar" contains the official USD exchange rate
        rate_match = re.search(r'id=[\"\']dolar[\"\'].*?<strong[^>]*>\s*([0-9.,]+)\s*</strong>', html, re.DOTALL)
        if not rate_match:
            rate_match = re.search(r'USD.*?<strong[^>]*>\s*([0-9.,]+)\s*</strong>', html, re.DOTALL)

        if not rate_match:
            return None, None

        raw_rate = rate_match.group(1).strip()
        # Robust parsing for Venezuelan and international decimal formats
        if "." in raw_rate and "," in raw_rate:
            if raw_rate.rfind(",") > raw_rate.rfind("."):
                clean_num = raw_rate.replace(".", "").replace(",", ".")
            else:
                clean_num = raw_rate.replace(",", "")
        elif "," in raw_rate:
            clean_num = raw_rate.replace(",", ".")
        else:
            clean_num = raw_rate

        try:
            rate = float(clean_num)
        except ValueError:
            return None, None

        # Extract Fecha Valor
        date_match = re.search(r'Fecha Valor:\s*<span[^>]*>\s*([^<]+)\s*</span>', html, re.DOTALL)
        fecha_valor = date_match.group(1).strip() if date_match else ""

        return rate, fecha_valor

    def _fetch_from_dolarapi(self) -> Tuple[Optional[float], Optional[float], str]:
        """Fetch official and parallel dollar rates from resilient JSON API ve.dolarapi.com."""
        url = "https://ve.dolarapi.com/v1/dolares"
        headers = {
            "User-Agent": "GymsisSystem/2.0 (Linux; x86_64)",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        oficial_rate = None
        paralelo_rate = None
        fecha = ""

        if isinstance(data, list):
            for item in data:
                fuente = str(item.get("fuente", "")).lower()
                promedio = item.get("promedio")
                if fuente == "oficial" and promedio:
                    oficial_rate = float(promedio)
                    fecha = item.get("fechaActualizacion", "")
                elif fuente == "paralelo" and promedio:
                    paralelo_rate = float(promedio)
        elif isinstance(data, dict):
            if "promedio" in data:
                oficial_rate = float(data["promedio"])

        return oficial_rate, paralelo_rate, fecha

    def fetch_official_rate(self) -> Tuple[bool, float, str]:
        """Fetch the latest official BCV dollar rate using multi-tier resilient fallback."""
        # Tier 1: Scrape directly from official BCV website
        try:
            rate, fecha_valor = self._scrape_bcv_direct()
            if rate and rate > 0:
                self.set_rate(rate, source="BCV Oficial (Web Directa)", fecha_valor=fecha_valor or "")
                msg = f"Tasa BCV oficial obtenida: Bs. {rate:,.2f}"
                if fecha_valor:
                    msg += f" (Fecha Valor: {fecha_valor})"
                logger.info(f"[BCV] {msg}")
                return True, rate, msg
        except Exception as e:
            logger.warning(f"[BCV] Scrape directo falló ({e}), intentando API de respaldo...")

        # Tier 2: Fetch from ve.dolarapi.com (returns both official and parallel)
        try:
            oficial, paralelo, fecha = self._fetch_from_dolarapi()
            if paralelo and paralelo > 0:
                with self._lock:
                    self._paralelo_rate = round(paralelo, 4)

            if oficial and oficial > 0:
                self.set_rate(oficial, source="DolarApi Oficial (BCV)", fecha_valor=fecha or "")
                msg = f"Tasa BCV obtenida vía DolarApi: Bs. {oficial:,.2f}"
                if paralelo:
                    msg += f" | Paralelo: Bs. {paralelo:,.2f}"
                logger.info(f"[BCV] {msg}")
                return True, oficial, msg
        except Exception as e:
            logger.warning(f"[BCV] API de respaldo falló ({e}).")

        # Tier 3: Offline fallback to cached rate
        current = self.get_rate()
        return False, current, f"No se pudo sincronizar en línea. Usando tasa almacenada: Bs. {current:,.2f}"

    def to_bs(self, usd_amount: float) -> float:
        """Convert a USD dollar amount to Venezuelan Bolívares (VES)."""
        return round(float(usd_amount) * self.get_rate(), 2)

    def format_bs(self, bs_amount: float) -> str:
        """Format number as Venezuelan currency (e.g. Bs. 1.250,50)."""
        val_str = f"{bs_amount:,.2f}"
        # Standard Venezuelan formatting: dots for thousands, comma for decimals
        formatted = val_str.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"Bs. {formatted}"

    def format_bimonetary(self, usd_amount: float) -> str:
        """Format amount in both USD ($) and Bolívares (Bs.)."""
        bs = self.to_bs(usd_amount)
        return f"${usd_amount:.2f} · {self.format_bs(bs)}"


# Global singleton instance
bcv_service = BCVService()

