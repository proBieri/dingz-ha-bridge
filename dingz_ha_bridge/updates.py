"""Check GitHub for a newer release (falls back to tags). Standard library only."""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from . import GITHUB_REPO, REPO_URL, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}"
TIMEOUT = 10.0


@dataclass
class UpdateInfo:
    current: str
    latest: str | None = None
    update_available: bool = False
    url: str = REPO_URL
    checked_at: float | None = None
    # Machine-readable reason why there is no result; the UI translates it.
    error_code: str | None = None  # disabled / unreachable / not_public / no_release
    error: str | None = None


def parse_version(text: str) -> tuple[int, ...] | None:
    """``v1.2.3`` / ``1.2`` -> ``(1, 2, 3)`` / ``(1, 2)``; None if not a plain version."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(p) for p in match.group(1).split(".")) if match else None


def is_newer(latest: str, current: str) -> bool:
    new, cur = parse_version(latest), parse_version(current)
    if new is None or cur is None:
        return False
    width = max(len(new), len(cur))
    return new + (0,) * (width - len(new)) > cur + (0,) * (width - len(cur))


def latest_from_responses(release: Any, tags: Any) -> tuple[str | None, str | None]:
    """Pick (version, url) from a releases/latest response or, failing that, the tag list."""
    if isinstance(release, dict) and release.get("tag_name"):
        return str(release["tag_name"]).lstrip("v"), release.get("html_url")
    if isinstance(tags, list):
        versions = [
            str(t["name"])
            for t in tags
            if isinstance(t, dict) and parse_version(str(t.get("name")))
        ]
        if versions:
            best = max(versions, key=lambda v: parse_version(v) or ())
            return best.lstrip("v"), f"{REPO_URL}/releases/tag/{best}"
    return None, None


async def check(current: str = __version__) -> UpdateInfo:
    info = UpdateInfo(current=current, checked_at=time.time())
    try:
        release = await asyncio.to_thread(_get, "/releases/latest")
        tags = None if release else await asyncio.to_thread(_get, "/tags")
    except (OSError, ValueError) as err:
        info.error_code, info.error = "unreachable", f"GitHub not reachable ({err})"
        return info
    if release is None and tags is None:
        info.error_code, info.error = "not_public", "repository not public or not found"
        return info
    latest, url = latest_from_responses(release, tags)
    if latest is None:
        info.error_code, info.error = "no_release", "no release yet"
        return info
    info.latest = latest
    info.update_available = is_newer(latest, current)
    if info.update_available and url:
        info.url = url
    return info


def _get(path: str) -> Any:
    request = urllib.request.Request(
        API_URL + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"dingz-ha-bridge/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise
