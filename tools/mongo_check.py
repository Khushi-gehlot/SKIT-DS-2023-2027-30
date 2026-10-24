"""
Prove the voiceprint database works, end to end.

Run after installing MongoDB:

    python tools/mongo_check.py

It connects, writes a throwaway voiceprint, reads it back, checks the 256
numbers survived the round trip, then deletes it. Nothing real is touched -
the test speaker is named so it cannot collide with anyone's enrolment.

    python tools/mongo_check.py --migrate

also copies any voiceprints from the old voiceprints.json file into the
database, so enrolments recorded before MongoDB existed are not lost.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                       # noqa: E402
import voiceprint_store as store    # noqa: E402

TEST_SPEAKER = "__selftest__"


def check() -> bool:
    print("=" * 62)
    print("  Voiceprint storage check")
    print("=" * 62)
    print(f"  backend wanted : {config.VOICEPRINT_BACKEND}")
    print(f"  uri            : {config.MONGO_URI}")
    print(f"  database       : {config.MONGO_DB}")
    print(f"  collection     : {config.MONGO_COLLECTION}")
    print("-" * 62)

    backend = store.get_store()

    if backend.name != "mongodb":
        print(f"  FELL BACK to {backend.describe()}")
        print(f"  reason: {store.fallback_reason}")
        print()
        print("  MongoDB is not answering. Check that:")
        print("    - MongoDB Community Server is installed")
        print("    - the 'MongoDB' service is running (services.msc)")
        print("    - nothing else is using port 27017")
        return False

    print(f"  CONNECTED: {backend.describe()}")

    # --- write, read back, compare -------------------------------------
    original = np.random.rand(256).astype(np.float32)
    original /= np.linalg.norm(original)

    if not backend.save(original, TEST_SPEAKER, samples=4):
        print("  FAILED: could not write a document.")
        return False
    print("  write  ok")

    returned = backend.load(TEST_SPEAKER)
    if returned is None:
        print("  FAILED: wrote a document but could not read it back.")
        return False
    print("  read   ok")

    # float32 -> BSON double -> float32 is lossless, but assert it rather
    # than assume: a silently mangled embedding would fail verification in
    # a way that looks like the user's voice changed.
    drift = float(np.max(np.abs(original - returned)))
    if drift > 1e-6:
        print(f"  FAILED: values changed in storage (max drift {drift:g}).")
        return False
    print(f"  values intact (max drift {drift:g})")

    if hasattr(backend, "details"):
        document = backend.details(TEST_SPEAKER)
        if document:
            print("-" * 62)
            print("  document stored (embedding omitted):")
            print("   ", json.dumps(document, indent=4, default=str).replace("\n", "\n    "))

    if not backend.delete(TEST_SPEAKER):
        print("  WARNING: could not delete the test document.")
    else:
        print("-" * 62)
        print("  cleanup ok")

    enrolled = [s for s in backend.speakers() if s != TEST_SPEAKER]
    print(f"  enrolled speakers in the database: {enrolled or 'none yet'}")
    print("=" * 62)
    print("  ALL CHECKS PASSED")
    return True


def migrate() -> None:
    """Copy voiceprints.json into the database."""
    path = config.VOICEPRINT_FILE
    if not path.is_file():
        print(f"Nothing to migrate: {path.name} does not exist.")
        return

    backend = store.get_store()
    if backend.name != "mongodb":
        print("Not connected to MongoDB, so there is nowhere to migrate to.")
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Could not read {path.name}: {e}")
        return

    for speaker, embedding in data.items():
        vector = np.array(embedding, dtype=np.float32)
        ok = backend.save(vector, speaker, samples=0)
        print(f"  {speaker}: {'migrated' if ok else 'FAILED'}")

    print()
    print(f"Done. {path.name} is left in place as a backup; delete it once")
    print("you have confirmed the database copy works.")


if __name__ == "__main__":
    passed = check()
    if "--migrate" in sys.argv and passed:
        print()
        print("Migrating existing voiceprints...")
        migrate()
    sys.exit(0 if passed else 1)
