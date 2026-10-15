import ssl
from pathlib import Path

import pytest

from dingz_ha_bridge import __main__ as cli
from dingz_ha_bridge.bridge import MqttConfig


def test_default_ports() -> None:
    assert MqttConfig("b").effective_port == 1883
    assert MqttConfig("b", tls=True).effective_port == 8883
    assert MqttConfig("b", 8884, tls=True).effective_port == 8884
    assert MqttConfig("b", tls=True).describe() == "mqtts://b:8883"


def test_tls_context() -> None:
    assert MqttConfig("b").tls_context() is None
    ctx = MqttConfig("b", tls=True).tls_context()
    assert ctx is not None
    assert (ctx.check_hostname, ctx.verify_mode) == (True, ssl.CERT_REQUIRED)
    insecure = MqttConfig("b", tls=True, tls_insecure=True).tls_context()
    assert insecure is not None
    assert (insecure.check_hostname, insecure.verify_mode) == (False, ssl.CERT_NONE)


def test_ca_file_must_be_pem(tmp_path: Path) -> None:
    bad = tmp_path / "ca.pem"
    bad.write_text("not a certificate")
    with pytest.raises(ssl.SSLError):
        MqttConfig("b", tls=True, ca_file=str(bad)).tls_context()


def test_cli_tls_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "DINGZ_MQTT_PORT",
        "DINGZ_MQTT_TLS",
        "DINGZ_MQTT_CA_FILE",
        "DINGZ_MQTT_TLS_INSECURE",
    ):
        monkeypatch.delenv(var, raising=False)
    parser = cli.build_parser()
    mqtt = cli._mqtt_config(parser.parse_args(["run", "--host", "b", "--tls", "--tls-insecure"]))
    assert mqtt is not None
    assert (mqtt.tls, mqtt.tls_insecure, mqtt.effective_port) == (True, True, 8883)
    # A CA file implies TLS; a missing file is rejected.
    ca = tmp_path / "ca.pem"
    ca.write_text("x")
    mqtt = cli._mqtt_config(parser.parse_args(["run", "--host", "b", "--ca-file", str(ca)]))
    assert mqtt is not None and mqtt.tls
    with pytest.raises(SystemExit):
        cli._mqtt_config(parser.parse_args(["run", "--host", "b", "--ca-file", "/nope.pem"]))
    monkeypatch.setenv("DINGZ_MQTT_TLS", "1")
    mqtt = cli._mqtt_config(cli.build_parser().parse_args(["run", "--host", "b"]))
    assert mqtt is not None and mqtt.tls
