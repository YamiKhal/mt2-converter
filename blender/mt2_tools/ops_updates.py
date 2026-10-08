import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import bpy

from . import updates

TIMEOUT = 60
NOTES_LENGTH = 600


def _repository() -> str | None:
    parts = __package__.split(".")

    return parts[1] if len(parts) == 3 and parts[0] == "bl_ext" else None


class MT2_OT_check_updates(bpy.types.Operator):
    bl_idname = "mt2.check_updates"
    bl_label = "Check now"
    bl_description = "Look for a new MT2 Tools release on GitHub"

    @classmethod
    def poll(cls, context):
        if not bpy.app.online_access:
            cls.poll_message_set("Allow online access first: Preferences ▸ System ▸ Network")
            return False

        return not updates.checking()

    def execute(self, context):
        updates.check()

        return {"FINISHED"}


class MT2_OT_install_update(bpy.types.Operator):
    bl_idname = "mt2.install_update"
    bl_label = "Install update"

    @classmethod
    def description(cls, context, properties):
        release = updates.available()
        if release is None:
            return "Download and install the new MT2 Tools release"
        plain = re.sub(r"^#+\s*|\*\*", "", release.notes, flags=re.M)
        notes = plain[:NOTES_LENGTH] + ("…" if len(plain) > NOTES_LENGTH else "")

        return f"Download and install MT2 Tools {release.version}" + (f"\n\n{notes}" if notes else "")

    @classmethod
    def poll(cls, context):
        release = updates.available()

        return release is not None and bool(release.download) and bpy.app.online_access

    def execute(self, context):
        release = updates.available()
        repository = _repository()
        if repository is None:
            bpy.ops.wm.url_open(url=release.page)
            return {"FINISHED"}
        archive = Path(tempfile.mkdtemp(prefix="mt2_tools_")) / f"mt2_tools-{release.version}.zip"
        try:
            with urllib.request.urlopen(release.download, timeout=TIMEOUT) as response:
                archive.write_bytes(response.read())
        except (urllib.error.URLError, OSError):
            self.report({"ERROR"}, "Couldn't download the update; try again or use the release page")
            return {"CANCELLED"}
        bpy.app.timers.register(lambda: _install(str(archive), repository, release.version), first_interval=0.1)

        return {"FINISHED"}


def _install(archive: str, repository: str, version: str):
    window = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=window):
        bpy.ops.extensions.package_install_files(filepath=archive, repo=repository, enable_on_install=True)
    print(f"MT2 Tools {version} installed")


CLASSES = (MT2_OT_check_updates, MT2_OT_install_update)
