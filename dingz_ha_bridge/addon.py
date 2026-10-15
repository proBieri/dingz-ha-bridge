"""Home Assistant add-on mode: settings from the Supervisor instead of CLI/env.

The Supervisor sets ``SUPERVISOR_TOKEN``. MQTT credentials come from
``GET http://supervisor/services/mqtt`` (``services: mqtt:need``), user options from
``/data/options.json``.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPERVISOR_URL = "http://supervisor"
OPTIONS_FILE = Path("/data/options.json")
# Requests through HA ingress always come from this address.
INGRESS_PEER = "172.30.32.2"
INGRESS_PORT = 8099


@dataclass
class AddonSettings:
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_tls: bool = False
    mqtt_tls_insecure: bool = False
    mqtt_ca_file: str | None = None
    id_prefix: str = "dingz"
    name_prefix: str = ""
    http_enrichment: bool = True
    log_level: str = "info"
    update_check: bool = True
    temperature_filter: bool = True


def is_addon() -> bool:
    return bool(os.environ.get("SUPERVISOR_TOKEN"))


def load_settings() -> AddonSettings:
    mqtt = _supervisor_get("/services/mqtt")
    options = _read_options()
    return AddonSettings(
        mqtt_host=str(mqtt["host"]),
        mqtt_port=int(mqtt.get("port") or 1883),
        mqtt_username=mqtt.get("username") or None,
        mqtt_password=mqtt.get("password") or None,
        mqtt_tls=bool(mqtt.get("ssl")),
        mqtt_tls_insecure=bool(options.get("mqtt_tls_insecure", False)),
        mqtt_ca_file=str(options.get("mqtt_ca_file") or "") or None,
        id_prefix=str(options.get("id_prefix") or "dingz"),
        name_prefix=str(options.get("name_prefix") or ""),
        http_enrichment=bool(options.get("http_enrichment", True)),
        log_level=str(options.get("log_level") or "info"),
        update_check=bool(options.get("update_check", True)),
        temperature_filter=bool(options.get("temperature_filter", True)),
    )


def _supervisor_get(path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        SUPERVISOR_URL + path,
        headers={"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.load(response)
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"unexpected Supervisor response for {path}")
    return data


def _read_options() -> dict[str, Any]:
    try:
        data = json.loads(OPTIONS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
