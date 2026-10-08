"""
Record, analyse and PLAY BACK a microphone sample.

The point of this tool is to let you HEAR what the assistant hears. If the
playback sounds distorted, muffled or silent, the problem is in the Windows
audio settings, not in the code.

    python mic_record_test.py          # Windows default input device
    python mic_record_test.py 6        # a specific device index
"""

import audioop
import os
import struct
import sys
import time
import wave

import speech_recognition as sr

SECONDS = 5
PHRASE = "hello vyas open notepad"


def _output_path() -> str:
    """Desktop if we can find it (OneDrive moves it), else next to this file."""
    home = os.path.expanduser("~")
    for candidate in (
        os.path.join(home, "OneDrive", "Desktop"),
        os.path.join(home, "Desktop"),
    ):
        if os.path.isdir(candidate):
            return os.path.join(candidate, "vyas_mic_sample.wav")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "vyas_mic_sample.wav")


OUT = _output_path()


def clipping_percent(raw: bytes) -> float:
    """Share of samples at or near full scale - the signature of distortion."""
    count = len(raw) // 2
    if not count:
        return 0.0
    values = struct.unpack(f"<{count}h", raw[: count * 2])
    clipped = sum(1 for v in values if v >= 32700 or v <= -32700)
    return 100.0 * clipped / count


def main():
    device = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    label = "DEFAULT DEVICE" if device is None else f"DEVICE {device}"

    print("=" * 58)
    print(f"RECORDING FROM {label}")
    print("=" * 58)

    r = sr.Recognizer()
    r.energy_threshold = 200
    r.dynamic_energy_threshold = False

    try:
        with sr.Microphone(device_index=device) as source:
            rate = source.SAMPLE_RATE
            print(f"Sample rate : {rate} Hz")
            print("Calibrating - stay quiet for 1 second...")
            r.adjust_for_ambient_noise(source, duration=1.0)
            print(f"Noise floor : {r.energy_threshold:.0f}")
            print()

            for n in (3, 2, 1):
                print(f"  Recording in {n}...", end="\r", flush=True)
                time.sleep(1)

            print(f'  SPEAK NOW for {SECONDS} seconds: "{PHRASE}"'.ljust(56))
            frames = source.stream.read(int(rate * SECONDS))
            print("  Done recording.".ljust(56))
    except Exception as e:
        print(f"\nCould not open the microphone: {type(e).__name__}: {e}")
        return

    rms = audioop.rms(frames, 2)
    peak = audioop.max(frames, 2)
    clip = clipping_percent(frames)

    print()
    print("-" * 58)
    print(f"  average level (rms) : {rms}")
    print(f"  peak level          : {peak}   (maximum possible 32767)")
    print(f"  clipped samples     : {clip:.2f}%")
    print("-" * 58)

    if rms < 120:
        print("  DIAGNOSIS: far too quiet. Raise the input level in Windows.")
    elif clip > 1.0:
        print("  DIAGNOSIS: audio is CLIPPING - distorted beyond recognition.")
        print("             Lower Microphone Boost in the Sound control panel.")
    elif rms < 400:
        print("  DIAGNOSIS: quiet but usable. Speak closer to the microphone.")
    else:
        print("  DIAGNOSIS: levels look healthy.")
    print()

    with wave.open(OUT, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    print(f"  Saved: {OUT}")

    # Play it back so you can hear exactly what was captured.
    try:
        import winsound
        print("  Playing it back now - listen carefully...")
        winsound.PlaySound(OUT, winsound.SND_FILENAME)
    except Exception as e:
        print(f"  (could not play automatically: {e} - open the file manually)")

    print()
    print("  Sending to Google...")
    audio = sr.AudioData(frames, rate, 2)
    for lang in ("en-IN", "en-US"):
        try:
            print(f'    {lang} -> "{r.recognize_google(audio, language=lang)}"')
        except sr.UnknownValueError:
            print(f"    {lang} -> could not understand")
        except sr.RequestError as e:
            print(f"    {lang} -> service error: {e}")

    print()
    print("=" * 58)
    print("  Did the playback sound like your voice, clearly?")
    print()
    print("   clear and normal -> audio is fine, report back")
    print("   distorted/buzzy  -> lower Microphone Boost in Windows")
    print("   very faint       -> raise the input level in Windows")
    print("   silence          -> wrong device, try another index")
    print("=" * 58)


if __name__ == "__main__":
    main()
