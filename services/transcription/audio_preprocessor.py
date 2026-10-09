"""
Audio Preprocessor
==================
Validatie, normalisatie en conversie van audiobestanden vóór Whisper-transcriptie.

- Valideert bestand (bestaat, niet corrupt, niet te lang)
- Converteert elk formaat (incl. webm/opus) naar 16kHz mono WAV
- Berekent audio-metadata (duur, sample rate, channels)
- Gebruikt ffmpeg (beschikbaar in Docker-image)

Waarom pre-processing?
1. Whisper presteert optimaal op 16kHz mono WAV
2. Vroege detectie van corrupte bestanden (fail-fast)
3. Consistente input voor diarisatie (PyAnnote)
4. Logging van audio-kwaliteit voor debugging
"""

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Maximale duur in seconden (1 uur standaard, configureerbaar)
MAX_DURATION_SECONDS = 3600

# Whisper-optimale parameters
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1  # mono

# Ondersteunde inputformaten
SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".opus"}


@dataclass
class AudioInfo:
    """Metadata van een audiobestand."""
    path: Path
    duration_secs: float
    sample_rate: int
    channels: int
    codec: str
    format_name: str
    file_size_bytes: int
    needs_conversion: bool


class AudioPreprocessingError(Exception):
    """Fout bij audio-validatie of conversie."""
    pass


