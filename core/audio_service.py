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


# Standard reusable audio phrases (Zero download delay, 100% offline local playback)
REUSABLE_PHRASES = {
    "granted": "¡Bienvenido, acceso concedido!",
    "exit": "Hasta luego, que tenga un buen día.",
    "denied_unregistered": "Acceso denegado, tarjeta no registrada.",
    "denied_expired": "Acceso denegado, membresía vencida.",
    "tag_scanned": "Llavero detectado correctamente.",
}


class AudioService:
    """Manages high-definition neural speech announcements and audio playback."""

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice
        self.enabled = True
        self._players = []
        for p_name in ("pw-play", "gst-play-1.0", "ffplay", "mpv", "aplay"):
            p_path = shutil.which(p_name)
            if p_path:
                self._players.append(p_path)

        self._player = self._players[0] if self._players else None
        self._spd_say = shutil.which("spd-say")
        self._lock = threading.Lock()

        # Warm reusable standard cache on startup
        self.warm_reusable_cache()

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
                res = subprocess.run(
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
                if res.returncode == 0:
                    return
            except Exception:
                pass

        print(f"\a[AUDIO]: {cleaned}")

    def _play_neural_tts(self, text: str) -> bool:
        """Generate/Fetch cached MP3 and play via system audio player."""
        if not self._players:
            return False

        # Generate a stable hash key for the text + voice combo
        cache_key = hashlib.md5(f"{self.voice}:{text}".encode("utf-8")).hexdigest()
        cache_file = CACHE_DIR / f"{cache_key}.mp3"

        # Generate if not in cache or if existing file is empty/corrupted
        if not cache_file.exists() or cache_file.stat().st_size == 0:
            try:
                import edge_tts

                async def _generate():
                    communicate = edge_tts.Communicate(text, self.voice, rate="+0%", pitch="-4Hz")
                    await communicate.save(str(cache_file))

                asyncio.run(_generate())
            except Exception:
                try:
                    if cache_file.exists() and cache_file.stat().st_size == 0:
                        cache_file.unlink(missing_ok=True)
                except Exception:
                    pass
                return False

        # Verify cache file has actual audio bytes
        if not cache_file.exists() or cache_file.stat().st_size == 0:
            try:
                cache_file.unlink(missing_ok=True)
            except Exception:
                pass
            return False

        # Try players in order until one plays successfully
        for player in self._players:
            try:
                if "pw-play" in player:
                    cmd = [player, str(cache_file)]
                elif "gst-play" in player:
                    cmd = [player, "--quiet", str(cache_file)]
                elif "ffplay" in player:
                    cmd = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(cache_file)]
                elif "mpv" in player:
                    cmd = [player, "--no-video", "--really-quiet", str(cache_file)]
                else:
                    cmd = [player, str(cache_file)]

                res = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=8,
                )
                if res.returncode == 0:
                    return True
            except Exception:
                continue

        return False

    def announce_access_granted(self, member_name: str = "", plan_name: str = ""):
        """Standard welcoming voice announcement for granted member (reusable, 0ms latency)."""
        self.speak(REUSABLE_PHRASES["granted"])

    def announce_access_exit(self, member_name: str = ""):
        """Standard farewell voice announcement when member exits gym (reusable, 0ms latency)."""
        self.speak(REUSABLE_PHRASES["exit"])

    def announce_access_denied(self, member_name: str = "", reason: str = ""):
        """Standard auditory warning for denied access (reusable, 0ms latency)."""
        if reason and ("moros" in reason.lower() or "vencid" in reason.lower()):
            self.speak(REUSABLE_PHRASES["denied_expired"])
        else:
            self.speak(REUSABLE_PHRASES["denied_unregistered"])

    def announce_tag_scanned(self, uid: str = ""):
        """Auditory confirmation when linking a tag in settings/registration."""
        self.speak(REUSABLE_PHRASES["tag_scanned"])

    def warm_reusable_cache(self):
        """Pre-generate the 5 standard reusable audio files so they are 100% on disk with 0ms delay."""
        def _worker():
            for text in REUSABLE_PHRASES.values():
                cleaned = text.replace('"', "").replace("'", "").replace("\n", " ").strip()
                cache_key = hashlib.md5(f"{self.voice}:{cleaned}".encode("utf-8")).hexdigest()
                cache_file = CACHE_DIR / f"{cache_key}.mp3"
                if not cache_file.exists() or cache_file.stat().st_size == 0:
                    try:
                        import edge_tts
                        import asyncio

                        async def _gen(t=cleaned, path=cache_file):
                            c = edge_tts.Communicate(t, self.voice, rate="+0%", pitch="-4Hz")
                            await c.save(str(path))

                        asyncio.run(_gen())
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True, name="AudioReusablePrecacheWorker").start()


# Global singleton instance
audio = AudioService()
