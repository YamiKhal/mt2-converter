import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import build_extension

ROOT = build_extension.ROOT
CHANGELOG = ROOT / "CHANGELOG.md"


def notes_for(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(rf"^## [^\n]*?\b{re.escape(version)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match is None or not match.group(1).strip():
        sys.exit(f"CHANGELOG.md has no '## MT2 Tools Patch - {version}' section; write the release notes there first")

    return match.group(1).strip() + "\n"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def main():
    if shutil.which("gh") is None:
        sys.exit("Install the GitHub CLI (https://cli.github.com) and run 'gh auth login' first")
    version = build_extension.version()
    notes = notes_for(version)
    if git("status", "--porcelain"):
        sys.exit("Commit and push your changes first, so the release matches the code on GitHub")
    if git("rev-parse", "HEAD") != git("rev-parse", "@{u}"):
        sys.exit("Push your commits first, so the release matches the code on GitHub")
    archive = build_extension.package(build_extension.assemble())
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as file:
        file.write(notes)
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            f"v{version}",
            str(archive),
            "--title",
            f"MT2 Tools {version}",
            "--notes-file",
            file.name,
            "--target",
            git("rev-parse", "HEAD"),
        ],
        cwd=ROOT,
        check=True,
    )
    Path(file.name).unlink()


if __name__ == "__main__":
    main()
