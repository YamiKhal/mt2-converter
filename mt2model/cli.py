import argparse
import os
import sys
from pathlib import Path

from . import detect, gltf, model, murmur
from .assets import ASSET_TYPES, asset_type
from .footprint import building_footprint, scenery_footprint
from .gamedata import GameData
from .materials import MaterialCatalog
from .validate import has_errors, validate


def _game(args) -> GameData:
    game = args.game or os.environ.get("MT2_GAME") or detect.find_game()
    if not game:
        sys.exit("game not found: pass --game <install folder, MMORPG.zip or extracted GameData>")

    return GameData.open(game, args.mod or [])


def cmd_info(args):
    root = model.load(args.file)
    for node, depth in root.walk():
        pad = "  " * depth
        print(f"{pad}{node.name!r} {node.version} t={_round(node.translation)} r={_round(node.rotation)} s={_round(node.scale)}")
        for lod_index, lod in enumerate(node.lods):
            for fragment in lod:
                print(f"{pad}  lod{lod_index} {fragment.material!r} {fragment.format} "
                      f"vertices={len(fragment.vertices)} triangles={len(fragment.indices) // 3}")
    print(f"variant id: {murmur.variant_id(Path(args.file).name)}")


def cmd_check(args):
    data = _game(args)
    rel = args.rel or ""
    findings = validate(model.load(args.file), asset_type(args.asset), MaterialCatalog(data),
                        replaces_vanilla=bool(rel) and data.is_vanilla(rel))
    for f in findings:
        where = f" [{f.node}/{f.material}]" if f.material else ""
        print(f"{f.level:7} {f.message}{where}")
    if not findings:
        print("no problems found")
    sys.exit(1 if has_errors(findings) else 0)


def cmd_footprint(args):
    root = model.load(args.file)
    polygon = building_footprint(root) if args.asset == "building" else scenery_footprint(root)
    if polygon is None:
        print("no footprint")
        return
    for x, z in polygon:
        print(f"{x:.3f} {z:.3f}")


def cmd_list(args):
    for name in _game(args).files(args.prefix, ".vmb"):
        print(name)


def cmd_selftest(args):
    data = _game(args)
    ok = failed = 0
    for rel in data.files("", ".vmb"):
        raw = data.read(rel)
        try:
            root, used = model.read_model_with_size(raw)
            if model.write_model(root) != raw[:used]:
                raise ValueError("written bytes differ")
            ok += 1
        except Exception as error:
            failed += 1
            print(f"FAIL {rel}: {error}")
    print(f"{ok} ok, {failed} failed")
    sys.exit(1 if failed else 0)


def cmd_convert(args):
    root = gltf.convert(Path(args.file), args.height)
    model.save(root, Path(args.out))
    vertices = sum(len(f.vertices) for f in root.fragments)
    print(f"wrote {args.out}: {vertices} vertices, {len(root.fragments)} fragment(s), material Material_tint")
    if args.game or os.environ.get("MT2_GAME") or detect.find_game():
        findings = validate(root, asset_type(args.asset), MaterialCatalog(_game(args)))
        for f in findings:
            print(f"{f.level:7} {f.message}")
        sys.exit(1 if has_errors(findings) else 0)


def cmd_hash(args):
    print(murmur.variant_id(args.name))


def _round(values) -> list[float]:
    return [round(v, 3) for v in values]


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="mt2model", description="MMORPG Tycoon 2 model tools")
    parser.add_argument("--game", help="game install folder, Data/MMORPG.zip or an extracted GameData folder")
    parser.add_argument("--mod", action="append", help="mod source folder to check against (repeatable)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="print a model's nodes and fragments")
    p.add_argument("file")
    p.set_defaults(run=cmd_info)

    p = sub.add_parser("check", help="validate a model for an asset type")
    p.add_argument("file")
    p.add_argument("--asset", choices=sorted(ASSET_TYPES), default="raw")
    p.add_argument("--rel", help="path the model will have in the game, to detect vanilla overrides")
    p.set_defaults(run=cmd_check)

    p = sub.add_parser("footprint", help="print the footprint the game computes")
    p.add_argument("file")
    p.add_argument("--asset", choices=("scenery", "building"), default="scenery")
    p.set_defaults(run=cmd_footprint)

    p = sub.add_parser("list", help="list the game's models")
    p.add_argument("prefix", nargs="?", default="")
    p.set_defaults(run=cmd_list)

    p = sub.add_parser("selftest", help="read and rewrite every game model, compare bytes")
    p.set_defaults(run=cmd_selftest)

    p = sub.add_parser("convert", help="convert a glTF (.glb/.gltf) model into a .vmb with vertex colors")
    p.add_argument("file")
    p.add_argument("out")
    p.add_argument("--height", type=float, help="scale so the model is this tall (a character is about 2)")
    p.add_argument("--asset", choices=sorted(ASSET_TYPES), default="scenery", help="rules to check it against")
    p.set_defaults(run=cmd_convert)

    p = sub.add_parser("hash", help="variant id the game saves for a model file name")
    p.add_argument("name")
    p.set_defaults(run=cmd_hash)

    args = parser.parse_args(argv)
    args.run(args)
