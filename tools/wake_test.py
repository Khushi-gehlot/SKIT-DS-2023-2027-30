"""
Live wake-word meter.

    python tools/wake_test.py

Prints a bar for every 80ms of audio showing how confident the model is
that the wake phrase just occurred, and says DETECTED when it crosses the
threshold. Say the phrase a few times, then say other things, and watch
what separates them.

This exists because a threshold guessed in the abstract is worthless. What
matters is the gap between your voice saying the phrase and your room doing
anything else, and that can only be measured here. Pick a number comfortably
below your real detections and comfortably above everything else, then put
it in .env as VYAS_WAKE_THRESHOLD.

    python tools/wake_test.py --quiet      only print detections
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config      # noqa: E402
import core        # noqa: E402
import wakeword    # noqa: E402


def main() -> int:
    quiet = "--quiet" in sys.argv

    print("=" * 64)
    print("  Wake-word meter")
    print("=" * 64)
    print(f"  engine    : {config.WAKE_ENGINE}")
    print(f"  model     : {config.WAKE_MODEL}")
    print(f"  phrase    : \"{config.WAKE_PHRASE}\"")
    print(f"  threshold : {config.WAKE_THRESHOLD}")
    print("-" * 64)

    if not wakeword.is_available():
        print(f"  NOT AVAILABLE: {wakeword.describe()}")
        if wakeword.load_error():
            print(f"  {wakeword.load_error()}")
        return 1

    if wakeword.get_model() is None:
        print(f"  Model failed to load: {wakeword.load_error()}")
        return 1

    print(f"  Say \"{config.WAKE_PHRASE}\". Ctrl-C to stop.")
    print("-" * 64)

    stats = {
        "frames": 0, "detections": 0, "peak": 0.0,
        "peak_level": 0, "silent_frames": 0, "started": time.time(),
    }

    def on_score(value: float):
        stats["frames"] += 1
        stats["peak"] = max(stats["peak"], value)

        # Audio level, measured separately from the score. Without this
        # there is no way to tell "the microphone is dead" from "the
        # microphone is fine but the model does not recognise the phrase" -
        # two problems with completely different fixes.
        level = core.last_frame_level()
        stats["peak_level"] = max(stats["peak_level"], level)
        if level < 50:
            stats["silent_frames"] += 1

        if quiet:
            return

        # A line per frame would be 12 a second, so only draw when either
        # the model or the microphone has something to report. Every 25th
        # frame prints regardless, so the meter visibly stays alive.
        interesting = value >= 0.01 or level >= 300
        if not interesting and stats["frames"] % 25:
            return

        score_bar = "#" * int(value * 40)
        level_bar = "=" * min(20, int(level / 150))
        marker = "  <-- DETECTED" if value >= config.WAKE_THRESHOLD else ""
        print(
            f"  score {value:5.3f} |{score_bar:<40}|  "
            f"mic {level:5d} |{level_bar:<20}|{marker}"
        )

    try:
        while True:
            heard = core.wait_for_wake_word(on_score=on_score)
            if heard:
                stats["detections"] += 1
                print()
                print(f"  *** WAKE WORD #{stats['detections']} ***")
                print()
    except KeyboardInterrupt:
        pass
    finally:
        core.release_mic()
        elapsed = time.time() - stats["started"]
        print()
        print("-" * 64)
        frames = stats["frames"]
        print(f"  listened   : {elapsed:.0f}s ({frames} frames)")
        print(f"  detections : {stats['detections']}")
        print(f"  peak score : {stats['peak']:.3f}")
        print(f"  peak level : {stats['peak_level']} / 32767")
        if frames:
            quiet_pct = 100 * stats["silent_frames"] / frames
            print(f"  near-silent: {quiet_pct:.0f}% of frames")
        print("-" * 64)

        # Say what the numbers mean, rather than leaving the user to work
        # out which of three unrelated problems they have.
        if frames == 0:
            print("  No audio was read at all - the microphone never opened.")
        elif stats["peak_level"] < 500:
            print("  The microphone is delivering almost nothing.")
            print("  Wrong input device, or muted. Check Windows sound")
            print("  settings, then list devices with:")
            print("    python -c \"import core; core.list_microphones()\"")
            print("  and set VYAS_MIC_INDEX=<n> in .env")
        elif stats["detections"] == 0 and stats["peak"] < 0.01:
            print("  Audio is arriving, but the model never came close.")
            print("  It is not hearing the phrase as 'hey jarvis' - say it")
            print("  as two clear words, slightly slower, and try again.")
            print("  If that still fails, the model does not fit your voice")
            print("  and a custom-trained one is the answer.")
        elif stats["detections"] == 0:
            print(f"  Nothing crossed {config.WAKE_THRESHOLD}, but the peak was "
                  f"{stats['peak']:.3f}.")
            print(f"  Try VYAS_WAKE_THRESHOLD={max(0.1, stats['peak'] * 0.6):.2f} "
                  "in .env and run this again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