class AudioPreprocessor:
    """
    Validatie en conversie van audiobestanden.

    Gebruik:
        preprocessor = AudioPreprocessor()
        processed_path, info = await preprocessor.process("/pad/naar/audio.webm")
        # processed_path is nu een 16kHz mono WAV
    """

    def __init__(self, max_duration: int = MAX_DURATION_SECONDS):
        self.max_duration = max_duration
        self._ffmpeg_path = shutil.which("ffmpeg")
        self._ffprobe_path = shutil.which("ffprobe")

    @property
    def ffmpeg_available(self) -> bool:
        return self._ffmpeg_path is not None

    async def process(self, audio_path: str | Path) -> tuple[Path, AudioInfo]:
        """
        Valideer en converteer een audiobestand naar Whisper-optimaal formaat.

        Args:
            audio_path: Pad naar het bronbestand

        Returns:
            Tuple van (pad naar verwerkt bestand, audio metadata)

        Raises:
            AudioPreprocessingError: Bij validatie- of conversiefout
        """
        audio_path = Path(audio_path)

        # --- Stap 1: Basisvalidatie ---
        self._validate_file(audio_path)

        # --- Stap 2: Metadata ophalen ---
        info = await self._probe_audio(audio_path)

        logger.info(
            "Audio geanalyseerd",
            path=str(audio_path),
            duration=round(info.duration_secs, 1),
            sample_rate=info.sample_rate,
            channels=info.channels,
            codec=info.codec,
            needs_conversion=info.needs_conversion,
        )

        # --- Stap 3: Duurvalidatie ---
        if info.duration_secs > self.max_duration:
            raise AudioPreprocessingError(
                f"Audiobestand te lang: {info.duration_secs:.0f}s "
                f"(max {self.max_duration}s / {self.max_duration // 60} min)"
            )

        if info.duration_secs < 1.0:
            raise AudioPreprocessingError(
                "Audiobestand te kort (< 1 seconde). Is het bestand correct?"
            )

        # --- Stap 4: Conversie indien nodig ---
        if info.needs_conversion:
            converted_path = await self._convert_to_wav(audio_path, info)
            # Update info met nieuwe path
            info.path = converted_path
            return converted_path, info

        return audio_path, info

    def _validate_file(self, path: Path) -> None:
        """Basisvalidatie van het bestandspad."""
        if not path.exists():
            raise AudioPreprocessingError(f"Bestand niet gevonden: {path}")

        if not path.is_file():
            raise AudioPreprocessingError(f"Geen geldig bestand: {path}")

        if path.stat().st_size == 0:
            raise AudioPreprocessingError("Bestand is leeg (0 bytes)")

        if path.stat().st_size < 100:
            raise AudioPreprocessingError(
                f"Bestand te klein ({path.stat().st_size} bytes) - waarschijnlijk corrupt"
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise AudioPreprocessingError(
                f"Niet-ondersteund formaat: {ext}. "
                f"Gebruik: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

    async def _probe_audio(self, path: Path) -> AudioInfo:
        """Haal audio-metadata op via ffprobe."""
        if not self._ffprobe_path:
            # Fallback: minimale info zonder ffprobe
            return AudioInfo(
                path=path,
                duration_secs=0.0,
                sample_rate=0,
                channels=0,
                codec="unknown",
                format_name=path.suffix.lstrip("."),
                file_size_bytes=path.stat().st_size,
                needs_conversion=path.suffix.lower() != ".wav",
            )

        cmd = [
            self._ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "onbekende fout"
                raise AudioPreprocessingError(
                    f"Audio niet leesbaar (mogelijk corrupt): {error_msg}"
                )

            import json
            probe_data = json.loads(stdout.decode())

        except asyncio.TimeoutError:
            raise AudioPreprocessingError("Audio-analyse timeout (bestand te groot of corrupt)")
        except json.JSONDecodeError:
            raise AudioPreprocessingError("Audio-metadata niet parseerbaar")

        # Zoek de audio-stream
        audio_stream = None
        for stream in probe_data.get("streams", []):
            if stream.get("codec_type") == "audio":
                audio_stream = stream
                break

        if not audio_stream:
            raise AudioPreprocessingError(
                "Geen audio-track gevonden in bestand. Is het een geldig audiobestand?"
            )

        # Parse metadata
        duration = float(probe_data.get("format", {}).get("duration", 0))
        sample_rate = int(audio_stream.get("sample_rate", 0))
        channels = int(audio_stream.get("channels", 0))
        codec = audio_stream.get("codec_name", "unknown")
        format_name = probe_data.get("format", {}).get("format_name", "unknown")

        # Bepaal of conversie nodig is
        needs_conversion = (
            sample_rate != TARGET_SAMPLE_RATE
            or channels != TARGET_CHANNELS
            or codec not in ("pcm_s16le", "pcm_s16be")  # niet al WAV 16-bit
            or path.suffix.lower() != ".wav"
        )

        return AudioInfo(
            path=path,
            duration_secs=duration,
            sample_rate=sample_rate,
            channels=channels,
            codec=codec,
            format_name=format_name,
            file_size_bytes=path.stat().st_size,
            needs_conversion=needs_conversion,
        )

    async def _convert_to_wav(self, source: Path, info: AudioInfo) -> Path:
        """
        Converteer audiobestand naar 16kHz mono WAV (PCM 16-bit).

        Het geconverteerde bestand wordt naast het bronbestand geplaatst
        met suffix '_16k.wav'.
        """
        if not self._ffmpeg_path:
            logger.warning(
                "ffmpeg niet beschikbaar - skip conversie, gebruik origineel",
                source=str(source),
            )
            return source

        output_path = source.with_suffix(".16k.wav")

        cmd = [
            self._ffmpeg_path,
            "-y",                    # Overschrijf bestaand bestand
            "-i", str(source),       # Input
            "-ar", str(TARGET_SAMPLE_RATE),  # 16kHz
            "-ac", str(TARGET_CHANNELS),     # Mono
            "-c:a", "pcm_s16le",     # 16-bit PCM (WAV)
            "-f", "wav",             # WAV container
            str(output_path),
        ]

        logger.info(
            "Audio conversie gestart",
            source=str(source),
            target=str(output_path),
            from_codec=info.codec,
            from_rate=info.sample_rate,
            from_channels=info.channels,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "onbekende fout"
                raise AudioPreprocessingError(
                    f"Audio conversie mislukt: {error_msg}"
                )

        except asyncio.TimeoutError:
            raise AudioPreprocessingError(
                "Audio conversie timeout (bestand te groot of ffmpeg-probleem)"
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise AudioPreprocessingError(
                "Geconverteerd bestand is leeg - bronbestand mogelijk corrupt"
            )

        logger.info(
            "Audio conversie voltooid",
            output=str(output_path),
            output_size=output_path.stat().st_size,
        )

        return output_path
