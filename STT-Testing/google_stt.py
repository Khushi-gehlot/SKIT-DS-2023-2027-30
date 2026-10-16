"""
Google Web Speech - standalone test.

Not connected to the project. Run it, speak, see what it heard.

    python google_stt.py

Needs: SpeechRecognition, PyAudio, and an internet connection.
Ctrl+C to stop.
"""

import time

import speech_recognition as sr

LANGUAGE = "en-IN"      # try "en-US" to compare
TIMEOUT = 8             # seconds to wait for you to start speaking
PHRASE_LIMIT = 8        # maximum length of one utterance
PAUSE_THRESHOLD = 1.2   # silence that ends a phrase


def main():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = PAUSE_THRESHOLD
    recognizer.dynamic_energy_threshold = True

    print("=" * 56)
    print("GOOGLE WEB SPEECH TEST")
    print("=" * 56)

    try:
        with sr.Microphone() as source:
            print(f"Device sample rate : {source.SAMPLE_RATE} Hz")
            print("Calibrating - stay quiet for 1 second...")
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            # A dead or muted device calibrates to ~0, which makes the
            # recogniser trigger on nothing at all.
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
            text = recognizer.recognize_google(audio, language=LANGUAGE)
            print(f'[{time.time() - start:.1f}s]  "{text}"')
        except sr.UnknownValueError:
            print(f"[{time.time() - start:.1f}s]  (could not understand)")
        except sr.RequestError as e:
            print(f"(service unreachable: {e})")
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
