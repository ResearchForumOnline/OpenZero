import os
import requests
import shutil
import subprocess
import tempfile
from typing import Dict

try:
    from .openzero_config import env_bool
except ImportError:
    from openzero_config import env_bool


class VoiceStack:
    def __init__(self, base_dir: str, config: Dict[str, str]):
        self.base_dir = base_dir
        self.config = config
        self.output_dir = os.path.join(base_dir, config.get("VOICE_OUTPUT_DIR", "voice"))
        os.makedirs(self.output_dir, exist_ok=True)

    def refresh(self, config: Dict[str, str]) -> None:
        self.config = config
        self.output_dir = os.path.join(self.base_dir, config.get("VOICE_OUTPUT_DIR", "voice"))
        os.makedirs(self.output_dir, exist_ok=True)

    def status(self) -> Dict[str, object]:
        backend = (self.config.get("VOICE_TTS_BACKEND") or "piper").strip().lower()
        return {
            "voice_enabled": env_bool(self.config, "VOICE_ENABLED"),
            "auto_listen": env_bool(self.config, "VOICE_AUTO_LISTEN"),
            "tts_enabled": env_bool(self.config, "VOICE_TTS_ENABLED"),
            "tts_backend": backend,
            "stt_model": self.config.get("VOICE_STT_MODEL", "base"),
            "tts_voice": self.config.get("VOICE_TTS_VOICE", "en_GB-alan-medium"),
            "voicebox_enabled": env_bool(self.config, "VOICEBOX_ENABLED"),
            "voicebox_url": self._voicebox_base_url(),
            "voicebox_profile": self.config.get("VOICEBOX_PROFILE", ""),
            "voicebox_engine": self.config.get("VOICEBOX_ENGINE", "auto"),
            "voicebox_health": self.voicebox_health(timeout_seconds=0.75) if backend in {"voicebox", "auto"} or env_bool(self.config, "VOICEBOX_ENABLED") else {"status": "disabled"},
            "piper_available": bool(shutil.which("piper")),
            "ffplay_available": bool(shutil.which("ffplay") or shutil.which("aplay")),
            "faster_whisper_available": self._has_faster_whisper(),
            "output_dir": self.output_dir,
        }

    def _has_faster_whisper(self) -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def _voicebox_base_url(self) -> str:
        return (self.config.get("VOICEBOX_URL") or "http://127.0.0.1:17493").strip().rstrip("/")

    def _voicebox_timeout(self) -> int:
        try:
            return max(3, min(600, int(self.config.get("VOICEBOX_TIMEOUT_SECONDS", "180"))))
        except Exception:
            return 180

    def voicebox_health(self, timeout_seconds: float = 3) -> Dict[str, object]:
        base_url = self._voicebox_base_url()
        try:
            response = requests.get(f"{base_url}/health", timeout=timeout_seconds)
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "status": "success" if response.ok else "error",
                "available": response.ok,
                "url": base_url,
                "http_status": response.status_code,
                "payload": payload,
            }
        except Exception as exc:
            return {"status": "error", "available": False, "url": base_url, "message": str(exc)}

    def voicebox_profiles(self) -> Dict[str, object]:
        base_url = self._voicebox_base_url()
        try:
            response = requests.get(f"{base_url}/profiles", timeout=8)
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            return {
                "status": "success" if response.ok else "error",
                "url": base_url,
                "http_status": response.status_code,
                "profiles": payload.get("items", payload) if isinstance(payload, dict) else payload,
            }
        except Exception as exc:
            return {"status": "error", "url": base_url, "message": str(exc), "profiles": []}

    def _speak_voicebox(self, text: str) -> Dict[str, object]:
        base_url = self._voicebox_base_url()
        payload: Dict[str, object] = {"text": text}
        profile = (self.config.get("VOICEBOX_PROFILE") or "").strip()
        engine = (self.config.get("VOICEBOX_ENGINE") or "auto").strip()
        language = (self.config.get("VOICEBOX_LANGUAGE") or "en").strip()
        if profile:
            payload["profile"] = profile
        if engine and engine != "auto":
            payload["engine"] = engine
        if language:
            payload["language"] = language
        if (self.config.get("VOICEBOX_PERSONALITY") or "").lower() in {"true", "false"}:
            payload["personality"] = env_bool(self.config, "VOICEBOX_PERSONALITY")

        headers = {
            "Content-Type": "application/json",
            "X-Voicebox-Client-Id": "openzero",
        }
        try:
            response = requests.post(f"{base_url}/speak", json=payload, headers=headers, timeout=self._voicebox_timeout())
            response_payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"raw": response.text}
            if response.ok:
                return {
                    "status": "success",
                    "backend": "voicebox",
                    "url": base_url,
                    "profile": profile or "voicebox default",
                    "engine": engine,
                    "text": text,
                    "voicebox": response_payload,
                }
            return {
                "status": "error",
                "backend": "voicebox",
                "url": base_url,
                "http_status": response.status_code,
                "message": response_payload.get("detail") if isinstance(response_payload, dict) else "Voicebox speech failed.",
                "voicebox": response_payload,
                "text": text,
            }
        except Exception as exc:
            return {"status": "error", "backend": "voicebox", "url": base_url, "message": str(exc), "text": text}

    def transcribe_file(self, file_path: str) -> Dict[str, object]:
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"Audio file not found: {file_path}"}
        if not self._has_faster_whisper():
            return {
                "status": "error",
                "message": "faster-whisper is not installed. Install voice dependencies to enable local STT.",
            }

        from faster_whisper import WhisperModel

        model_name = self.config.get("VOICE_STT_MODEL", "base")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(file_path, vad_filter=True)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        return {
            "status": "success",
            "text": transcript,
            "language": getattr(info, "language", "unknown"),
            "duration": getattr(info, "duration", 0),
        }

    def speak_text(self, text: str, output_name: str = "openzero_reply.wav") -> Dict[str, object]:
        text = (text or "").strip()
        if not text:
            return {"status": "error", "message": "No text provided for speech."}
        if not env_bool(self.config, "VOICE_TTS_ENABLED"):
            return {"status": "skipped", "message": "VOICE_TTS_ENABLED is false.", "text": text}

        backend = (self.config.get("VOICE_TTS_BACKEND") or "piper").strip().lower()
        if backend in {"voicebox", "auto"} or env_bool(self.config, "VOICEBOX_ENABLED"):
            voicebox_result = self._speak_voicebox(text)
            if voicebox_result.get("status") == "success":
                return voicebox_result
            if backend == "voicebox" and not env_bool(self.config, "VOICEBOX_FALLBACK_PIPER"):
                return voicebox_result

        piper_binary = shutil.which("piper")
        if not piper_binary:
            return {
                "status": "error",
                "message": "Piper is not installed. Install voice dependencies to enable local TTS.",
                "text": text,
            }

        voice_name = self.config.get("VOICE_TTS_VOICE", "en_GB-alan-medium")
        output_path = os.path.join(self.output_dir, output_name)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(text)
            temp_path = handle.name

        try:
            command = [piper_binary, "--model", voice_name, "--output_file", output_path]
            result = subprocess.run(command, input=text, text=True, capture_output=True, timeout=120)
            if result.returncode != 0:
                return {"status": "error", "message": result.stderr.strip() or "Piper synthesis failed."}

            player = shutil.which("ffplay") or shutil.which("aplay")
            if player:
                if os.path.basename(player) == "ffplay":
                    subprocess.Popen([player, "-nodisp", "-autoexit", output_path])
                else:
                    subprocess.Popen([player, output_path])

            return {"status": "success", "path": output_path, "voice": voice_name, "text": text}
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
