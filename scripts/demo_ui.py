"""Serve the web UI with invented demo devices, e.g. for the documentation screenshots.

Usage: python scripts/demo_ui.py <port> <en|de>
Then open http://127.0.0.1:<port>/?lang=<en|de> (append #192.0.2.53 for the details).
No network access: scan, device API and update check are replaced by fakes.
"""

import asyncio
import sys
import time

from dingz_ha_bridge import discovery as d
from dingz_ha_bridge import updates, web
from dingz_ha_bridge.bridge import Bridge, BridgeConfig, MqttConfig
from dingz_ha_bridge.device_api import DeviceApi, DeviceStatus, WifiSignal
from dingz_ha_bridge.scan import FoundDevice

port, lang = int(sys.argv[1]), sys.argv[2]
NAMES = {
    "en": [
        ("Living Room", "Living room"),
        ("Kitchen", "Kitchen"),
        ("Bathroom", "Bathroom"),
        ("Hallway", "Hallway"),
    ],
    "de": [("Wohnzimmer", "Wohnzimmer"), ("Küche", "Küche"), ("Bad", "Bad"), ("Flur OG", "Flur")],
}[lang]
DEVICES = [
    # host, mac, mqtt id, model, rssi, seconds since last message
    ("192.0.2.51", "246F28000051", "livingroom", "dz1f-4b", -58, 3),
    ("192.0.2.52", "246F28000052", "kitchen", "dz1f-pir", -67, 1),
    ("192.0.2.53", "246F28000053", "bathroom", "dz1f-pir", -74, 12),
    ("192.0.2.54", "246F28000054", "hallway", "dz1f-pir", -83, 41),
]
OUTPUTS = {
    "dz1f-4b": [
        ("light", True, False),
        ("light", True, True),
        ("light", True, False),
        ("light", True, False),
    ],
    "dz1f-pir": [
        ("light", True, True),
        ("power_socket", True, False),
        ("light", False, False),
        ("light", False, False),
    ],
}

found = [
    FoundDevice(
        host,
        mac=mac,
        mqtt_id=mid,
        name=f"Dingz {NAMES[i][0]}",
        room=NAMES[i][1],
        model=model,
        fw_version="2.4.3",
        protected=False,
        has_pir="pir" in model,
        mqtt_online=True,
        sources={"mdns", "mqtt"},
    )
    for i, (host, mac, mid, model, _, _) in enumerate(DEVICES)
]

bridge = Bridge(BridgeConfig(MqttConfig("192.0.2.10")))
registry = bridge.registry
start = time.time()
for _host, _mac, mid, model, _rssi, ago in DEVICES:
    registry.devices[mid] = d.DeviceState(mid, model=model)
    registry.published[d.discovery_topic(mid)] = b"{}"
    registry.last_message[mid] = (start - ago, f"dingz/{mid}/{model}/sensor/light")


async def fake_scan(**kwargs):
    return list(found)


async def fake_status(self):
    _host, mac, mid, model, _rssi, _ = next(x for x in DEVICES if x[0] == self.host)
    dev = next(f for f in found if f.host == self.host)
    return DeviceStatus(
        host=self.host,
        mac=mac,
        mqtt_id=mid,
        name=dev.name,
        room=dev.room,
        model=model,
        fw_version="2.4.3",
        hw_version="1.1.2",
        has_pir="pir" in model,
        protected=False,
        mqtt_enabled=True,
        mqtt_uri="mqtt://dingz:***@192.0.2.10",
        outputs=[
            {"ph_out_id": n, "type": t, "enable": e, "on": on, "value": 100}
            for n, (t, e, on) in enumerate(OUTPUTS[model])
        ],
    )


async def fake_wifi(self):
    rssi = next(x[4] for x in DEVICES if x[0] == self.host)
    aps = [rssi, rssi - 3, rssi - 17]
    from dingz_ha_bridge.device_api import rate_rssi, rssi_percent

    return WifiSignal("HomeIoT", rssi, rate_rssi(rssi), rssi_percent(rssi), aps)


async def fake_check():
    from dingz_ha_bridge import __version__ as v

    return updates.UpdateInfo(current=v, latest=v, checked_at=time.time())


web.scan = fake_scan
DeviceApi.status = fake_status
DeviceApi.wifi = fake_wifi
updates.check = fake_check


async def keep_alive():
    # Fresh "last message" times so the activity dots flash and the ages look real.
    while True:
        await asyncio.sleep(1)
        now = time.time()
        for _host, _mac, mid, model, _rssi, ago in DEVICES:
            if ago < 15:
                registry.last_message[mid] = (now - ago, f"dingz/{mid}/{model}/sensor/light")


async def main():
    config = web.WebConfig(bind="127.0.0.1", port=port, default_broker="192.0.2.10")
    await asyncio.gather(web.serve(config, bridge=bridge), keep_alive())


asyncio.run(main())
