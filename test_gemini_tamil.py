import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"), override=True)

from app.services import gemini_service


SAMPLES = [
    ("greeting", "வணக்கம், நான் DigiDara Technologiesலிருந்து பேசுறேன்."),
    ("number_date", "உங்கள் batch ஜூலை 15 ஆம் தேதி காலை 10 மணிக்கு start ஆகும்."),
    ("code_mixed_course", "AI and Machine Learning course details WhatsAppல share பண்ணலாமா?"),
]


def safe_print_text(text: str) -> str:
    return (text or "").encode("ascii", errors="backslashreplace").decode("ascii")


async def main() -> int:
    out_dir = Path("/tmp")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Writing Gemini Tamil WAV files to: {out_dir}")
    generated = []
    for name, text in SAMPLES:
        wav_bytes = await gemini_service.text_to_speech_async(text, language_code="ta-IN")
        out_path = out_dir / f"gemini_tamil_{name}.wav"
        out_path.write_bytes(wav_bytes)
        generated.append((name, text, out_path))
        print(f"[TTS] {name}: {out_path} ({len(wav_bytes)} bytes)")

    audio_cache = Path(__file__).with_name("audio_cache")
    sarvam_files = sorted(audio_cache.glob("*.wav"))[:10] if audio_cache.exists() else []
    print("\nSarvam/audio_cache WAVs available for manual comparison:")
    if sarvam_files:
        for path in sarvam_files:
            print(f"- {path}")
    else:
        print("- none found")

    roundtrip_name, original_text, roundtrip_path = generated[0]
    transcript = await gemini_service.speech_to_text_async(
        roundtrip_path.read_bytes(),
        filename=roundtrip_path.name,
        language_code="ta-IN",
    )
    print("\n[Round-trip]")
    print(f"Original:   {safe_print_text(original_text)}")
    print(f"Transcript: {safe_print_text(transcript)}")

    if not transcript.strip():
        print("FAIL: empty transcript")
        return 1
    print("PASS: non-empty transcript returned")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
