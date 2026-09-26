import json
from datetime import date
from pathlib import Path

MANIFEST = "manifest.json"
EXPORT_LOG = ".mt2export.json"


def read_mod_id(project: Path) -> str | None:
    manifest = project / MANIFEST
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None

    return data.get("id") or data.get("namespace")


def create_manifest(project: Path, mod_id: str, name: str, author: str):
    project.mkdir(parents=True, exist_ok=True)
    manifest = {"id": mod_id, "name": name, "version": "0.1.0", "author": author,
                "description": "Models made with MT2 Tools for Blender."}
    (project / MANIFEST).write_text(json.dumps(manifest, indent=4) + "\n", encoding="utf-8")


def read_log(project: Path) -> dict:
    path = project / EXPORT_LOG
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def record_export(project: Path, rel: str, object_name: str):
    log = read_log(project)
    entry = log.setdefault(rel, {"first_export": date.today().isoformat()})
    entry["object"] = object_name
    entry["last_export"] = date.today().isoformat()
    (project / EXPORT_LOG).write_text(json.dumps(log, indent=4, sort_keys=True) + "\n", encoding="utf-8")


def read_text(project: Path | None, rel: str) -> str:
    path = project / rel if project else None

    return path.read_text(encoding="utf-8") if path and path.is_file() else ""


def write_text(project: Path, rel: str, text: str):
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_bytes(project: Path, rel: str, data: bytes):
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
