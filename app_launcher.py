"""
Launch any application installed on this PC.

The old approach hard-coded six apps, which meant the assistant could not
open Chrome, VS Code, WhatsApp or anything else the user actually had. For a
tool meant to replace a mouse and keyboard entirely, that is the difference
between a demo and something usable: a person who cannot use their hands
needs to open *their* applications, not a list somebody chose in advance.

Windows already keeps the authoritative list - it is what the Start menu
shows - and `Get-StartApps` exposes it including packaged (UWP) apps that
have no .lnk file anywhere. Roughly 200 entries on a typical machine.

    launch("chrome")          -> opens Google Chrome
    launch("vs code")         -> opens Visual Studio Code
    find("ch")                -> [Chrome, Character Map, ...] for disambiguation
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import time

# Cache the index: enumerating apps takes about a second, and the set of
# installed applications does not change mid-conversation.
_apps: list[dict[str, str]] | None = None
_indexed_at: float = 0.0
INDEX_TTL = 600  # seconds

# Spoken names that will not fuzzy-match the real entry.
ALIASES = {
    "chrome": "google chrome",
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "code": "visual studio code",
    "word": "microsoft word",
    "excel": "microsoft excel",
    "powerpoint": "microsoft powerpoint",
    "cmd": "command prompt",
    "terminal": "windows terminal",
    "explorer": "file explorer",
    "files": "file explorer",
    "browser": "google chrome",
    "whatsapp": "whatsapp",
    "settings": "settings",
    "task manager": "task manager",
}


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def index(force: bool = False) -> list[dict[str, str]]:
    """
    All launchable applications, as [{"name", "app_id"}].

    Uses Get-StartApps because it covers both classic desktop programs and
    packaged apps; scanning Start-menu .lnk files misses the latter entirely.
    """
    global _apps, _indexed_at

    if _apps is not None and not force and (time.time() - _indexed_at) < INDEX_TTL:
        return _apps

    try:
        raw = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress",
            ],
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=30,
        )
        data = json.loads(raw)
        if isinstance(data, dict):      # a single app comes back unwrapped
            data = [data]
        _apps = [
            {"name": str(a.get("Name", "")), "app_id": str(a.get("AppID", ""))}
            for a in data
            if a.get("Name")
        ]
    except Exception as e:
        print(f"Could not index applications: {type(e).__name__}: {e}")
        _apps = []

    _indexed_at = time.time()
    return _apps


def find(spoken: str, limit: int = 5) -> list[dict[str, str]]:
    """
    Applications matching what was said, best first.

    Returns a list rather than one result on purpose: "open ch" is ambiguous
    between Chrome and Character Map, and guessing is worse than asking.
    """
    query = _normalise(ALIASES.get(_normalise(spoken), spoken))
    if not query:
        return []

    apps = index()
    scored: list[tuple[float, dict[str, str]]] = []

    for app in apps:
        name = _normalise(app["name"])
        if not name:
            continue

        if name == query:
            score = 1.0
        elif name.startswith(query):
            score = 0.9
        elif query in name:
            score = 0.8
        elif set(query.split()) <= set(name.split()):
            score = 0.75
        else:
            score = difflib.SequenceMatcher(None, query, name).ratio()
            if score < 0.6:
                continue
        scored.append((score, app))

    scored.sort(key=lambda pair: (-pair[0], len(pair[1]["name"])))
    return [app for _score, app in scored[:limit]]


def launch(spoken: str) -> tuple[bool, str, list[dict[str, str]]]:
    """
    Open the application the user named.

    Returns (launched, message, candidates). When several apps match closely,
    nothing is launched and the candidates come back so the caller can ask
    which one was meant.
    """
    matches = find(spoken)
    if not matches:
        return False, f"I could not find an app called {spoken}.", []

    # Ambiguous: several plausible matches and no clear winner.
    if len(matches) > 1:
        best = _normalise(matches[0]["name"])
        query = _normalise(ALIASES.get(_normalise(spoken), spoken))
        if best != query and not best.startswith(query):
            return False, "", matches

    app = matches[0]
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app['app_id']}"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        return False, f"I could not open {app['name']}: {e}", []

    return True, f"Opening {app['name']}", []


def launch_exact(app_id: str, name: str = "") -> tuple[bool, str]:
    """Launch a specific app chosen from a disambiguation list."""
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{app_id}"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True, f"Opening {name or 'the app'}"
    except Exception as e:
        return False, f"I could not open it: {e}"


if __name__ == "__main__":
    apps = index()
    print(f"{len(apps)} applications indexed\n")
    for query in ("chrome", "notepad", "vs code", "whatsapp", "spotify", "ch"):
        hits = find(query)
        shown = ", ".join(h["name"] for h in hits[:4]) or "(no match)"
        print(f"  {query!r:12} -> {shown}")
