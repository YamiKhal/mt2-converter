import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")


def main():
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_extension

    folder = build_extension.assemble()
    archive = build_extension.package(folder)
    sandbox = Path(tempfile.mkdtemp(prefix="mt2_blender_"))
    env = dict(os.environ)
    for name in ("CONFIG", "SCRIPTS", "EXTENSIONS", "DATAFILES"):
        env[f"BLENDER_USER_{name}"] = str(sandbox / name.lower())
    args = sys.argv[1:]
    script = ROOT / "tests_blender" / "suite.py"
    if "--script" in args:
        script = Path(args.pop(args.index("--script") + 1))
        args.remove("--script")
    command = [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1",
               "--python", str(script), "--", str(archive), str(sandbox), *args]
    try:
        code = subprocess.call(command, env=env)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
