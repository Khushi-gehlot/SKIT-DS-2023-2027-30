"""
Microphone diagnostic.

Run it, and it will count you in before recording so you know exactly when to
speak. It reports the signal level and what Google heard, for each candidate
input device, then tells you which device to use.

    python mic_test.py
"""

import audioop
import time

import speech_recognition as sr

PHRASE = "hello vyas open notepad"
CANDIDATES = [None, 6, 1, 0, 5, 12]   # None = Windows default device


def test(device_index):
    label = "default" if device_index is None else f"device {device_index}"
    r = sr.Recognizer()
    r.energy_threshold = 200
    r.dynamic_energy_threshold = False
    r.pause_threshold = 1.0

    try:
        with sr.Microphone(device_index=device_index) as source:
            print(f"\n--- {label} ---")
            print("    calibrating (stay quiet)...", end="", flush=True)
            r.adjust_for_ambient_noise(source, duration=1.0)
            print(f" noise floor = {r.energy_threshold:.0f}")

            for n in (3, 2, 1):
                print(f"    speak in {n}...", end="\r", flush=True)
                time.sleep(1)
            print(f'    SPEAK NOW: "{PHRASE}"            ')

            audio = r.listen(source, timeout=8, phrase_time_limit=6)
    except sr.WaitTimeoutError:
        print("    no speech detected — nothing reached the mic")
        return None
    except Exception as e:
        print(f"    unavailable ({type(e).__name__})")
        return None

    raw = audio.get_raw_data()
    rms = audioop.rms(raw, 2)
    peak = audioop.max(raw, 2)
    print(f"    level: rms={rms}  peak={peak}", end="")
    if rms < 150:
        print("   -> TOO QUIET")
    elif peak >= 32000 and rms < 1500:
        print("   -> CLIPPING / impulse noise, not speech")
    else:
        print("   -> good")

    try:
        text = r.recognize_google(audio, language="en-IN")
        print(f'    heard: "{text}"   <-- WORKS')
        return (device_index, rms, text)
    except sr.UnknownValueError:
        print("    heard: (could not understand)")
    except sr.RequestError as e:
        print(f"    Google unreachable: {e}")
    return None


def main():
    print("=" * 60)
    print("MICROPHONE DIAGNOSTIC")
    print("=" * 60)
    print(f'You will be counted in, then say: "{PHRASE}"')
    print("Speak normally, about 30 cm from the laptop.")
    input("\nPress Enter to begin...")

    working = [w for w in (test(d) for d in CANDIDATES) if w]

    print("\n" + "=" * 60)
    if not working:
        print("No device produced recognisable speech.")
        print("Check: Windows Settings > System > Sound > Input — speak and")
        print("watch the test bar move. Also raise Microphone Boost under")
        print("Sound Control Panel > Recording > Properties > Levels.")
    else:
        best = max(working, key=lambda w: w[1])
        idx = best[0]
        print(f"BEST DEVICE: {'default' if idx is None else idx}  (heard: \"{best[2]}\")")
        if idx is not None:
            print("\nUse it by setting this before running the app:")
            print(f"    $env:VYAS_MIC_INDEX = \"{idx}\"")
        else:
            print("\nThe Windows default device works — no change needed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
