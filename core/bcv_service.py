"""BCV Exchange Rate Service for Venezuelan Bolívares (VES / USD).

Provides real-time official exchange rates from the Banco Central de Venezuela (BCV),
with local persistence in database settings, offline fallback, manual override,
and bimonetary formatting for POS and membership payments.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import threading
import urllib.request
from typing import Optional, Tuple

logger = logging.getLogger("GymsisBCV")

DEFAULT_FALLBACK_RATE = 45.00


class BCVService:
    """Manages the official USD/VES exchange rate."""

    def __init__(self):
        self._current_rate: float = DEFAULT_FALLBACK_RATE
        self._last_updated: Optional[str] = None
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
            self._last_updated = settings.get("bcv_last_updated", "Inicial")
            self._source = settings.get("bcv_source", "Almacenado")
        except Exception:
            pass

    def get_rate(self) -> float:
        """Return the current official BCV exchange rate in Bs. per USD."""
        with self._lock:
            return self._current_rate

    def get_last_updated(self) -> str:
        """Return the timestamp of the last rate update."""
        with self._lock:
            return self._last_updated or "No sincronizado"

    def get_source(self) -> str:
        """Return the source of the rate (Oficial BCV or Manual)."""
        with self._lock:
            return self._source

    def set_manual_rate(self, new_rate: float) -> bool:
        """Explicitly set a manual rate override."""
        self._source = "Manual"
        return self.set_rate(new_rate)

    def set_rate(self, new_rate: float) -> bool:
        """Manually override or update the BCV rate and persist to database."""
        if new_rate <= 0:
            return False

        with self._lock:
            self._current_rate = round(float(new_rate), 4)
            self._last_updated = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            from core.db_store import save_settings
            from core.event_bus import event_bus

            save_settings({
                "bcv_rate": self._current_rate,
                "bcv_last_updated": self._last_updated,
                "bcv_source": self._source,
            })
            event_bus.publish("bcv_updated", self._current_rate)
            event_bus.publish("bcv_rate_updated", {"rate": self._current_rate, "updated": self._last_updated})
            return True
        except Exception as e:
            logger.error(f"[BCV] Error saving rate to DB: {e}")
            return False


    def fetch_official_rate(self) -> Tuple[bool, float, str]:
        """Fetch the latest official BCV dollar rate from public Venezuelan API."""
        endpoints = [
            "https://ve.dolarapi.com/v1/dolares/oficial",
            "https://pydolarvenezuela-api.vercel.app/api/v1/dollar?page=bcv",
        ]

        for url in endpoints:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "GymsisSystem/2.0"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))

                        rate = None
                        if "promedio" in data:
                            rate = float(data["promedio"])
                        elif "monitors" in data and "bcv" in data["monitors"]:
                            rate = float(data["monitors"]["bcv"].get("price", 0))
                        elif "price" in data:
                            rate = float(data["price"])

                        if rate and rate > 0:
                            self.set_rate(rate)
                            return True, rate, f"Tasa BCV actualizada: Bs. {rate:,.2f}"
            except Exception:
                continue

        return False, self.get_rate(), "No se pudo conectar con la API oficial del BCV. Usando tasa almacenada."

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
