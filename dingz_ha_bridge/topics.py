"""Parse dingz MQTT topics.

Layout: ``dingz/<id>/<model>/<kind>/<component>[/<index>]`` plus the per-device
meta topics ``dingz/<id>/online``, ``dingz/<id>/announce`` and ``dingz/<id>/last_alive``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

ROOT = "dingz"


class Kind(StrEnum):
    STATE = "state"
    COMMAND = "command"
    EVENT = "event"
    POWER = "power"
    ENERGY = "energy"
    SENSOR = "sensor"
    ONLINE = "online"
    ANNOUNCE = "announce"
    LAST_ALIVE = "last_alive"


META_KINDS = frozenset({Kind.ONLINE, Kind.ANNOUNCE, Kind.LAST_ALIVE})
CHANNEL_KINDS = frozenset(Kind) - META_KINDS


@dataclass(frozen=True, slots=True)
class TopicInfo:
    device_id: str
    model: str | None
    kind: Kind
    component: str | None = None
    index: int | None = None


def parse_topic(topic: str) -> TopicInfo | None:
    """Return the parsed topic, or ``None`` for anything that is not a dingz device topic."""
    parts = topic.split("/")
    if len(parts) < 3 or parts[0] != ROOT or not parts[1] or not all(parts):
        return None
    device_id = parts[1]

    if len(parts) == 3:
        try:
            kind = Kind(parts[2])
        except ValueError:
            return None
        return TopicInfo(device_id, None, kind) if kind in META_KINDS else None

    # FW 2.4.3 publishes last_alive below the model: dingz/<id>/<model>/last_alive.
    if len(parts) == 4:
        return (
            TopicInfo(device_id, parts[2], Kind.LAST_ALIVE) if parts[3] == Kind.LAST_ALIVE else None
        )

    if len(parts) not in (5, 6):
        return None
    _, _, model, kind_str, component, *rest = parts
    try:
        kind = Kind(kind_str)
    except ValueError:
        return None
    if kind not in CHANNEL_KINDS:
        return None

    index: int | None = None
    if rest:
        if not rest[0].isdigit():
            return None
        index = int(rest[0])
    return TopicInfo(device_id, model, kind, component, index)


def base_topic(device_id: str, model: str) -> str:
    return f"{ROOT}/{device_id}/{model}"


def channel_topic(
    device_id: str, model: str, kind: Kind, component: str, index: int | None = None
) -> str:
    topic = f"{base_topic(device_id, model)}/{kind}/{component}"
    return topic if index is None else f"{topic}/{index}"


def meta_topic(device_id: str, kind: Kind) -> str:
    return f"{ROOT}/{device_id}/{kind}"
