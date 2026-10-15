"""Home Assistant add-on mode: settings from the Supervisor and/or the add-on options.

The Supervisor sets ``SUPERVISOR_TOKEN`` and provides user options in ``/data/options.json``.
MQTT broker settings come from, in order of precedence:
1. the add-on options (``mqtt_host`` …) — for an external broker;
2. the Supervisor MQTT service (``GET /services/mqtt``, needs the Mosquitto add-on or
   another ``mqtt`` service provider).
If neither is available the add-on stops with a clear message.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
OPTIONS_FILE = Path("/data/options.json")
# Requests through HA ingress always come from this address.
INGRESS_PEER = "172.30.32.2"
INGRESS_PORT = 8099


class AddonConfigError(RuntimeError):
    """A configuration problem the user must fix (shown without a traceback)."""


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
    options = _read_options()
    broker = _broker_from_options(options) or _broker_from_supervisor()
    if broker is None:
        raise AddonConfigError(
            "No MQTT broker configured. Either install the Mosquitto broker add-on, or set "
            "'mqtt_host' (and user/password) in this add-on's configuration."
        )
    return AddonSettings(
        mqtt_host=broker["host"],
        mqtt_port=broker["port"],
        mqtt_username=broker["username"],
        mqtt_password=broker["password"],
        mqtt_tls=broker["tls"],
        mqtt_tls_insecure=bool(options.get("mqtt_tls_insecure", False)),
        mqtt_ca_file=str(options.get("mqtt_ca_file") or "") or None,
        id_prefix=str(options.get("id_prefix") or "dingz"),
        name_prefix=str(options.get("name_prefix") or ""),
        http_enrichment=bool(options.get("http_enrichment", True)),
        log_level=str(options.get("log_level") or "info"),
        update_check=bool(options.get("update_check", True)),
        temperature_filter=bool(options.get("temperature_filter", True)),
    )


def _broker_from_options(options: dict[str, Any]) -> dict[str, Any] | None:
    host = str(options.get("mqtt_host") or "").strip()
    if not host:
        return None
    log.info("using the MQTT broker from the add-on options (%s)", host)
    return {
        "host": host,
        "port": int(options.get("mqtt_port") or 1883),
        "username": str(options.get("mqtt_username") or "") or None,
        "password": str(options.get("mqtt_password") or "") or None,
        "tls": bool(options.get("mqtt_tls", False)),
    }


def _broker_from_supervisor() -> dict[str, Any] | None:
    try:
        mqtt = _supervisor_get("/services/mqtt")
    except (AddonConfigError, urllib.error.URLError, OSError) as err:
        log.info("no MQTT service from the Supervisor (%s)", err)
        return None
    log.info("using the MQTT broker from the Supervisor service (%s)", mqtt.get("host"))
    return {
        "host": str(mqtt["host"]),
        "port": int(mqtt.get("port") or 1883),
        "username": mqtt.get("username") or None,
        "password": mqtt.get("password") or None,
        "tls": bool(mqtt.get("ssl")),
    }


def _supervisor_get(path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        SUPERVISOR_URL + path,
        headers={"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as err:
        raise AddonConfigError(f"Supervisor request {path} failed: {err}") from err
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise AddonConfigError(f"unexpected Supervisor response for {path}")
    return data


def _read_options() -> dict[str, Any]:
    try:
        data = json.loads(OPTIONS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
