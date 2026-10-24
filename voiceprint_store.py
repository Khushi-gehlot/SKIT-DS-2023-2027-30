"""
Where voiceprints are kept.

Two interchangeable backends behind one interface:

    MongoStore   a `voiceprints` collection, one document per speaker
    JsonStore    a local file, used when MongoDB is absent or unreachable

Everything above this module - voiceprint.py, auth.py, the UI - works in
terms of `get_store()` and never knows which one it got. That is what makes
the database swappable, and it is why the enrolment code did not have to
change when MongoDB arrived.

Falling back rather than failing is deliberate. An accessibility tool whose
microphone stops working because a database service is not running is worse
than one that quietly keeps a file. The fallback is announced, never silent.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import config

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    PYMONGO_AVAILABLE = True
except ImportError:
    MongoClient = None
    PyMongoError = Exception
    PYMONGO_AVAILABLE = False


# =============== INTERFACE ===============

class VoiceprintStore:
    """
    What any backend must do.

    Four operations, all of which have to survive the store being broken:
    a failed save returns False, a failed load returns None. Nothing here
    raises, because a storage fault must not take the assistant down mid
    command.
    """

    name = "none"

    def save(self, voiceprint: np.ndarray, speaker: str, samples: int = 0) -> bool:
        raise NotImplementedError

    def load(self, speaker: str) -> np.ndarray | None:
        raise NotImplementedError

    def delete(self, speaker: str) -> bool:
        raise NotImplementedError

    def speakers(self) -> list[str]:
        raise NotImplementedError

    def describe(self) -> str:
        """One line for the UI and the logs, so the user can see where their
        biometric data is actually going."""
        return self.name


# =============== MONGODB ===============

class MongoStore(VoiceprintStore):
    """
    One document per speaker in the `voiceprints` collection:

        {
          "_id":        "default",          # speaker name, unique by construction
          "embedding":  [0.013, -0.072, ...],   # 256 floats
          "dimensions": 256,
          "samples":    4,                  # recordings averaged into it
          "created_at": 2026-10-29T11:04:22Z,
          "updated_at": 2026-10-29T11:04:22Z
        }

    Using the speaker name as `_id` gives uniqueness and upsert for free -
    re-enrolling overwrites rather than accumulating duplicates, which is
    what a user re-recording their voice expects to happen.
    """

    name = "mongodb"

    def __init__(self, uri: str, database: str, collection: str):
        self.uri = uri
        self.database = database
        self.collection_name = collection
        # serverSelectionTimeoutMS is short on purpose. pymongo connects
        # lazily and would otherwise block for 30 seconds on a dead server -
        # unacceptable when this sits in front of the microphone.
        self._client = MongoClient(
            uri,
            serverSelectionTimeoutMS=config.MONGO_TIMEOUT_MS,
            appname="vyasa-voiceprints",
        )
        # Fail now, in the constructor, so get_store() can fall back to JSON
        # before anything depends on this working.
        self._client.admin.command("ping")
        self._collection = self._client[database][collection]

    def save(self, voiceprint: np.ndarray, speaker: str, samples: int = 0) -> bool:
        now = datetime.now(timezone.utc)
        try:
            self._collection.update_one(
                {"_id": speaker},
                {
                    "$set": {
                        # float() per element: numpy's float32 is not a type
                        # BSON knows, and pymongo refuses to encode it.
                        "embedding": [float(x) for x in voiceprint],
                        "dimensions": int(voiceprint.shape[0]),
                        "samples": samples,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            return True
        except PyMongoError as e:
            print(f"MongoDB save failed: {type(e).__name__}: {e}")
            return False

    def load(self, speaker: str) -> np.ndarray | None:
        try:
            document = self._collection.find_one(
                {"_id": speaker}, {"embedding": 1}
            )
        except PyMongoError as e:
            print(f"MongoDB read failed: {type(e).__name__}: {e}")
            return None

        if not document or not document.get("embedding"):
            return None
        return np.array(document["embedding"], dtype=np.float32)

    def delete(self, speaker: str) -> bool:
        try:
            return self._collection.delete_one({"_id": speaker}).deleted_count > 0
        except PyMongoError as e:
            print(f"MongoDB delete failed: {type(e).__name__}: {e}")
            return False

    def speakers(self) -> list[str]:
        try:
            return sorted(d["_id"] for d in self._collection.find({}, {"_id": 1}))
        except PyMongoError as e:
            print(f"MongoDB list failed: {type(e).__name__}: {e}")
            return []

    def details(self, speaker: str) -> dict | None:
        """Everything stored about one speaker, minus the 256 numbers.

        For the UI and for the report - 'enrolled on 29 Oct from 4 samples'
        is useful to a user in a way that the embedding never is.
        """
        try:
            return self._collection.find_one({"_id": speaker}, {"embedding": 0})
        except PyMongoError:
            return None

    def describe(self) -> str:
        # Never print the URI itself: on Atlas it carries the password.
        host = "localhost" if "localhost" in self.uri or "127.0.0.1" in self.uri \
            else "remote cluster"
        return f"MongoDB ({host}) -> {self.database}.{self.collection_name}"


# =============== JSON FILE (fallback) ===============

class JsonStore(VoiceprintStore):
    """The original file store, kept as the fallback and for machines with
    no MongoDB installed."""

    name = "json"

    def __init__(self, path: Path):
        self.path = path

    def _read_all(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            # A corrupt store should not stop the assistant working; it just
            # means nobody is enrolled.
            return {}

    def _write_all(self, data: dict) -> bool:
        try:
            self.path.write_text(json.dumps(data), encoding="utf-8")
            return True
        except Exception as e:
            print(f"Could not write the voiceprint file: {type(e).__name__}: {e}")
            return False

    def save(self, voiceprint: np.ndarray, speaker: str, samples: int = 0) -> bool:
        data = self._read_all()
        data[speaker] = voiceprint.tolist()
        return self._write_all(data)

    def load(self, speaker: str) -> np.ndarray | None:
        stored = self._read_all().get(speaker)
        return np.array(stored, dtype=np.float32) if stored else None

    def delete(self, speaker: str) -> bool:
        data = self._read_all()
        if speaker not in data:
            return False
        del data[speaker]
        return self._write_all(data)

    def speakers(self) -> list[str]:
        return sorted(self._read_all())

    def describe(self) -> str:
        return f"local file ({self.path.name})"


# =============== SELECTION ===============

_store: VoiceprintStore | None = None

# Set when MongoDB was asked for but could not be reached, so the UI can say
# so instead of silently appearing to work.
fallback_reason: str | None = None


def get_store() -> VoiceprintStore:
    """
    The configured store, built once.

    Tries MongoDB when it is asked for, falls back to the file when it is
    not available. The decision is made once per process: re-testing a dead
    database before every verification would add a timeout to each one.
    """
    global _store, fallback_reason
    if _store is not None:
        return _store

    json_store = JsonStore(config.VOICEPRINT_FILE)

    if config.VOICEPRINT_BACKEND != "mongodb":
        _store = json_store
        return _store

    if not PYMONGO_AVAILABLE:
        fallback_reason = "pymongo is not installed (pip install pymongo)"
    else:
        try:
            _store = MongoStore(
                config.MONGO_URI, config.MONGO_DB, config.MONGO_COLLECTION
            )
            print(f"Voiceprints: {_store.describe()}")
            return _store
        except Exception as e:
            fallback_reason = f"{type(e).__name__}: {e}"

    print(
        f"MongoDB unavailable, using the local file instead. ({fallback_reason})"
    )
    _store = json_store
    return _store


def reset():
    """Drop the cached store so the next call reconnects.

    Needed because Streamlit keeps the process alive across reruns: without
    this, starting MongoDB after the app would not be noticed until restart.
    """
    global _store, fallback_reason
    _store = None
    fallback_reason = None


def status() -> dict:
    """Backend, location and enrolled speakers - what the UI panel shows."""
    store = get_store()
    return {
        "backend": store.name,
        "location": store.describe(),
        "speakers": store.speakers(),
        "fallback_reason": fallback_reason,
    }
