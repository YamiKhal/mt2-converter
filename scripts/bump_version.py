import re
import sys

from build_extension import LIBRARY, SOURCE

FILES = {
    SOURCE / "blender_manifest.toml": r'^(version\s*=\s*")[^"]+(")',
    LIBRARY / "__init__.py": r'^(__version__\s*=\s*")[^"]+(")',
}


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        sys.exit("Usage: python scripts/bump_version.py <major.minor.patch>")
    version = sys.argv[1]
    for path, pattern in FILES.items():
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(pattern, rf"\g<1>{version}\g<2>", text, count=1, flags=re.M), encoding="utf-8")
    print(f"version {version}; add a '## MT2 Tools Patch - {version}' section to CHANGELOG.md")


if __name__ == "__main__":
    main()
