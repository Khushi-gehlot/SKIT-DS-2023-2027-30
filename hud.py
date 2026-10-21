"""
Live data for the HUD panels.

Everything here is real. A dashboard full of invented numbers looks
impressive for about ten seconds and then undermines the whole project, so
the panels are wired to actual sources rather than placeholders.
"""

from __future__ import annotations

import datetime


# =============== TODAY ===============

def today(history: list[dict], limit: int = 6) -> list[dict[str, str]]:
    """
    What the assistant has actually done today, newest first.

    The mockup showed a calendar here. Until a calendar is connected, showing
    real activity is more honest than inventing meetings - and for someone
    operating hands-free, a record of what was just run is arguably more
    useful anyway.
    """
    return [
        {
            "time": item.get("time", ""),
            "title": (item.get("heard") or "")[:46],
            "detail": (item.get("message") or "")[:52],
            "ok": bool(item.get("success")),
        }
        for item in history[:limit]
    ]


def clock() -> tuple[str, str]:
    """(date, time) formatted for the header bar."""
    now = datetime.datetime.now()
    return now.strftime("%a · %d %b %Y").upper(), now.strftime("%H:%M")
