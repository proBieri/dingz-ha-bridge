"""Command line entry point: ``python -m dingz_ha_bridge [command] ...``.

Commands: ``run`` (default; the bridge, optionally with web UI), ``scan``, ``status``,
``set-mqtt``, ``ui``. Settings come from CLI arguments, falling back to environment
variables (``DINGZ_*``). In a Home Assistant add-on, ``run`` takes everything from the
Supervisor.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import getpass
import ipaddress
import json
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Sequence

from . import __version__, addon
from .bridge import Bridge, BridgeConfig, MqttConfig
from .discovery import DEFAULT_ID_PREFIX, ID_PREFIX_PATTERN

COMMANDS = ("run", "scan", "status", "set-mqtt", "ui")
DEFAULT_UI_PORT = 8099

log = logging.getLogger("dingz_ha_bridge")


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"DINGZ_{name}", default)


def _flag(name: str) -> bool:
    return (_env(name) or "").lower() in ("1", "true", "yes")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-level", default=_env("LOG_LEVEL", "INFO"))

    broker = argparse.ArgumentParser(add_help=False)
    group = broker.add_argument_group("MQTT broker")
    group.add_argument("--host", default=_env("MQTT_HOST"), help="env DINGZ_MQTT_HOST")
    group.add_argument(
        "--port",
        type=int,
        default=int(_env("MQTT_PORT")) if _env("MQTT_PORT") else None,
        help="env DINGZ_MQTT_PORT (default 1883, with --tls 8883)",
    )
    group.add_argument("--username", default=_env("MQTT_USERNAME"), help="env DINGZ_MQTT_USERNAME")
    group.add_argument("--password", default=_env("MQTT_PASSWORD"), help="env DINGZ_MQTT_PASSWORD")
    group.add_argument(
        "--client-id", default=_env("MQTT_CLIENT_ID"), help="env DINGZ_MQTT_CLIENT_ID"
    )
    group.add_argument(
        "--tls",
        action="store_true",
        default=_flag("MQTT_TLS"),
        help="connect with TLS (env DINGZ_MQTT_TLS=1)",
    )
    group.add_argument(
        "--ca-file",
        default=_env("MQTT_CA_FILE"),
        help="CA certificate (PEM) for TLS (env DINGZ_MQTT_CA_FILE)",
    )
    group.add_argument(
        "--client-cert",
        default=_env("MQTT_CLIENT_CERT"),
        help="client certificate (PEM) (env DINGZ_MQTT_CLIENT_CERT)",
    )
    group.add_argument(
        "--client-key",
        default=_env("MQTT_CLIENT_KEY"),
        help="client key (PEM) (env DINGZ_MQTT_CLIENT_KEY)",
    )
    group.add_argument(
        "--tls-insecure",
        action="store_true",
        default=_flag("MQTT_TLS_INSECURE"),
        help="do not verify the broker certificate - testing only (env DINGZ_MQTT_TLS_INSECURE=1)",
    )

    web = argparse.ArgumentParser(add_help=False)
    group = web.add_argument_group("web UI")
    group.add_argument(
        "--ui-bind",
        default=_env("UI_BIND", "127.0.0.1"),
        help="address to listen on (env DINGZ_UI_BIND, default 127.0.0.1)",
    )
    group.add_argument(
        "--ui-port",
        type=int,
        default=int(_env("UI_PORT") or DEFAULT_UI_PORT),
        help="env DINGZ_UI_PORT",
    )
    group.add_argument(
        "--ui-password",
        default=_env("UI_PASSWORD"),
        help="HTTP basic auth password; required unless bound to localhost (env DINGZ_UI_PASSWORD)",
    )
    group.add_argument(
        "--no-update-check",
        action="store_true",
        default=_env("UPDATE_CHECK", "1") in ("0", "false", "no"),
        help="do not ask GitHub for newer releases (env DINGZ_UPDATE_CHECK=0)",
    )

    parser = argparse.ArgumentParser(
        prog="dingz-ha-bridge",
        description="Expose dingz switches to Home Assistant via MQTT discovery.",
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    run = sub.add_parser("run", parents=[common, broker, web], help="run the bridge (default)")
    run.add_argument(
        "--id-prefix",
        default=_env("ID_PREFIX", DEFAULT_ID_PREFIX),
        help="prefix of unique_ids and discovery topics (env DINGZ_ID_PREFIX, default dingz)",
    )
    run.add_argument(
        "--name-prefix",
        default=_env("NAME_PREFIX", ""),
        help="prefix of HA device names, e.g. 'TEST ' (env DINGZ_NAME_PREFIX)",
    )
    run.add_argument(
        "--dry-run", action="store_true", help="log discovery configs instead of publishing them"
    )
    run.add_argument(
        "--no-http",
        action="store_true",
        help="do not read names and output types from the dingz HTTP API",
    )
    run.add_argument(
        "--no-temperature-filter",
        action="store_true",
        default=_env("TEMPERATURE_FILTER", "1") in ("0", "false", "no"),
        help="publish the raw dingz temperature incl. the floored status-dump values "
        "(env DINGZ_TEMPERATURE_FILTER=0)",
    )
    run.add_argument(
        "--ui",
        action="store_true",
        default=_env("UI", "") in ("1", "true", "yes"),
        help="also serve the web UI (env DINGZ_UI=1)",
    )

    scan = sub.add_parser("scan", parents=[common, broker], help="find dingz devices")
    scan.add_argument("--no-mdns", action="store_true", help="skip mDNS")
    scan.add_argument(
        "--subnet", help="also sweep this network via HTTP, e.g. 192.168.1.0/24 (max /20)"
    )
    scan.add_argument("--timeout", type=float, default=3.0)
    scan.add_argument("--json", action="store_true", help="print JSON")

    status = sub.add_parser("status", parents=[common], help="show one device")
    status.add_argument("device", help="IP or host name of the dingz")
    status.add_argument("--json", action="store_true", help="print JSON")
    status.add_argument(
        "--wifi", action="store_true", help="also measure the WLAN signal (device scan, ~2 s)"
    )

    set_mqtt = sub.add_parser(
        "set-mqtt",
        parents=[common],
        help="configure the MQTT broker on a dingz",
        description="Write the broker settings to a dingz (POST services_config) and verify "
        "them. Prefer a dedicated broker user for the dingz.",
    )
    set_mqtt.add_argument("device", help="IP or host name of the dingz")
    target = set_mqtt.add_mutually_exclusive_group(required=True)
    target.add_argument("--uri", help="full broker URI, e.g. mqtt://user:pass@192.168.1.10")
    target.add_argument("--broker", help="broker host or IP as seen from the dingz")
    set_mqtt.add_argument("--broker-port", type=int, default=1883)
    set_mqtt.add_argument("--broker-user")
    set_mqtt.add_argument(
        "--broker-password",
        default=_env("BROKER_PASSWORD"),
        help="env DINGZ_BROKER_PASSWORD; prompted if a user is given without password",
    )
    set_mqtt.add_argument("--disable", action="store_true", help="disable MQTT on the device")
    set_mqtt.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")

    sub.add_parser("ui", parents=[common, broker, web], help="serve only the web UI")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list or (
        args_list[0] not in COMMANDS and args_list[0] not in ("-h", "--help", "--version")
    ):
        args_list.insert(0, "run")

    parser = build_parser()
    args = parser.parse_args(args_list)

    if args.command == "run" and addon.is_addon() and not args.host:
        try:
            _apply_addon_settings(args)
        except addon.AddonConfigError as err:
            sys.exit(f"error: {err}")

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    match args.command:
        case "run":
            _run_async(_cmd_run(parser, args))
        case "scan":
            _run_async(_cmd_scan(args))
        case "status":
            _run_async(_cmd_status(args))
        case "set-mqtt":
            sys.exit(_run_async(_cmd_set_mqtt(args)) or 0)
        case "ui":
            _run_async(_cmd_ui(parser, args))


def _apply_addon_settings(args: argparse.Namespace) -> None:
    settings = addon.load_settings()
    args.host, args.port = settings.mqtt_host, settings.mqtt_port
    args.tls, args.tls_insecure = settings.mqtt_tls, settings.mqtt_tls_insecure
    args.ca_file = settings.mqtt_ca_file
    args.username, args.password = settings.mqtt_username, settings.mqtt_password
    args.id_prefix, args.name_prefix = settings.id_prefix, settings.name_prefix
    args.no_http = not settings.http_enrichment
    args.log_level = settings.log_level
    args.no_update_check = not settings.update_check
    args.no_temperature_filter = not settings.temperature_filter
    # UI only through ingress; the peer check in web.py rejects everything else.
    args.ui, args.ui_bind, args.ui_port = True, "0.0.0.0", addon.INGRESS_PORT
    args.ingress_only = True


def _mqtt_config(args: argparse.Namespace) -> MqttConfig | None:
    if not args.host:
        return None
    for name in ("ca_file", "client_cert", "client_key"):
        if (path := getattr(args, name)) and not os.path.isfile(path):
            sys.exit(f"--{name.replace('_', '-')}: file not found: {path}")
    tls = args.tls or bool(args.ca_file or args.client_cert)
    mqtt = MqttConfig(
        args.host,
        args.port,
        args.username,
        args.password,
        tls=tls,
        ca_file=args.ca_file,
        client_cert=args.client_cert,
        client_key=args.client_key,
        tls_insecure=args.tls_insecure,
    )
    if args.client_id:
        mqtt.client_id = args.client_id
    if mqtt.tls_insecure:
        log.warning("TLS certificate verification is disabled (--tls-insecure)")
    return mqtt


def _web_config(parser: argparse.ArgumentParser, args: argparse.Namespace):
    from .web import WebConfig

    ingress_only = getattr(args, "ingress_only", False)
    if not ingress_only and not args.ui_password and not _is_loopback(args.ui_bind):
        parser.error("--ui-password (DINGZ_UI_PASSWORD) is required unless --ui-bind is local")
    return WebConfig(
        bind=args.ui_bind,
        port=args.ui_port,
        password=args.ui_password,
        ingress_only=ingress_only,
        update_check=not args.no_update_check,
    )


async def _cmd_run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    mqtt = _mqtt_config(args)
    if mqtt is None:
        parser.error("MQTT host missing (--host or DINGZ_MQTT_HOST)")
    if not ID_PREFIX_PATTERN.fullmatch(args.id_prefix):
        parser.error("--id-prefix may only contain letters, digits, '_' and '-'")
    config = BridgeConfig(
        mqtt,
        id_prefix=args.id_prefix,
        name_prefix=args.name_prefix,
        dry_run=args.dry_run,
        http_enrichment=not args.no_http,
        temperature_filter=not args.no_temperature_filter,
    )
    bridge = Bridge(config)
    if not args.ui:
        await bridge.run()
        return
    from .web import serve

    web_config = _web_config(parser, args)
    web_config.default_broker = mqtt.host
    await asyncio.gather(bridge.run(), serve(web_config, mqtt=mqtt, bridge=bridge))


async def _cmd_ui(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from .web import serve

    mqtt = _mqtt_config(args)
    web_config = _web_config(parser, args)
    web_config.default_broker = mqtt.host if mqtt else None
    await serve(web_config, mqtt=mqtt)


async def _cmd_scan(args: argparse.Namespace) -> None:
    from .scan import scan

    if args.subnet:
        try:
            ipaddress.ip_network(args.subnet, strict=False)
        except ValueError as err:
            sys.exit(f"invalid --subnet: {err}")
    devices = await scan(
        mdns=not args.no_mdns, mqtt=_mqtt_config(args), subnet=args.subnet, timeout=args.timeout
    )
    if args.json:
        print(json.dumps([d.as_dict() for d in devices], indent=2, ensure_ascii=False))
        return
    if not devices:
        print("no dingz found")
        return
    rows = [
        (
            d.name or "?",
            d.host,
            d.mac or "?",
            d.model or "?",
            d.fw_version or "?",
            d.mqtt_id or "?",
            {True: "online", False: "offline", None: "-"}[d.mqtt_online],
            ",".join(sorted(d.sources)),
        )
        for d in devices
    ]
    _print_table(("NAME", "IP", "MAC", "MODEL", "FW", "MQTT ID", "MQTT", "FOUND VIA"), rows)


async def _cmd_status(args: argparse.Namespace) -> None:
    from .device_api import DeviceApi, DeviceApiError

    api = DeviceApi(args.device, timeout=15)
    status = await api.status()
    fields = dataclasses.asdict(status)
    if args.wifi:
        try:
            fields["wifi"] = dataclasses.asdict(await api.wifi())
        except DeviceApiError as err:
            fields["errors"].append(str(err))
    if args.json:
        print(json.dumps(fields, indent=2, ensure_ascii=False))
        return
    if wifi := fields.pop("wifi", None):
        fields["wifi"] = (
            f"{wifi['rssi']} dBm ({wifi['percent']} %, {wifi['quality']}), SSID {wifi['ssid']}"
            if wifi["rssi"] is not None
            else "not found"
        )
    outputs = fields.pop("outputs")
    errors = fields.pop("errors")
    width = max(len(k) for k in fields)
    for key, value in fields.items():
        print(f"{key:<{width}}  {'-' if value is None else value}")
    for output in outputs:
        print(f"{'output':<{width}}  {output}")
    for error in errors:
        print(f"{'error':<{width}}  {error}", file=sys.stderr)


async def _cmd_set_mqtt(args: argparse.Namespace) -> int:
    from .device_api import DeviceApi, build_mqtt_uri, mask_uri

    if args.uri:
        uri = args.uri
    else:
        password = args.broker_password
        if args.broker_user and password is None:
            password = getpass.getpass(f"broker password for {args.broker_user}: ")
        uri = build_mqtt_uri(args.broker, args.broker_port, args.broker_user, password)

    api = DeviceApi(args.device)
    status = await api.status()
    print(f"device:   {status.name or '?'} ({args.device}, MQTT id {status.mqtt_id or '?'})")
    print(f"current:  {status.mqtt_uri or '-'} (enabled: {status.mqtt_enabled})")
    print(f"new:      {mask_uri(uri)} (enabled: {not args.disable})")
    if status.protected:
        print("warning:  device is protected; the write will probably be rejected")
    if not args.yes and input("apply? [y/N] ").strip().lower() not in ("y", "yes"):
        print("aborted")
        return 1
    result = await api.set_mqtt(uri, enable=not args.disable)
    print(("OK: " if result.ok else "FAILED: ") + result.message)
    if result.uri:
        print(f"device now reports: {result.uri}")
    return 0 if result.ok else 2


def _run_async[T](coro: Awaitable[T]) -> T | None:
    async def runner() -> T:
        task = asyncio.current_task()
        assert task is not None
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, task.cancel)
        return await coro

    with contextlib.suppress(KeyboardInterrupt, asyncio.CancelledError):
        return asyncio.run(runner())
    return None


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _print_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())


if __name__ == "__main__":
    main()
