"""Audio & Text-to-Speech (TTS) service for Gymsis.

Uses native Linux Speech Dispatcher (spd-say) with asynchronous execution
so voice feedback never freezes the UI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading


class AudioService:
    """Manages voice announcements and auditory feedback."""

    def __init__(self, language: str = "es"):
        self.language = language
        self.enabled = True
        self._spd_say = shutil.which("spd-say")
        self._espeak = shutil.which("espeak") or shutil.which("espeak-ng")

    def speak(self, text: str, priority: str = "important"):
        """Speak text aloud in a background thread."""
        if not self.enabled or not text:
            return

        thread = threading.Thread(
            target=self._speak_worker,
            args=(text, priority),
            daemon=True,
            name="GymsisAudioWorker",
        )
        thread.start()

    def _speak_worker(self, text: str, priority: str):
        cleaned = text.replace('"', "").replace("'", "").replace("\n", " ").strip()
        if not cleaned:
            return

        # 1. Try spd-say (default high quality in modern Linux desktops)
        if self._spd_say:
            try:
                subprocess.run(
                    [
                        self._spd_say,
                        "-l", self.language,
                        "-t", "female1",
                        "-r", "5",      # slightly dynamic speed
                        "-p", "10",     # energetic pitch
                        "-i", "100",    # max volume
                        cleaned,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
                return
            except Exception:
                pass

        # 2. Fallback to espeak
        if self._espeak:
            try:
                subprocess.run(
                    [self._espeak, f"-v{self.language}", "-s", "160", cleaned],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
                return
            except Exception:
                pass

        # 3. Terminal beep fallback if no speech synthesizer is available
        print(f"\a[AUDIO TTS]: {cleaned}")

    def announce_access_granted(self, member_name: str, plan_name: str = ""):
        """Loud welcoming voice announcement for granted member."""
        first_name = member_name.split()[0] if member_name else "socio"
        msg = f"Bienvenido, {first_name}."
        self.speak(msg)

    def announce_access_denied(self, member_name: str = "", reason: str = ""):
        """Clear auditory warning for denied access."""
        if member_name:
            first_name = member_name.split()[0]
            if "moros" in reason.lower() or "vencid" in reason.lower():
                msg = f"Acceso denegado. Membresía vencida para {first_name}."
            else:
                msg = f"Acceso denegado para {first_name}."
        else:
            msg = "Acceso denegado. Tarjeta no registrada."
        self.speak(msg)

    def announce_tag_scanned(self, uid: str):
        """Auditory confirmation when linking a tag in settings/registration."""
        self.speak("Llavero detectado correctamente.")


# Global singleton instance
audio = AudioService()
