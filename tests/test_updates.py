import pytest

from dingz_ha_bridge import updates


@pytest.mark.parametrize(
    ("latest", "current", "newer"),
    [
        ("0.2.0", "0.1.0", True),
        ("v0.1.1", "0.1.0", True),
        ("0.1", "0.1.0", False),
        ("0.1.0", "0.1.0", False),
        ("0.0.9", "0.1.0", False),
        ("1.10.0", "1.9.3", True),
        ("nightly", "0.1.0", False),
    ],
)
def test_is_newer(latest: str, current: str, newer: bool) -> None:
    assert updates.is_newer(latest, current) is newer


def test_latest_prefers_release_then_highest_tag() -> None:
    release = {"tag_name": "v0.3.0", "html_url": "https://example/rel"}
    assert updates.latest_from_responses(release, None) == ("0.3.0", "https://example/rel")
    tags = [{"name": "v0.2.0"}, {"name": "v0.10.0"}, {"name": "test-tag"}]
    version, url = updates.latest_from_responses(None, tags)
    assert version == "0.10.0"
    assert url.endswith("/releases/tag/v0.10.0")
    assert updates.latest_from_responses(None, []) == (None, None)


async def test_check_reports_private_or_missing_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates, "_get", lambda path: None)
    info = await updates.check("0.1.0")
    assert info.latest is None
    assert info.update_available is False
    assert info.error_code == "not_public"


async def test_check_finds_update(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        updates, "_get", lambda path: {"tag_name": "v0.2.0", "html_url": "https://example/rel"}
    )
    info = await updates.check("0.1.0")
    assert (info.latest, info.update_available, info.url) == ("0.2.0", True, "https://example/rel")


async def test_check_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: str) -> None:
        raise OSError("offline")

    monkeypatch.setattr(updates, "_get", boom)
    info = await updates.check("0.1.0")
    assert info.error_code == "unreachable"
    assert info.error is not None and "offline" in info.error
