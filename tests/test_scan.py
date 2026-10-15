import json
from pathlib import Path

from dingz_ha_bridge.scan import (
    FoundDevice,
    _parse_announce,
    merge_devices,
    parse_device_response,
    parse_mdns,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_mdns_from_fixture() -> None:
    lines = (FIXTURES / "mdns_http_tcp.txt").read_text().splitlines()
    server = lines[1].split(" at ")[1].rsplit(":", 1)[0]
    txt = lines[2].strip().replace("\\ ", "\0").split(" ")
    props = {
        k.encode(): v.replace("\0", " ").encode() for k, v in (item.split("=", 1) for item in txt)
    }
    device = parse_mdns(server, props, ["192.0.2.50"])
    assert device == FoundDevice(
        host="192.0.2.50",
        mac="246F28000001",
        mqtt_id="dingztest",
        name="Dingz Test",
        room="Room",
        model="dz1f-4b",
        fw_version="2.4.3",
        protected=False,
        has_pir=False,
        sources={"mdns"},
    )


def test_parse_mdns_without_address() -> None:
    assert parse_mdns("x.local.", {}, []) is None


def test_parse_device_response_from_fixture() -> None:
    data = json.loads((FIXTURES / "http" / "device.json").read_text())
    device = parse_device_response("192.0.2.50", data)
    assert device is not None
    assert (device.mac, device.model, device.has_pir) == ("246F28000001", "dz1f-4b", False)


def test_parse_device_response_rejects_other_devices() -> None:
    assert parse_device_response("h", {"AABBCCDDEEFF": {"type": "switch"}}) is None
    assert parse_device_response("h", {"a": {}, "b": {}}) is None
    assert parse_device_response("h", None) is None


def test_parse_announce() -> None:
    device = _parse_announce(
        "dingztest", b'{"model":"dz1f-pir","ip":"192.0.2.9","fw_version":"2.4.3"}'
    )
    assert device is not None
    assert (device.host, device.mqtt_id, device.model) == ("192.0.2.9", "dingztest", "dz1f-pir")
    assert _parse_announce("x", b"not json") is None
    assert _parse_announce("x", b'{"model":"dz1f-pir"}') is None


def test_merge_by_mac_host_and_mqtt_id() -> None:
    mdns = FoundDevice("192.0.2.9", mac="AA", name="Kitchen", mqtt_id="k", sources={"mdns"})
    mqtt = FoundDevice("192.0.2.9", mqtt_id="k", mqtt_online=True, sources={"mqtt"})
    other = FoundDevice("192.0.2.10", mac="BB", sources={"http"})
    moved = FoundDevice("192.0.2.11", mqtt_id="k", sources={"mqtt"})
    merged = merge_devices([mdns], [mqtt, other, moved])
    assert len(merged) == 2
    kitchen = next(d for d in merged if d.mac == "AA")
    assert kitchen.mqtt_online is True
    assert kitchen.sources == {"mdns", "mqtt"}
