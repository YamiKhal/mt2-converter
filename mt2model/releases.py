import re
from dataclasses import dataclass

REPOSITORY = "YamiKhal/mt2-converter"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ASSET_PATTERN = re.compile(r"^mt2_tools-[\d.]+\.zip$")


@dataclass(frozen=True)
class Release:
    version: str
    page: str
    download: str
    notes: str


def version_numbers(text: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())

    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def newer_release(latest: dict, current: str) -> Release | None:
    found = version_numbers(latest.get("tag_name", ""))
    installed = version_numbers(current)
    if found is None or installed is None or found <= installed:
        return None
    asset = next((a for a in latest.get("assets", []) if ASSET_PATTERN.match(a.get("name", ""))), None)

    return Release(
        version=".".join(str(part) for part in found),
        page=latest.get("html_url", f"https://github.com/{REPOSITORY}/releases"),
        download=asset["browser_download_url"] if asset else "",
        notes=(latest.get("body") or "").strip(),
    )
