import json
from pathlib import Path

import pytest

from dingz_ha_bridge import __main__ as cli
from dingz_ha_bridge import addon


@pytest.fixture
def supervisor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    options = tmp_path / "options.json"
    options.write_text(
        json.dumps({"id_prefix": "dingztest", "name_prefix": "TEST ", "http_enrichment": False})
    )
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr(addon, "OPTIONS_FILE", options)
    monkeypatch.setattr(
        addon,
        "_supervisor_get",
        lambda path: {
            "host": "core-mosquitto",
            "port": 8883,
            "username": "addons",
            "password": "pw",
            "ssl": True,
        },
    )
    return options


def test_load_settings(supervisor: Path) -> None:
    assert addon.is_addon()
    settings = addon.load_settings()
    assert (settings.mqtt_host, settings.mqtt_username) == ("core-mosquitto", "addons")
    assert (settings.id_prefix, settings.name_prefix) == ("dingztest", "TEST ")
    assert settings.http_enrichment is False
    assert (settings.mqtt_tls, settings.mqtt_port, settings.mqtt_tls_insecure) == (
        True,
        8883,
        False,
    )


def test_missing_options_use_defaults(supervisor: Path) -> None:
    supervisor.unlink()
    settings = addon.load_settings()
    assert (settings.id_prefix, settings.http_enrichment) == ("dingz", True)


def test_cli_applies_addon_settings(supervisor: Path) -> None:
    args = cli.build_parser().parse_args(["run"])
    cli._apply_addon_settings(args)
    assert (args.host, args.password, args.id_prefix, args.no_http) == (
        "core-mosquitto",
        "pw",
        "dingztest",
        True,
    )
    assert (args.ui, args.ui_bind, args.ingress_only) == (True, "0.0.0.0", True)
    web_config = cli._web_config(cli.build_parser(), args)
    assert web_config.ingress_only


def test_external_broker_from_options(supervisor: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor.write_text(
        json.dumps(
            {
                "mqtt_host": "10.0.10.11",
                "mqtt_port": 8883,
                "mqtt_username": "bridge",
                "mqtt_password": "secret",
                "mqtt_tls": True,
                "mqtt_ca_file": "/ssl/mqtt-ca.pem",
            }
        )
    )

    def no_supervisor(path: str) -> dict:
        raise AssertionError("Supervisor must not be asked when mqtt_host is set")

    monkeypatch.setattr(addon, "_supervisor_get", no_supervisor)
    settings = addon.load_settings()
    assert (settings.mqtt_host, settings.mqtt_port, settings.mqtt_tls) == ("10.0.10.11", 8883, True)
    assert (settings.mqtt_username, settings.mqtt_password) == ("bridge", "secret")
    assert settings.mqtt_ca_file == "/ssl/mqtt-ca.pem"


def test_empty_mqtt_host_uses_supervisor(supervisor: Path) -> None:
    supervisor.write_text(json.dumps({"mqtt_host": "  ", "mqtt_port": 1883}))
    assert addon.load_settings().mqtt_host == "core-mosquitto"


def test_no_broker_gives_clear_error(supervisor: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_request(path: str) -> dict:
        raise addon.AddonConfigError(f"Supervisor request {path} failed: HTTP Error 400")

    monkeypatch.setattr(addon, "_supervisor_get", bad_request)
    with pytest.raises(addon.AddonConfigError, match="mqtt_host"):
        addon.load_settings()
    with pytest.raises(SystemExit, match="mqtt_host"):
        cli.main(["run"])
