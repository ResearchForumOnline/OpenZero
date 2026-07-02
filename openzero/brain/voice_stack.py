import os
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
        return {
            "voice_enabled": env_bool(self.config, "VOICE_ENABLED"),
            "auto_listen": env_bool(self.config, "VOICE_AUTO_LISTEN"),
            "tts_enabled": env_bool(self.config, "VOICE_TTS_ENABLED"),
            "stt_model": self.config.get("VOICE_STT_MODEL", "base"),
            "tts_voice": self.config.get("VOICE_TTS_VOICE", "en_GB-alan-medium"),
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
