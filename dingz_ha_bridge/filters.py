"""Temperature filter for the dingz periodic status dump.

FW 2.4.3 publishes ``sensor/temperature`` twice: on change with 0.5 °C resolution, and
every ~5 min in a status dump that floors the value to whole degrees (21.5 -> 21.0).
In HA that produces a saw-tooth. A dump is a burst of all topics of a device within
a few milliseconds that always ends with ``…/last_alive``; a change message comes alone.

The filter holds each temperature for ``window`` seconds. If a ``last_alive`` of the
same device arrives within that window, the value came from a dump and is dropped when
it is just the floored last good value. Everything is pure and driven by timestamps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

DEFAULT_WINDOW = 1.5


@dataclass
class _Pending:
    value: float
    received: float
    retained: bool


@dataclass
class TemperatureFilter:
    window: float = DEFAULT_WINDOW
    _pending: dict[str, _Pending] = field(default_factory=dict)
    _marker: dict[str, float] = field(default_factory=dict)
    _good: dict[str, float] = field(default_factory=dict)

    def seed(self, device_id: str, value: float) -> None:
        """Last published good value (e.g. our own retained topic after a restart)."""
        self._good.setdefault(device_id, value)

    def temperature(
        self, device_id: str, value: float, now: float, retained: bool = False
    ) -> list[tuple[str, float]]:
        """Record a raw value. Returns values that became due because a newer one arrived."""
        out = []
        if (previous := self._pending.get(device_id)) is not None:
            out += self._decide(device_id, previous)
        self._pending[device_id] = _Pending(value, now, retained)
        return out

    def dump_marker(self, device_id: str, now: float) -> None:
        self._marker[device_id] = now

    def due(self, now: float) -> list[tuple[str, float]]:
        """Values whose waiting window has passed and that should be published."""
        out = []
        for device_id, pending in list(self._pending.items()):
            if now - pending.received >= self.window:
                del self._pending[device_id]
                out += self._decide(device_id, pending)
        return out

    def exact(self, device_id: str, value: float) -> list[tuple[str, float]]:
        """An exact reading (HTTP ``room_temperature``), e.g. to correct the start value."""
        if self._good.get(device_id) == value:
            return []
        self._good[device_id] = value
        return [(device_id, value)]

    def last_good(self, device_id: str) -> float | None:
        return self._good.get(device_id)

    def _decide(self, device_id: str, pending: _Pending) -> list[tuple[str, float]]:
        self._pending.pop(device_id, None)
        marker = self._marker.get(device_id)
        from_dump = pending.retained or (
            marker is not None and abs(marker - pending.received) <= self.window
        )
        good = self._good.get(device_id)
        if from_dump and good is not None and is_floor_of(pending.value, good):
            return []
        if good == pending.value:
            return []
        self._good[device_id] = pending.value
        return [(device_id, pending.value)]


def is_floor_of(value: float, good: float) -> bool:
    """True if ``value`` is ``good`` floored to whole degrees (21.0 for 21.5 or 21.0)."""
    return value == math.floor(good)
