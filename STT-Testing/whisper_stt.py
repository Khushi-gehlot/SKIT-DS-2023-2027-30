"""
Whisper (local) - standalone test.

Not connected to the project. Run it, speak, see what it heard.

    python whisper_stt.py              # base model
    python whisper_stt.py small        # a bigger, slower, usually better one

Needs: SpeechRecognition, PyAudio, faster-whisper, numpy.
    pip install faster-whisper

No internet needed once the model has downloaded (first run fetches it:
tiny ~75 MB, base ~145 MB, small ~480 MB).

Ctrl+C to stop.
"""

import sys
import time

import numpy as np
import speech_recognition as sr

MODEL = sys.argv[1] if len(sys.argv) > 1 else "base"
LANGUAGE = "en"         # forcing it stops Whisper guessing Welsh on short clips

# Whisper has no accent setting - one multilingual model, and `language` picks
# the language only ("en-IN" is not a valid value). The equivalent lever is
# initial_prompt: text that biases the decoder's vocabulary, as if the model
# had just been reading it. Seeding it with the words this assistant actually
# expects is far more effective than any accent switch would be, and it is how
# you stop "nova" coming back as "no va".
INITIAL_PROMPT = (
    "Nova is a voice assistant. Commands include: Nova, hello Nova, "
    "open Notepad, open Calculator, open Downloads, display settings, "
    "WiFi settings, Bluetooth, volume up, volume down, mute, scroll down, "
    "scroll up, take screenshot, battery, lock, shutdown, restart, "
    "open YouTube, search Google, click the second link, go back."
)
TIMEOUT = 8
PHRASE_LIMIT = 8
PAUSE_THRESHOLD = 1.2

# Whisper invents speech when it hears none - these are artefacts of its
# training data, and an always-on mic produces a lot of silence.
HALLUCINATIONS = {
    "thank you", "thanks for watching", "you", "bye", "thanks",
    "thank you for watching", "please subscribe", ".",
    "subtitles by the amara.org community",
}


def is_hallucination(text: str) -> bool:
    return text.strip().lower().strip(".!?,") in {
        h.strip(".!?,") for h in HALLUCINATIONS
    }


def main():
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is not installed. Run:")
        print("    pip install faster-whisper")
        return

    print("=" * 56)
    print(f"WHISPER TEST  (model: {MODEL}, local)")
    print("=" * 56)
    print("Loading model... first run downloads it.")

    start = time.time()
    # int8 keeps CPU inference fast with very little accuracy cost.
    model = WhisperModel(MODEL, device="cpu", compute_type="int8")
    print(f"Ready in {time.time() - start:.1f}s")

    recognizer = sr.Recognizer()
    recognizer.pause_threshold = PAUSE_THRESHOLD
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            print(f"Device sample rate : {source.SAMPLE_RATE} Hz")
            print("Calibrating - stay quiet for 1 second...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            if recognizer.energy_threshold < 100:
                recognizer.energy_threshold = 100
            print(f"Noise floor        : {recognizer.energy_threshold:.0f}")
    except Exception as e:
        print(f"\nCannot open the microphone: {type(e).__name__}: {e}")
        return

    print("\nSpeak when it says Listening. Ctrl+C to stop.\n")

    while True:
        try:
            with sr.Microphone() as source:
                print("Listening...", end=" ", flush=True)
                audio = recognizer.listen(
                    source, timeout=TIMEOUT, phrase_time_limit=PHRASE_LIMIT
                )
        except sr.WaitTimeoutError:
            print("(nothing heard)")
            continue
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"(mic error: {type(e).__name__})")
            continue

        start = time.time()
        try:
            # Hand Whisper a float32 array rather than a WAV file. Current
            # PyAV versions break faster-whisper's own file decoding, and this
            # also guarantees the 16 kHz mono it wants.
            pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

            segments, _info = model.transcribe(
                samples,
                language=LANGUAGE,
                initial_prompt=INITIAL_PROMPT,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(s.text for s in segments).strip()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"(whisper error: {type(e).__name__}: {e})")
            continue

        elapsed = time.time() - start
        if not text:
            print(f"[{elapsed:.1f}s]  (nothing recognised)")
        elif is_hallucination(text):
            print(f"[{elapsed:.1f}s]  (ignored hallucination: {text!r})")
        else:
            print(f'[{elapsed:.1f}s]  "{text}"')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
