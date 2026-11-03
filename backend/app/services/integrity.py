"""Rule-based integrity summary built from browser proctoring events.

These are signals for a human reviewer, never an automated verdict. There is no face
recognition or other biometric analysis anywhere in this project.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel

EventKind = Literal[
    "tab_hidden",
    "tab_visible",
    "window_blur",
    "fullscreen_exit",
    "copy",
    "paste",
    "camera_unavailable",
]
EVENT_KINDS: tuple[str, ...] = get_args(EventKind)
TAB_SWITCH_LIMIT = 3
TIME_AWAY_LIMIT_SECONDS = 60
SNAPSHOT_COVERAGE_MIN = 0.5


@dataclass(frozen=True)
class EventRecord:
    kind: str
    at: datetime
    detail: str = ""


class Flag(BaseModel):
    level: Literal["info", "warning"]
    message: str


class TimelineEntry(BaseModel):
    kind: str
    at: datetime
    offset_seconds: int
    detail: str


class IntegritySummary(BaseModel):
    risk: Literal["low", "medium", "high"]
    flags: list[Flag]
    counts: dict[str, int]
    time_away_seconds: int
    snapshots_received: int
    snapshots_expected: int
    timeline: list[TimelineEntry]


def time_away_seconds(events: list[EventRecord], ended_at: datetime) -> float:
    """Total time the test tab was hidden; a tab still hidden at the end counts until then."""
    total = 0.0
    hidden_since: datetime | None = None
    for event in events:
        if event.kind == "tab_hidden" and hidden_since is None:
            hidden_since = event.at
        elif event.kind == "tab_visible" and hidden_since is not None:
            total += (event.at - hidden_since).total_seconds()
            hidden_since = None
    if hidden_since is not None:
        total += max(0.0, (ended_at - hidden_since).total_seconds())
    return total


def expected_snapshots(started_at: datetime, ended_at: datetime, interval_seconds: int) -> int:
    """The browser takes one snapshot right away, then one every interval."""
    if interval_seconds <= 0:
        return 0
    return 1 + int((ended_at - started_at).total_seconds() // interval_seconds)


def _times(count: int) -> str:
    return "once" if count == 1 else f"{count} times"


def build_flags(counts: Counter[str], away: float, received: int, expected: int) -> list[Flag]:
    warnings: list[str] = []
    notes: list[str] = []
    if counts["tab_hidden"] >= TAB_SWITCH_LIMIT:
        warnings.append(f"Left the test tab {_times(counts['tab_hidden'])}")
    if away >= TIME_AWAY_LIMIT_SECONDS:
        warnings.append(f"Away from the test for {int(away)}s in total")
    if counts["paste"]:
        warnings.append(f"Pasted content {_times(counts['paste'])}")
    if counts["camera_unavailable"]:
        warnings.append("Webcam was unavailable or blocked")
    elif expected and received < expected * SNAPSHOT_COVERAGE_MIN:
        warnings.append(f"Only {received} of ~{expected} expected webcam snapshots arrived")
    if counts["fullscreen_exit"]:
        notes.append(f"Exited full screen {_times(counts['fullscreen_exit'])}")
    if counts["copy"]:
        notes.append(f"Copied text {_times(counts['copy'])}")
    return [Flag(level="warning", message=m) for m in warnings] + [
        Flag(level="info", message=m) for m in notes
    ]


def risk_level(flags: list[Flag]) -> Literal["low", "medium", "high"]:
    warnings = sum(1 for flag in flags if flag.level == "warning")
    if warnings >= 3:
        return "high"
    return "medium" if warnings else "low"


def summarize(
    events: list[EventRecord],
    started_at: datetime,
    ended_at: datetime,
    snapshots_received: int,
    snapshot_interval_seconds: int,
) -> IntegritySummary:
    ordered = sorted(events, key=lambda event: event.at)
    counts = Counter(event.kind for event in ordered)
    away = time_away_seconds(ordered, ended_at)
    expected = expected_snapshots(started_at, ended_at, snapshot_interval_seconds)
    flags = build_flags(counts, away, snapshots_received, expected)
    return IntegritySummary(
        risk=risk_level(flags),
        flags=flags,
        counts={kind: counts[kind] for kind in EVENT_KINDS},
        time_away_seconds=int(away),
        snapshots_received=snapshots_received,
        snapshots_expected=expected,
        timeline=[
            TimelineEntry(
                kind=event.kind,
                at=event.at,
                offset_seconds=int((event.at - started_at).total_seconds()),
                detail=event.detail,
            )
            for event in ordered
        ],
    )
