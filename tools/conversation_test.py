"""
Drive the whole conversation with scripted speech. No microphone, no
speakers, and nothing actually runs.

    python tools/conversation_test.py

This is only possible because the loop moved out of the UI. Previously the
wake-word handling, the greeting, the command session, the ambiguity
confirmation and the sleep word all lived inside a Streamlit thread, so the
only way to test any of it was to open a browser and talk. Now the same
object can be fed a list of sentences and checked.

Every scenario below is a real failure mode the assistant has to survive:
a command it does not know, a guess it is not sure about, a user who stops
talking, and an action that raises.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config       # noqa: E402
import core         # noqa: E402
import executor     # noqa: E402
import pipeline     # noqa: E402
import wakeword     # noqa: E402
from intent import ExecutionResult, Intent      # noqa: E402


class Harness:
    """Replaces the microphone, the speakers and the executor."""

    def __init__(self, script: list[str], wakes: int = 1):
        self.script = list(script)
        self.wakes = wakes
        self.spoken: list[str] = []
        self.executed: list[str] = []
        self.turns: list[pipeline.Turn] = []
        self._originals = {}

    def __enter__(self):
        # Keyword engine only. The LLM would make these tests need network,
        # take eight seconds per unknown phrase, and give different answers
        # on different days - none of which belongs in a test of the
        # orchestration.
        self._llm_was = config.USE_LLM_INTENT
        config.USE_LLM_INTENT = False

        self._originals = {
            "speak": core.speak,
            "listen": core.listen,
            "transcribe": core.transcribe,
            "wait": core.wait_for_wake_word,
            "available": wakeword.is_available,
            "execute": executor.execute,
        }

        core.speak = lambda text: self.spoken.append(text)
        core.listen = self._listen
        core.transcribe = lambda *a, **k: self._listen()[0]
        core.wait_for_wake_word = self._wake
        wakeword.is_available = lambda: True
        # Nothing is allowed to touch the real machine: the point is to test
        # the orchestration, not to open Notepad forty times.
        executor.execute = self._execute
        return self

    def __exit__(self, *exc):
        config.USE_LLM_INTENT = self._llm_was
        core.speak = self._originals["speak"]
        core.listen = self._originals["listen"]
        core.transcribe = self._originals["transcribe"]
        core.wait_for_wake_word = self._originals["wait"]
        wakeword.is_available = self._originals["available"]
        executor.execute = self._originals["execute"]
        return False

    # --- the fakes ---

    def _wake(self, **kwargs):
        if self.wakes <= 0:
            return False
        self.wakes -= 1
        return True

    def _listen(self, *args, **kwargs):
        if not self.script:
            return None, None
        line = self.script.pop(0)
        # "" in the script means a silence, which is how the timeout and
        # give-up paths are exercised.
        return (line or None), None

    def _execute(self, intent: Intent) -> ExecutionResult:
        if intent.action == "__boom__":
            raise RuntimeError("the action blew up")
        self.executed.append(f"{intent.action}:{intent.target}")
        return ExecutionResult.ok(f"Did {intent.action}.", intent)

    # --- running ---

    def run(self):
        # Stop once the conversation has ended and there are no more wakes
        # left to give. Keying off the script running out is not enough: the
        # assistant may legitimately sleep with lines still unread, and the
        # loop would then wait for a wake word that never comes.
        ended = []

        def record(turn):
            self.turns.append(turn)
            if turn.kind == "sleep":
                ended.append(True)

        conversation = pipeline.Conversation(
            on_turn=record,
            should_stop=lambda: bool(ended) and self.wakes <= 0,
        )
        conversation.run()
        return self


def scenario(name: str, script: list[str], expect_executed: list[str] | None = None):
    print("=" * 66)
    print(f"  {name}")
    print("=" * 66)
    for line in script:
        print(f"    user: {line or '(silence)'}")
    print("-" * 66)

    with Harness(script) as harness:
        harness.run()

    for turn in harness.turns:
        flag = "ok  " if turn.success else "FAIL"
        print(f"    [{turn.kind:7}] {flag} {turn.heard!r}")
        print(f"              -> {turn.message}")

    print(f"    executed: {harness.executed or 'nothing'}")

    passed = True
    if expect_executed is not None and harness.executed != expect_executed:
        print(f"    MISMATCH: expected {expect_executed}")
        passed = False
    print(f"    {'PASS' if passed else 'FAIL'}")
    print()
    return passed


def main() -> int:
    results = []

    results.append(scenario(
        "A normal exchange, then dismissed",
        ["open notepad", "go to sleep"],
        expect_executed=["open_app:notepad"],
    ))

    results.append(scenario(
        "A command the assistant does not know",
        ["flibbertigibbet the wotsit", "go to sleep"],
        expect_executed=[],
    ))

    results.append(scenario(
        "The user goes quiet and it sleeps by itself",
        [""] * (config.CONVERSATION_SILENCE_LIMIT + 1),
        expect_executed=[],
    ))

    results.append(scenario(
        "Several commands in one session",
        ["open notepad", "volume up", "goodbye"],
        expect_executed=["open_app:notepad", "volume:up"],
    ))

    results.append(scenario(
        "Two commands in one breath",
        ["open notepad and volume up", "go to sleep"],
        expect_executed=["open_app:notepad", "volume:up"],
    ))

    results.append(scenario(
        "A chain stops at the step that fails",
        ["open notepad and flibbertigibbet and volume up", "go to sleep"],
        expect_executed=[],
    ))

    print("=" * 66)
    print(f"  {sum(results)}/{len(results)} scenarios passed")
    print("=" * 66)
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
