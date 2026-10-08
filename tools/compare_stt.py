"""
Compare speech-to-text engines on the same audio.

Records once (or reads a WAV) and runs every engine over the identical
recording, so the comparison is fair - the usual mistake is recording twice
and comparing transcriptions of two different utterances.

    python tools/compare_stt.py                     record, then compare
    python tools/compare_stt.py sample.wav          compare an existing file
    python tools/compare_stt.py sample.wav "hello vyas open notepad"
                                                    also score against truth
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import speech_recognition as sr  # noqa: E402

import config  # noqa: E402
import core  # noqa: E402

WHISPER_MODELS = ["tiny", "base", "small"]


def record() -> sr.AudioData:
    r = sr.Recognizer()
    with sr.Microphone(device_index=config.MIC_INDEX) as source:
        print("Calibrating - stay quiet...")
        r.adjust_for_ambient_noise(source, duration=1.0)
        for n in (3, 2, 1):
            print(f"  Speak in {n}...", end="\r", flush=True)
            time.sleep(1)
        print("  SPEAK NOW".ljust(40))
        audio = r.listen(source, timeout=10, phrase_time_limit=8)
    print("  Done.".ljust(40))
    return audio


def load(path: str) -> sr.AudioData:
    r = sr.Recognizer()
    with sr.AudioFile(path) as source:
        return r.record(source)


def word_accuracy(expected: str, got: str) -> float:
    """Crude word overlap. Enough to rank engines, not a formal WER."""
    want = set(expected.lower().split())
    have = set((got or "").lower().replace(",", "").replace(".", "").split())
    return 100.0 * len(want & have) / len(want) if want else 0.0


def main():
    path = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".wav") else None
    truth = sys.argv[2] if len(sys.argv) > 2 else None

    audio = load(path) if path else record()
    print()

    results = []

    # Google
    config.STT_ENGINE = "google"
    start = time.time()
    text = core.transcribe_audio(audio)
    results.append(("google", text, time.time() - start))

    # Whisper, each model size
    config.STT_ENGINE = "whisper"
    for model in WHISPER_MODELS:
        config.WHISPER_MODEL = model
        core._whisper_model = None          # force a reload
        start = time.time()
        text = core.transcribe_audio(audio)
        results.append((f"whisper-{model}", text, time.time() - start))

    print()
    print("=" * 72)
    header = f"{'engine':16} {'seconds':>8}  transcription"
    if truth:
        header = f"{'engine':16} {'seconds':>8} {'match':>6}  transcription"
    print(header)
    print("-" * 72)
    for name, text, seconds in results:
        shown = (text or "(nothing)")[:40]
        if truth:
            print(f"{name:16} {seconds:8.1f} {word_accuracy(truth, text):5.0f}%  {shown}")
        else:
            print(f"{name:16} {seconds:8.1f}  {shown}")
    print("=" * 72)
    if truth:
        print(f"expected: {truth}")
    print()
    print("Timings include a one-off model load on first use of each size.")
    print("Switch engine permanently with VYAS_STT=google or VYAS_STT=whisper,")
    print("and model size with VYAS_WHISPER_MODEL=tiny|base|small.")


if __name__ == "__main__":
    main()
