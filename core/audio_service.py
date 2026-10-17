"""Audio & Text-to-Speech (TTS) service for Gymsis with HD Neural Spanish voices.

Uses Microsoft Neural TTS (edge-tts) for ultra-realistic human voices in Spanish
(Venezuelan / Latin American neutral), with audio caching for instant zero-latency
playback on turnstiles and entrance kiosks.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import subprocess
import threading
from pathlib import Path

# Local cache directory for instant audio playback without network latency
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "audio"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Voice selection: Dalia (Mujer madura, elegante, profesional de recepción)
DEFAULT_VOICE = "es-MX-DaliaNeural"


class AudioService:
    """Manages high-definition neural speech announcements and audio playback."""

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice
        self.enabled = True
        self._player = shutil.which("ffplay") or shutil.which("gst-play-1.0") or shutil.which("mpv")
        self._spd_say = shutil.which("spd-say")
        self._lock = threading.Lock()

    def speak(self, text: str, priority: str = "normal"):
        """Speak text aloud in high quality using a background thread."""
        if not self.enabled or not text:
            return

        thread = threading.Thread(
            target=self._speak_worker,
            args=(text,),
            daemon=True,
            name="GymsisNeuralAudioWorker",
        )
        thread.start()

    def _speak_worker(self, text: str):
        cleaned = text.replace('"', "").replace("'", "").replace("\n", " ").strip()
        if not cleaned:
            return

        # 1. Try High-Definition Neural TTS (edge-tts with disk caching)
        success = self._play_neural_tts(cleaned)
        if success:
            return

        # 2. Fallback to local system Speech Dispatcher with Latin American Spanish
        if self._spd_say:
            try:
                subprocess.run(
                    [
                        self._spd_say,
                        "-l", "es-419",
                        "-t", "female1",
                        "-r", "0",
                        "-p", "5",
                        "-i", "100",
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

        print(f"\a[AUDIO]: {cleaned}")

    def _play_neural_tts(self, text: str) -> bool:
        """Generate/Fetch cached MP3 and play via system audio player."""
        if not self._player:
            return False

        # Generate a stable hash key for the text + voice combo
        cache_key = hashlib.md5(f"{self.voice}:{text}".encode("utf-8")).hexdigest()
        cache_file = CACHE_DIR / f"{cache_key}.mp3"

        # Generate if not in cache
        if not cache_file.exists():
            try:
                import edge_tts

                async def _generate():
                    communicate = edge_tts.Communicate(text, self.voice, rate="+0%", pitch="-3Hz")
                    await communicate.save(str(cache_file))

                asyncio.run(_generate())
            except Exception as e:
                # Network down or edge-tts error
                return False

        # Play audio file
        try:
            if "ffplay" in self._player:
                cmd = [self._player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(cache_file)]
            elif "gst-play" in self._player:
                cmd = [self._player, "--quiet", str(cache_file)]
            elif "mpv" in self._player:
                cmd = [self._player, "--no-video", "--really-quiet", str(cache_file)]
            else:
                return False

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=8)
            return True
        except Exception:
            return False

    def announce_access_granted(self, member_name: str, plan_name: str = ""):
        """Loud welcoming voice announcement for granted member."""
        first_name = member_name.split()[0] if member_name else "socio"
        msg = f"¡Bienvenido, {first_name}!"
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
