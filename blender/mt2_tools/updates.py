import json
import threading
import urllib.error
import urllib.request

import bpy

from . import game
from .mt2model import __version__
from .mt2model.releases import LATEST_URL, Release, newer_release

TIMEOUT = 10
STARTUP_DELAY = 5.0
POLL_INTERVAL = 0.5

_state: dict = {"release": None, "status": "", "thread": None}


def available() -> Release | None:
    return _state["release"]


def status() -> str:
    return _state["status"]


def checking() -> bool:
    thread = _state["thread"]

    return thread is not None and thread.is_alive()


def check():
    if checking() or not bpy.app.online_access:
        return
    _state["status"] = "Checking GitHub…"
    _state["thread"] = threading.Thread(target=_fetch, daemon=True)
    _state["thread"].start()
    bpy.app.timers.register(_wait, first_interval=POLL_INTERVAL)


def register():
    bpy.app.timers.register(_check_on_startup, first_interval=STARTUP_DELAY)


def unregister():
    for timer in (_check_on_startup, _wait):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)


def _check_on_startup():
    if game.preferences().check_updates:
        check()


def _fetch():
    request = urllib.request.Request(LATEST_URL, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": f"mt2-tools/{__version__}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            release = newer_release(json.load(response), __version__)
    except urllib.error.HTTPError as error:
        release = None
        _state["status"] = "No releases yet" if error.code == 404 else f"GitHub answered {error.code}"
    except (urllib.error.URLError, OSError, ValueError):
        release = None
        _state["status"] = "Couldn't reach GitHub"
    else:
        _state["status"] = f"{release.version} is available" if release else f"Up to date ({__version__})"
    _state["release"] = release


def _wait():
    if checking():
        return POLL_INTERVAL
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in ("VIEW_3D", "PREFERENCES"):
                area.tag_redraw()

    return None
