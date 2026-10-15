import json
from pathlib import Path

from dingz_ha_bridge.filters import TemperatureFilter, is_floor_of
from dingz_ha_bridge.topics import Kind, parse_topic

CAPTURE = Path(__file__).parent / "fixtures" / "mqtt" / "wz_21min_fw2.4.3.jsonl"


def run(events: list[tuple[float, str, float | None]], seed: float | None = None) -> list[float]:
    """events: (time, "temp"|"marker", value). Returns the published values."""
    f = TemperatureFilter(window=1.5)
    if seed is not None:
        f.seed("d", seed)
    out: list[float] = []
    for t, kind, value in events:
        out += [v for _, v in f.due(t)]
        if kind == "temp":
            assert value is not None
            out += [v for _, v in f.temperature("d", value, t)]
        else:
            f.dump_marker("d", t)
    out += [v for _, v in f.due(10_000)]
    return out


def test_dump_value_is_dropped_when_it_is_the_floored_good_value() -> None:
    events = [
        (0.0, "temp", 21.5),  # change message
        (300.0, "temp", 21.0),  # dump ...
        (300.02, "marker", None),  # ... followed by last_alive
        (600.0, "temp", 21.0),
        (600.02, "marker", None),
    ]
    assert run(events) == [21.5]


def test_real_change_to_whole_degree_is_kept() -> None:
    events = [(0.0, "temp", 21.5), (50.0, "temp", 21.0)]  # no marker: change message
    assert run(events) == [21.5, 21.0]


def test_dump_with_other_value_is_used_as_fallback() -> None:
    events = [(0.0, "temp", 21.5), (300.0, "temp", 23.0), (300.02, "marker", None)]
    assert run(events) == [21.5, 23.0]


def test_first_dump_value_without_history_is_published() -> None:
    assert run([(0.0, "temp", 21.0), (0.02, "marker", None)]) == [21.0]


def test_seed_from_own_retained_value() -> None:
    assert run([(0.0, "temp", 21.0), (0.02, "marker", None)], seed=21.5) == []


def test_retained_raw_value_counts_as_dump() -> None:
    f = TemperatureFilter()
    f.seed("d", 22.5)
    f.temperature("d", 22.0, 0.0, retained=True)
    assert f.due(5.0) == []


def test_marker_before_window_end_only() -> None:
    # A last_alive long after a change message must not turn it into a dump.
    events = [(0.0, "temp", 21.5), (100.0, "temp", 21.0), (103.0, "marker", None)]
    assert run(events) == [21.5, 21.0]


def test_is_floor_of() -> None:
    assert is_floor_of(21.0, 21.5)
    assert is_floor_of(21.0, 21.0)
    assert not is_floor_of(21.0, 22.0)
    assert not is_floor_of(21.5, 21.5)


def test_replay_real_capture_removes_saw_tooth() -> None:
    """21 min of real traffic: dumps send 21.0/22.0, change messages 21.5/22.0/21.5."""
    f = TemperatureFilter()
    raw: list[float] = []
    published: list[float] = []
    for line in CAPTURE.read_text().splitlines()[1:]:
        r = json.loads(line)
        published += [v for _, v in f.due(r["t"])]
        info = parse_topic(r["topic"])
        if info is None:
            continue
        if info.kind is Kind.LAST_ALIVE:
            f.dump_marker(info.device_id, r["t"])
        elif info.kind is Kind.SENSOR and info.component == "temperature":
            raw.append(float(r["payload"]))
            published += [
                v
                for _, v in f.temperature(info.device_id, float(r["payload"]), r["t"], r["retain"])
            ]
    published += [v for _, v in f.due(1e9)]

    assert raw == [21.0, 21.0, 21.5, 21.0, 21.0, 22.0, 21.5, 21.0, 21.0]
    # Raw jumps 21.0 -> 21.5 -> 21.0 -> 22.0 -> 21.5 -> 21.0; filtered keeps the change messages.
    assert published == [21.0, 21.5, 22.0, 21.5]


def test_exact_value_corrects_floored_start_value() -> None:
    f = TemperatureFilter()
    f.temperature("d", 23.0, 0.0, retained=True)  # retained raw value from a dump
    assert f.exact("d", 23.5) == [("d", 23.5)]
    assert f.due(5.0) == []  # 23.0 is the floor of 23.5 -> dropped
    assert f.exact("d", 23.5) == []
