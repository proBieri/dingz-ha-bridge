import pytest

from dingz_ha_bridge import __main__ as cli


def parse(*argv: str):
    args = list(argv)
    if not args or (args[0] not in cli.COMMANDS and args[0] not in ("-h", "--help", "--version")):
        args.insert(0, "run")
    return cli.build_parser().parse_args(args)


def test_run_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DINGZ_MQTT_HOST", raising=False)
    args = parse("--host", "b", "--id-prefix", "dingztest", "--name-prefix", "TEST ")
    assert args.command == "run"
    assert (args.host, args.id_prefix, args.name_prefix) == ("b", "dingztest", "TEST ")
    assert args.ui_bind == "127.0.0.1"


def test_env_fallback_and_cli_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DINGZ_MQTT_HOST", "from-env")
    monkeypatch.setenv("DINGZ_MQTT_PORT", "1884")
    assert parse().host == "from-env"
    assert parse().port == 1884
    assert parse("--host", "cli").host == "cli"


def test_subcommands() -> None:
    assert parse("scan", "--subnet", "192.0.2.0/24").subnet == "192.0.2.0/24"
    assert parse("status", "192.0.2.5").device == "192.0.2.5"
    args = parse("set-mqtt", "192.0.2.5", "--broker", "b", "--broker-user", "u", "-y")
    assert (args.broker, args.broker_user, args.yes) == ("b", "u", True)
    with pytest.raises(SystemExit):
        parse("set-mqtt", "192.0.2.5")  # needs --uri or --broker


def test_ui_off_localhost_needs_password() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["ui", "--ui-bind", "0.0.0.0"])
    with pytest.raises(SystemExit):
        cli._web_config(parser, args)
    args = parser.parse_args(["ui", "--ui-bind", "0.0.0.0", "--ui-password", "x"])
    assert cli._web_config(parser, args).password == "x"
    args = parser.parse_args(["ui"])
    assert cli._web_config(parser, args).bind == "127.0.0.1"
