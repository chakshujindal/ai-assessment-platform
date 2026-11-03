from datetime import UTC, datetime, timedelta

from app.services.integrity import (
    EventRecord,
    expected_snapshots,
    summarize,
    time_away_seconds,
)

START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def at(seconds: int, kind: str, detail: str = "") -> EventRecord:
    return EventRecord(kind=kind, at=START + timedelta(seconds=seconds), detail=detail)


def test_time_away_pairs_hidden_and_visible_and_counts_open_gap() -> None:
    events = [at(10, "tab_hidden"), at(40, "tab_visible"), at(100, "tab_hidden")]
    assert time_away_seconds(events, START + timedelta(seconds=120)) == 50
    assert time_away_seconds([at(5, "tab_visible")], START) == 0


def test_expected_snapshots() -> None:
    end = START + timedelta(minutes=5)
    assert expected_snapshots(START, end, 30) == 11
    assert expected_snapshots(START, end, 0) == 0


def test_clean_attempt_is_low_risk() -> None:
    summary = summarize([], START, START + timedelta(minutes=5), 11, 30)
    assert summary.risk == "low"
    assert summary.flags == []
    assert summary.counts["paste"] == 0


def test_suspicious_attempt_is_high_risk_with_timeline() -> None:
    events = [
        at(30, "tab_hidden"),
        at(60, "tab_visible"),
        at(70, "tab_hidden"),
        at(110, "tab_visible"),
        at(120, "tab_hidden"),
        at(125, "tab_visible"),
        at(130, "paste", "42 chars"),
        at(140, "fullscreen_exit"),
        at(150, "copy"),
    ]
    summary = summarize(list(reversed(events)), START, START + timedelta(minutes=5), 2, 30)
    assert summary.risk == "high"
    messages = [f.message for f in summary.flags]
    assert "Left the test tab 3 times" in messages
    assert "Away from the test for 75s in total" in messages
    assert "Pasted content once" in messages
    assert "Only 2 of ~11 expected webcam snapshots arrived" in messages
    assert {f.level for f in summary.flags if "full screen" in f.message} == {"info"}
    assert [e.offset_seconds for e in summary.timeline][:2] == [30, 60]
    assert summary.timeline[6].detail == "42 chars"


def test_blocked_camera_is_one_warning_and_medium_risk() -> None:
    summary = summarize([at(1, "camera_unavailable")], START, START + timedelta(minutes=5), 0, 30)
    assert [f.message for f in summary.flags] == ["Webcam was unavailable or blocked"]
    assert summary.risk == "medium"
