import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
ARCHIVE, SANDBOX = ARGS[0], Path(ARGS[1])
STEP = 1 if "--all" in ARGS else 10 if "--full" in ARGS else 0
PACKAGE = "bl_ext.user_default.mt2_tools"

bpy.ops.extensions.package_install_files(filepath=ARCHIVE, repo="user_default", enable_on_install=True)


def module(name: str):
    return importlib.import_module(f"{PACKAGE}.{name}")


pipeline = module("pipeline")
game = module("game")
model = module("mt2model.model")
formats = module("mt2model.formats")
detect = module("mt2model.detect")
records = module("mt2model.records")
obstruction = module("mt2model.obstruction")
pads = module("mt2model.pads")
costume_files = module("mt2model.costume_files")
animations = module("mt2model.animations")
dungeons = module("mt2model.dungeons")
gltf = module("mt2model.gltf")
offered_vehicles = module("mt2model.vehicle_tool").offered_vehicles

GAME = detect.find_game()
PROJECT = Path(tempfile.mkdtemp(prefix="mt2_project_", dir=SANDBOX))

SAMPLES = (
    "scenery/tree/p_ext_tree_01.vmb",
    "scenery/desert/bones_eldritch_1.vmb",
    "scenery/tagged/f_light_classic_brazier.vmb",
    "weapons/swords/015_sword_basic1.vmb",
    "costumes/knight/head.vmb",
    "costumes/knight/torso.vmb",
    "building_themes/castle2/sides/b_w_castle2_blank.vmb",
    "wall_themes/castle/wall_castle.vmb",
    "buildings/tavern/base.vmb",
    "buildings/inn/base.vmb",
    "gizmo/door/base1.vmb",
    "dungeon/themes/arid/walls/N/d_arid_N.vmb",
    "skeletons/humanoid.vmb",
)

NORMAL_OUTLIERS = 0.005
TOLERANCE = {"position": 2e-3, "color": 2.5 / 255, "normal": 1e-2, "uv": 2e-3}


def reset_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    bpy.context.scene.mt2.findings.clear()


def parts(fragment, index):
    lay = formats.layout(fragment.format)
    v = fragment.vertices[index]
    out = {"position": v[:3]}
    if lay.color is not None:
        out["color"] = v[lay.color:lay.color + 4]
    if lay.normal is not None:
        n = v[lay.normal:lay.normal + 3]
        length = sum(x * x for x in n) ** 0.5 or 1.0
        out["normal"] = tuple(x / length for x in n)
    if lay.texel is not None:
        out["uv"] = v[lay.texel:lay.texel + 2]

    return out


def triangles(root):
    for node, depth in root.walk():
        points = [v[:3] for f in node.fragments for v in f.vertices]
        span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3)) if points else 1.0
        span = span or 1.0
        for fragment in node.fragments:
            for k in range(0, len(fragment.indices) // 3 * 3, 3):
                ids = fragment.indices[k:k + 3]
                if len(set(ids)) == 3 and area(*(fragment.vertices[i][:3] for i in ids)) > 1e-9 * span * span:
                    corners = [parts(fragment, i) for i in ids]
                    for corner in corners:
                        corner["position"] = tuple(x / span for x in corner["position"])
                    yield node.name, depth, fragment.material, corners


def area(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    w = [c[i] - a[i] for i in range(3)]
    cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])

    return sum(x * x for x in cross) ** 0.5


def canonical(tri):
    keys = [tuple(round(x, 2) for x in c["position"]) for c in tri]
    start = min(range(3), key=keys.__getitem__)

    return tuple(keys[start:] + keys[:start]), tri[start:] + tri[:start]


def assert_same_geometry(case, original, exported, compare_uv: bool):
    pool = {}
    for name, depth, material, tri in triangles(exported):
        key, ordered = canonical(tri)
        pool.setdefault((depth, material, key), []).append(ordered)
    missing = total = normal_outliers = 0
    worst = {k: 0.0 for k in TOLERANCE}
    for name, depth, material, tri in triangles(original):
        key, ordered = canonical(tri)
        candidates = pool.get((depth, material, key))
        if not candidates:
            missing += 1
            continue

        def error(candidate):
            result = {}
            for kind in TOLERANCE:
                if kind == "uv" and not compare_uv:
                    continue
                if material == "light" and kind != "position":
                    continue
                if all(kind in c for c in ordered) and all(kind in c for c in candidate):
                    result[kind] = max(abs(a - b) for x, y in zip(ordered, candidate) for a, b in zip(x[kind], y[kind]))

            return result

        best = min(candidates, key=lambda c: sum(error(c).values()))
        candidates.remove(best)
        total += 1
        for kind, value in error(best).items():
            if kind == "normal" and value > TOLERANCE[kind]:
                normal_outliers += 1
            else:
                worst[kind] = max(worst[kind], value)
    case.assertEqual(missing, 0, f"{missing} triangles missing or moved")
    for kind, value in worst.items():
        case.assertLessEqual(value, TOLERANCE[kind], f"{kind} differs by {value}")
    case.assertLessEqual(normal_outliers, max(2, total * NORMAL_OUTLIERS), f"{normal_outliers} of {total} triangles have normals off")


def run(operator, **properties):
    try:
        return operator(**properties)
    except RuntimeError:
        return {"CANCELLED"}


def import_game(rel):
    bpy.ops.mt2.import_game(model=rel)

    return bpy.context.view_layer.objects.active


def select_only(obj):
    for other in bpy.context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def add_cube(name, size=2.0, location=(0, 0, 1)):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    obj = bpy.context.active_object
    obj.name = name

    return obj


def select_faces(obj, indices):
    select_only(obj)
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for index in indices:
        obj.data.polygons[index].select = True
    obj.data.polygons.active = indices[0]
    bpy.ops.object.mode_set(mode="EDIT")


def selected_faces(obj):
    bpy.ops.object.mode_set(mode="OBJECT")
    chosen = [p.index for p in obj.data.polygons if p.select]
    bpy.ops.object.mode_set(mode="EDIT")

    return chosen


def textured_material():
    image = bpy.data.images.new("tex", 4, 4)
    image.pixels = [0.0, 1.0, 0.0, 1.0] * 16
    material = bpy.data.materials.new("textured")
    if material.node_tree is None:
        material.use_nodes = True
    nodes = material.node_tree.nodes
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    material.node_tree.links.new(texture.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])

    return material


def game_material(obj, name):
    select_only(obj)
    bpy.ops.mt2.setup_material(name=name)


class Setup(unittest.TestCase):
    def test_extension_installed_and_paths_set(self):
        self.assertIsNotNone(GAME, "game install not found")
        self.assertIn(PACKAGE, bpy.context.preferences.addons)
        self.assertIsNotNone(game.game_data())


class RoundTrip(unittest.TestCase):
    def setUp(self):
        reset_scene()
        bpy.context.scene.mt2.mod_id = "roundtrip"

    def check_round_trip(self, rel):
        data = game.game_data()
        original = model.read_model(data.read(rel))
        obj = import_game(rel)
        plan = pipeline.plan(obj)
        self.assertIsNotNone(plan.built, [f.message for f in plan.findings])
        compare_uv = any("costume" in f.material or "dungeon" in f.material for n, _ in original.walk() for f in n.fragments)
        assert_same_geometry(self, original, plan.built.root, compare_uv)
        self.assertEqual(sum(1 for _ in original.walk()), sum(1 for _ in plan.built.root.walk()))

    def test_samples(self):
        for rel in SAMPLES:
            with self.subTest(rel=rel):
                reset_scene()
                self.check_round_trip(rel)

    def test_game_models(self):
        if not STEP:
            self.skipTest("pass --full (every 10th game model) or --all")
        for rel in game.game_data().files("", ".vmb")[::STEP]:
            with self.subTest(rel=rel):
                reset_scene()
                self.check_round_trip(rel)

    def test_clearing_custom_normals_wins_over_original_normals(self):
        obj = import_game("costumes/knight/head.vmb")
        select_only(obj)
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
        bpy.ops.object.shade_flat()
        fragment = pipeline.plan(obj).built.root.fragments[0]
        for k in range(0, len(fragment.indices), 3):
            a, b, c = (fragment.vertices[i] for i in fragment.indices[k:k + 3])
            u = [b[i] - a[i] for i in range(3)]
            w = [c[i] - a[i] for i in range(3)]
            face = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            length = sum(x * x for x in face) ** 0.5
            normal = a[3:6]
            self.assertLess(sum(x / length * n for x, n in zip(face, normal)), -0.999)

    def test_obstruction_and_light_are_imported_as_helpers(self):
        obj = import_game("scenery/desert/bones_eldritch_1.vmb")
        roles = sorted(child.mt2.role for child in obj.children)
        self.assertIn("OBSTRUCTION", roles)
        plan = pipeline.plan(obj)
        original = obstruction.read_obstruction(game.game_data().read("scenery/desert/bones_eldritch_1_obs.vrt").decode())
        self.assertEqual(len(plan.built.obstruction), len(original))
        for a, b in zip(plan.built.obstruction, original):
            for p, q in zip(a, b):
                self.assertAlmostEqual(p[0], q[0], places=4)
                self.assertAlmostEqual(p[1], q[1], places=4)
        brazier = import_game("scenery/tagged/f_light_classic_brazier.vmb")
        self.assertIn("LIGHT", [c.mt2.role for c in brazier.children])
        original = model.read_model(game.game_data().read("scenery/tagged/f_light_classic_brazier.vmb"))
        exported = pipeline.plan(brazier).built.root
        colors = [next(f for f in root.fragments if f.material == "light").vertices[0][3:7] for root in (original, exported)]
        for a, b in zip(*colors):
            self.assertAlmostEqual(a, b, places=4)


class NewModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bpy.context.scene.mt2.project_dir = str(PROJECT)
        bpy.context.scene.mt2.mod_id = ""
        bpy.ops.mt2.create_project(mod_name="Test Models", author="tests")

    def setUp(self):
        reset_scene()
        for obj in PROJECT.rglob("*.vmb"):
            obj.unlink()

    def test_manifest_created(self):
        manifest = json.loads((PROJECT / "manifest.json").read_text())
        self.assertEqual(manifest["id"], "test_models")
        self.assertEqual(bpy.context.scene.mt2.mod_id, "test_models")

    def test_scenery_export_with_light_and_obstruction(self):
        cube = add_cube("Rock", size=4.0, location=(10, 5, 2))
        game_material(cube, "Material_tint")
        bpy.context.scene.mt2.paint_color = (0.5, 0.25, 1.0, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.mt2.make_asset()
        cube.mt2.scenery_type = "stone"
        bpy.context.scene.cursor.location = (10, 5, 3)
        bpy.ops.mt2.add_light(radius=15.0)
        select_only(cube)
        bpy.ops.mt2.add_obstruction(size=3.0)
        select_only(cube)
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        path = PROJECT / "scenery/stone/test_models_rock.vmb"
        root = model.load(path)
        materials = sorted(f.material for f in root.fragments)
        self.assertEqual(materials, ["Material_tint", "light"])
        tint = next(f for f in root.fragments if f.material == "Material_tint")
        self.assertEqual(tint.format, "PCN")
        ys = [v[1] for v in tint.vertices]
        self.assertAlmostEqual(min(ys), -2.0, places=4)
        self.assertAlmostEqual(max(ys), 2.0, places=4)
        self.assertAlmostEqual(tint.vertices[0][3], 128 / 255, places=3)
        self.assertAlmostEqual(tint.vertices[0][4], 64 / 255, places=3)
        light = next(f for f in root.fragments if f.material == "light")
        corners = [v[:3] for v in light.vertices]
        diagonal = sum((max(c[i] for c in corners) - min(c[i] for c in corners)) ** 2 for i in range(3)) ** 0.5
        self.assertAlmostEqual(diagonal * 0.375, 15.0, places=3)
        centre_y = (max(c[1] for c in corners) + min(c[1] for c in corners)) / 2
        self.assertAlmostEqual(centre_y, 1.0, places=3)
        obs = (PROJECT / "scenery/stone/test_models_rock_obs.vrt").read_text()
        self.assertEqual(len(obstruction.read_obstruction(obs)), 1)
        log = json.loads((PROJECT / ".mt2export.json").read_text())
        self.assertIn("scenery/stone/test_models_rock.vmb", log)

    def test_axes_map_blender_to_game(self):
        mesh = bpy.data.meshes.new("tri")
        mesh.from_pydata([(1, 2, 3), (2, 2, 3), (1, 3, 3)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new("Tri", mesh)
        bpy.context.collection.objects.link(obj)
        select_only(obj)
        game_material(obj, "Material_tint")
        bpy.ops.mt2.make_asset()
        obj.mt2.asset = "raw"
        obj.mt2.raw_path = "scenery/stone/tri.vmb"
        plan = pipeline.plan(obj)
        fragment = plan.built.root.fragments[0]
        positions = [fragment.vertices[i][:3] for i in fragment.indices]
        self.assertEqual([tuple(round(x, 5) for x in p) for p in positions], [(-1, 3, 2), (-1, 3, 3), (-2, 3, 2)])
        normal = fragment.vertices[fragment.indices[0]][7:10]
        self.assertAlmostEqual(normal[1], 1.0, places=4)
        a, b, c = (Vector(p) for p in positions)
        self.assertLess((b - a).cross(c - a).dot(Vector(normal)), 0, "game triangles are clockwise")

    def test_costume_part_palette_and_normalise(self):
        cube = add_cube("Hat", size=2.0, location=(0, 0, 0))
        game_material(cube, "costume")
        bpy.ops.mt2.palette_slot(slot=3)
        bpy.context.scene.mt2.shade = 0.4
        bpy.ops.mt2.shade(gradient=False)
        bpy.ops.mt2.make_asset()
        cube.mt2.asset = "costume_part"
        cube.mt2.costume_set = "test_models_knight"
        cube.mt2.bone = "hat"
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        root = model.load(PROJECT / "costumes/test_models_knight/hat.vmb")
        fragment = root.fragments[0]
        self.assertEqual((fragment.material, fragment.format), ("costume", "PNT"))
        self.assertTrue(all(abs(v[6] - 2.5 / 8) < 1e-6 and abs(v[7] - 0.4) < 1e-6 for v in fragment.vertices))
        extent = max(max(v[i] for v in fragment.vertices) - min(v[i] for v in fragment.vertices) for i in range(3))
        self.assertAlmostEqual(extent, 1.0, places=5)
        self.assertAlmostEqual(cube.mt2.model_scale, 2.0, places=5)

    def test_edit_mode_fill_touches_only_selected_faces(self):
        cube = add_cube("Painted")
        game_material(cube, "Material_tint")
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        cube.data.polygons[0].select = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.context.scene.mt2.paint_color = (1.0, 0.0, 0.0, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.object.mode_set(mode="OBJECT")
        colors = [tuple(round(c, 3) for c in d.color_srgb) for d in cube.data.color_attributes.active_color.data]
        red = sum(1 for c in colors if c == (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(red, cube.data.polygons[0].loop_total)

    def test_select_same_color_and_recent_colors(self):
        cube = add_cube("Two reds")
        game_material(cube, "Material_tint")
        bpy.context.scene.mt2.recent_colors.clear()
        bpy.context.scene.mt2.paint_color = (1.0, 1.0, 1.0, 1.0)
        bpy.ops.mt2.fill_color()
        normals = [tuple(round(x) for x in p.normal) for p in cube.data.polygons]
        opposite = normals.index(tuple(-x for x in normals[0]))
        select_faces(cube, [0, opposite])
        bpy.context.scene.mt2.paint_color = (1.0, 0.0, 0.0, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.mt2.fill_color()
        self.assertEqual([tuple(round(c, 3) for c in e.color) for e in bpy.context.scene.mt2.recent_colors],
                         [(1.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0)])
        select_faces(cube, [0])
        bpy.context.scene.mt2.paint_color = (0.0, 0.0, 1.0, 1.0)
        bpy.ops.mt2.pick_color()
        self.assertEqual(tuple(round(c, 3) for c in bpy.context.scene.mt2.paint_color), (1.0, 0.0, 0.0, 1.0))
        bpy.context.scene.mt2.select_connected = True
        bpy.ops.mt2.select_color()
        self.assertEqual(selected_faces(cube), [0])
        bpy.context.scene.mt2.select_connected = False
        bpy.ops.mt2.select_color()
        self.assertEqual(selected_faces(cube), sorted([0, opposite]))
        select_faces(cube, [1 if opposite != 1 else 2])
        bpy.context.scene.mt2.select_connected = True
        bpy.ops.mt2.select_color()
        self.assertEqual(len(selected_faces(cube)), 4)
        bpy.ops.object.mode_set(mode="OBJECT")

    def test_missing_material_blocks_export(self):
        cube = add_cube("Broken")
        material = bpy.data.materials.new("Broken")
        material.mt2.game_name = "NotAMaterial"
        cube.data.materials.append(material)
        select_only(cube)
        bpy.ops.mt2.make_asset()
        self.assertEqual(run(bpy.ops.mt2.export), {"CANCELLED"})
        self.assertTrue(any("closes" in f.message for f in bpy.context.scene.mt2.findings))

    def test_rename_after_export_is_blocked(self):
        cube = add_cube("Stable", size=4.0, location=(0, 0, 2))
        game_material(cube, "Material_tint")
        bpy.ops.mt2.make_asset()
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"})
        cube.mt2.name = "renamed"
        self.assertEqual(run(bpy.ops.mt2.export), {"CANCELLED"})
        cube.mt2.exported_path = ""
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"})

    def test_building_variant_is_derived(self):
        obj = import_game("buildings/tavern/base.vmb")
        obj.mt2.name = "blue"
        obj.mt2.display_name = "Blue Tavern"
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        variant = records.parse((PROJECT / "buildings/tavern/test_models_blue.variant").read_text())[0]
        self.assertEqual(variant.prop("name"), "test_models_blue")
        self.assertEqual(variant.prop("modelFile"), "buildings/tavern/test_models_blue.vmb")
        self.assertIsNotNone(variant.child("pad"))
        strings = (PROJECT / "i18n/english/test_models_models.vrt").read_text()
        self.assertIn('building_variant_tavern_test_models_blue_displayname "Blue Tavern"', strings)

    def test_weapon_path_and_footprint_preview(self):
        sword = add_cube("Blade", size=0.2, location=(0, 0, 0.5))
        game_material(sword, "Material_tint")
        bpy.ops.mt2.make_asset()
        sword.mt2.asset = "weapon"
        sword.mt2.weapon_category = "swords"
        sword.mt2.item_level = 45
        self.assertEqual(pipeline.plan(sword).rel, "weapons/swords/045_test_models_blade.vmb")
        tower = add_cube("Tower", size=6.0, location=(0, 0, 3))
        game_material(tower, "Material_tint")
        bpy.ops.mt2.make_asset()
        bpy.ops.mt2.footprint_preview()
        self.assertTrue(any(c.mt2.role == "PREVIEW" for c in tower.children))
        self.assertTrue(pipeline.plan(tower).ok)

    def test_new_weapon_category_gets_a_name(self):
        blade = add_cube("Blade", size=0.2, location=(0, 0, 0.5))
        game_material(blade, "Material_tint")
        bpy.ops.mt2.make_asset()
        blade.mt2.asset = "weapon"
        blade.mt2.weapon_category = "test_blades"
        self.assertTrue(any("<<weapon_category_test_blades>>" in f.message for f in pipeline.plan(blade).findings))
        blade.mt2.display_name = "Test Blades"
        plan = pipeline.plan(blade)
        self.assertIn('weapon_category_test_blades "Test Blades"', plan.texts["i18n/english/test_models_models.vrt"])

    def test_two_assets_cannot_share_a_path(self):
        for name in ("Twin", "Twin.001"):
            twin = add_cube(name, size=3.0)
            game_material(twin, "Material_tint")
            bpy.ops.mt2.make_asset()
            twin.mt2.name = "twin"
        messages = [f.message for f in pipeline.plan(twin).findings if f.level == "error"]
        self.assertTrue(any("also exports to" in m for m in messages), messages)

    def test_picking_a_game_material_leaves_other_objects_alone(self):
        first, second = add_cube("First", location=(0, 0, 1)), add_cube("Second", location=(5, 0, 1))
        for cube in (first, second):
            game_material(cube, "Material_tint")
        select_only(first)
        bpy.ops.mt2.pick_game_material(slot=0, name="emissive")
        self.assertEqual(first.material_slots[0].material.mt2.game_name, "emissive")
        self.assertEqual(second.material_slots[0].material.mt2.game_name, "Material_tint")

    def test_new_textured_material(self):
        cube = add_cube("Crate", size=3.0)
        select_only(cube)
        checker = Path(__file__).resolve().parent.parent / "examples" / "checker.png"
        self.assertEqual(run(bpy.ops.mt2.new_textured_material, filepath=str(checker), material_name="crate"),
                         {"FINISHED"})
        self.assertTrue((PROJECT / "textures/test_models_crate.png").is_file())
        mat = (PROJECT / "materials/test_models_crate.mat").read_text()
        self.assertLess(mat.index("texture"), mat.index("shader"))
        self.assertEqual(cube.material_slots[0].material.mt2.game_name, "test_models_crate")
        self.assertIsNotNone(cube.data.color_attributes.active_color, "no colors would preview black")
        bpy.ops.mt2.make_asset()
        cube.mt2.name = "crate"
        plan = pipeline.plan(cube)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual(plan.built.root.fragments[0].format, "PCNT")
        texture = PROJECT / "textures/test_models_crate.png"
        texture.rename(texture.with_name("moved.png"))
        run(bpy.ops.mt2.check)
        self.assertTrue(any("isn't in the game" in f.message for f in bpy.context.scene.mt2.findings))
        texture.with_name("moved.png").rename(texture)
        self.assertEqual(run(bpy.ops.mt2.new_textured_material, filepath=str(checker), material_name="crate"),
                         {"CANCELLED"})

    def test_edit_mode_without_selection_changes_nothing(self):
        cube = add_cube("Untouched")
        game_material(cube, "Material_tint")
        bpy.context.scene.mt2.paint_color = (1.0, 1.0, 1.0, 1.0)
        bpy.ops.mt2.fill_color()
        select_faces(cube, [0])
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.context.scene.mt2.paint_color = (1.0, 0.0, 0.0, 1.0)
        self.assertEqual(run(bpy.ops.mt2.fill_color), {"CANCELLED"})
        bpy.ops.object.mode_set(mode="OBJECT")
        colors = {tuple(round(c, 3) for c in d.color_srgb) for d in cube.data.color_attributes.active_color.data}
        self.assertEqual(colors, {(1.0, 1.0, 1.0, 1.0)})

    def test_imported_pads_export_unchanged(self):
        tavern = import_game("buildings/tavern/base.vmb")
        original = pads.read_pads(records.parse(game.game_data().read("buildings/tavern/base.variant"))[0])
        self.assertEqual(len([c for c in tavern.children if c.mt2.role == "PAD"]), len(original))
        tavern.mt2.name = "padded"
        plan = pipeline.plan(tavern)
        written = pads.read_pads(records.parse(plan.texts["buildings/tavern/test_models_padded.variant"])[0])
        self.assertEqual([p.name for p in written], [p.name for p in original])
        for new, old in zip(written, original):
            for a, b in zip(new.corners + [pt for e in new.entrances for pt in e.points],
                            old.corners + [pt for e in old.entrances for pt in e.points]):
                self.assertTrue(all(abs(x - y) < 1e-4 for x, y in zip(a, b)), (a, b))

    def test_add_pad_and_entrance(self):
        hut = add_cube("Hut", size=6.0, location=(0, 0, 3))
        game_material(hut, "Material_tint")
        bpy.ops.mt2.make_asset()
        hut.mt2.asset = "building"
        hut.mt2.building_dir = "buildings/tavern"
        hut.mt2.name = "hut"
        bpy.context.scene.cursor.location = (0, -2, 0)
        self.assertEqual(bpy.ops.mt2.add_pad(), {"FINISHED"})
        pad = bpy.context.view_layer.objects.active
        self.assertEqual(pad.mt2.role, "PAD")
        self.assertEqual(bpy.ops.mt2.add_entrance(), {"FINISHED"})
        plan = pipeline.plan(hut)
        written = pads.read_pads(records.parse(plan.texts["buildings/tavern/test_models_hut.variant"])[0])
        self.assertEqual(len(written), 1)
        self.assertEqual(len(written[0].corners), 4)
        self.assertEqual(len(written[0].entrances), 2)
        self.assertTrue(all(abs(c[1]) < 1e-6 for c in written[0].corners))
        self.assertAlmostEqual(written[0].entrances[0].points[0][2], -10.0, places=4)
        bpy.context.scene.cursor.location = (0, 0, 0)

    def test_mod_id_is_cleaned_as_typed(self):
        settings = bpy.context.scene.mt2
        settings.mod_id = "My Mod"
        self.assertEqual(settings.mod_id, "my_mod")
        settings.mod_id = "test_models"

    def test_flat_shading_drops_smooth_shading_and_custom_normals(self):
        cube = add_cube("Smooth")
        game_material(cube, "Material_tint")
        bpy.ops.mt2.make_asset()
        bpy.ops.object.shade_smooth()
        cube.data.normals_split_custom_set([(0.0, 0.0, 1.0)] * len(cube.data.loops))
        select_faces(cube, [0])
        self.assertEqual(bpy.ops.mt2.flat_shading(), {"FINISHED"})
        bpy.ops.object.mode_set(mode="OBJECT")
        self.assertEqual([p.use_smooth for p in cube.data.polygons], [False] + [True] * 5)
        self.assertTrue(cube.data.has_custom_normals)
        face = cube.data.polygons[0]
        for corner in face.loop_indices:
            self.assertAlmostEqual(cube.data.corner_normals[corner].vector.dot(face.normal), 1.0, places=4)
        self.assertAlmostEqual(cube.data.corner_normals[cube.data.polygons[1].loop_start].vector.z, 1.0, places=4)
        select_only(cube)
        self.assertEqual(bpy.ops.mt2.flat_shading(), {"FINISHED"})
        self.assertFalse(cube.data.has_custom_normals)
        self.assertFalse(any(p.use_smooth for p in cube.data.polygons))

    def test_two_parts_on_one_bone_are_refused(self):
        bpy.ops.mt2.import_costume(costume="costumes/knight.costume")
        root = bpy.context.view_layer.objects.active
        torso = next(o for o in root.children_recursive if o.mt2.role == "BONE" and o.get("mt2_node") == "torso")
        extra = add_cube("Extra", size=0.3)
        extra.parent = torso
        bpy.ops.mt2.make_asset()
        self.assertTrue(any("both on torso" in f.message for f in pipeline.plan(root).findings))

    def test_costume_round_trip(self):
        bpy.ops.mt2.import_costume(costume="costumes/knight.costume")
        root = bpy.context.view_layer.objects.active
        self.assertEqual(root.mt2.asset, "costume")
        self.assertEqual(len(root.mt2.palette), 8)
        original = {p.bone: p for p in costume_files.read_costume(game.game_data().read("costumes/knight.costume")).parts}
        plan = pipeline.plan(root)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual(plan.parts, [])
        written = {p.bone: p for p in costume_files.read_costume(plan.texts["costumes/test_models_knight.costume"]).parts}
        for bone, old in original.items():
            new = written[bone]
            self.assertEqual(new.model_file, old.model_file, bone)
            if old.model_file:
                self.assertAlmostEqual(new.model_scale, old.model_scale, places=4)
                for a, b in zip(new.offset, old.offset):
                    self.assertAlmostEqual(a, b, places=4, msg=bone)
        self.assertIn("mmoCostumeDefaults", plan.texts["costumes/test_models_knight.defaults"])
        parts = [o for o in root.children_recursive if o.mt2.asset == "costume_part"]
        lowest = min((o.matrix_world @ Vector(c)).z for o in parts for c in o.bound_box)
        self.assertAlmostEqual(lowest, 0.0, delta=0.03, msg="bone offsets chain down the skeleton, so feet touch 0")
        root.mt2.display_name = "Red Knight"
        self.assertIn('costume_test_models_knight "Red Knight"', pipeline.plan(root).texts["i18n/english/test_models_models.vrt"])
        torso = next(o for o in parts if o.mt2.bone == "torso")
        torso.location.z -= 0.3
        plan = pipeline.plan(root)
        self.assertEqual([p.rel for p in plan.parts], ["costumes/test_models_knight/torso.vmb"])
        torso.location.z += 0.3
        head = next(o for o in parts if o.mt2.bone == "head")
        head.data.vertices[0].co.x += 0.01
        plan = pipeline.plan(root)
        self.assertEqual([p.rel for p in plan.parts], ["costumes/test_models_knight/head.vmb"])
        written = {p.bone: p for p in costume_files.read_costume(plan.texts["costumes/test_models_knight.costume"]).parts}
        self.assertEqual(written["head"].model_file, "costumes/test_models_knight/head.vmb")
        self.assertAlmostEqual(written["head"].model_scale, original["head"].model_scale, places=2)
        for a, b in zip(written["head"].offset, original["head"].offset):
            self.assertAlmostEqual(a, b, places=4)
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        self.assertTrue((PROJECT / "costumes/test_models_knight/head.vmb").is_file())
        self.assertTrue((PROJECT / "costumes/test_models_knight.costume").is_file())

    def test_art_pack_follows_exports(self):
        rock = add_cube("Packed", size=3.0)
        game_material(rock, "Material_tint")
        bpy.ops.mt2.make_asset()
        rock.mt2.name = "packed"
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"})
        settings = bpy.context.scene.mt2
        settings.art_pack_name = "Test Pack"
        settings.art_pack = True
        pack = PROJECT / "artpacks/test_models.vrt"
        self.assertIn('"stone/test_models_packed.vmb"', pack.read_text())
        self.assertIn('artpack_test_models_displayname "Test Pack"', (PROJECT / "i18n/english/test_models_models.vrt").read_text())
        settings.art_pack_description = "Rocks for testing"
        self.assertIn('artpack_test_models_description "Rocks for testing"',
                      (PROJECT / "i18n/english/test_models_models.vrt").read_text())
        blade = add_cube("Packed blade", size=0.2)
        game_material(blade, "Material_tint")
        bpy.ops.mt2.make_asset()
        blade.mt2.asset = "weapon"
        blade.mt2.weapon_category = "test_models_packed"
        blade.mt2.name = "packed_blade"
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"})
        weapons = PROJECT / "artpacks/weapons_test_models_packed.vrt"
        self.assertFalse(weapons.exists(), "weapon packs are only made when enabled")
        settings.weapon_packs = True
        self.assertIn('type "weapons"', weapons.read_text())
        self.assertNotIn('"test_models_packed"', pack.read_text())
        settings.art_pack = False
        self.assertFalse(pack.exists())
        self.assertTrue(weapons.exists())
        settings.weapon_packs = False
        self.assertFalse(weapons.exists())

    def test_vehicle_variant(self):
        balloon = import_game("vehicles/air/balloon.vmb")
        self.assertEqual((balloon.mt2.asset, balloon.mt2.vehicle_kind), ("vehicle", "air"))
        balloon.mt2.name = "red_balloon"
        balloon.mt2.display_name = "Red Balloon"
        balloon.mt2.description = "Red and round"
        plan = pipeline.plan(balloon)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        definition = records.parse(plan.texts["vehicles/air/test_models_red_balloon.def"])[0]
        self.assertEqual(definition.prop("modelFile"), "vehicles/air/test_models_red_balloon.vmb")
        deck = pads.read_pads(definition)[0]
        self.assertEqual([e.name for e in deck.entrances], ["port", "starboard"])
        self.assertIn("vehicle_definition_test_models_red_balloon_displayname",
                      plan.texts["i18n/english/test_models_models.vrt"])
        self.assertIn('vehicle_definition_test_models_red_balloon_description "Red and round"',
                      plan.texts["i18n/english/test_models_models.vrt"])
        self.assertEqual(offered_vehicles(plan.texts["CursorBehaviours.txt"]), ["test_models_red_balloon"])

    def test_gizmo_animation_round_trip(self):
        chest = import_game("gizmo/container/chest.vmb")
        self.assertEqual((chest.mt2.asset, chest.mt2.gizmo_dir), ("gizmo", "gizmo/container"))
        original = animations.read_animations(game.game_data().read("gizmo/container/chest.van"))
        chest.mt2.name = "chest2"
        plan = pipeline.plan(chest)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        variant = records.parse(plan.texts["gizmo/container/test_models_chest2.variant"])[0]
        self.assertEqual(variant.prop("animationFile"), "gizmo/container/test_models_chest2")
        written = animations.read_animations(plan.texts["gizmo/container/test_models_chest2.van"])
        self.assertEqual([a.name for a in written], [a.name for a in original])
        self.assertEqual(written[0].playback, original[0].playback)
        for old, new in zip(original[0].timelines, written[0].timelines):
            self.assertEqual(old.node, new.node)
            for channel in ("translation", "rotation", "scale"):
                old_keys, new_keys = getattr(old, channel), getattr(new, channel)
                if len(old_keys) == len(new_keys):
                    for (t1, v1), (t2, v2) in zip(old_keys, new_keys):
                        self.assertAlmostEqual(t1, t2, places=4)
                        sign = 1 if channel != "rotation" or sum(a * b for a, b in zip(v1, v2)) >= 0 else -1
                        for a, b in zip(v1, v2):
                            self.assertAlmostEqual(a, sign * b, delta=1e-3 * max(1.0, abs(a)))

    def test_costume_animations(self):
        bpy.ops.mt2.import_costume(costume="costumes/knight.costume")
        root = bpy.context.view_layer.objects.active
        self.assertEqual(bpy.ops.mt2.import_animations(), {"FINISHED"})
        plan = pipeline.plan(root)
        self.assertNotIn("skeletons/humanoid.van", plan.texts)
        self.assertEqual(bpy.ops.mt2.new_animation(name="wave"), {"FINISHED"})
        self.assertNotIn("skeletons/humanoid.van", pipeline.plan(root).texts)
        head = next(o for o in root.children_recursive if o.mt2.role == "BONE" and o.get("mt2_node") == "head")
        head.keyframe_insert("rotation_quaternion", frame=1)
        head.rotation_quaternion.x = 0.2
        head.keyframe_insert("rotation_quaternion", frame=12)
        written = animations.read_animations(pipeline.plan(root).texts["skeletons/humanoid.van"])
        self.assertEqual([a.name for a in written], ["wave"])
        self.assertEqual([t.node for t in written[0].timelines], ["head"])
        self.assertEqual(len(written[0].timelines[0].rotation), 12)

    def costume(self, rel="costumes/knight.costume"):
        bpy.ops.mt2.import_costume(costume=rel)

        return bpy.context.view_layer.objects.active

    def bone(self, root, name):
        return next(o for o in root.children_recursive if o.mt2.role == "BONE" and o.get("mt2_node") == name)

    def test_new_rig_from_a_costume(self):
        root = self.costume()
        self.assertEqual(root.mt2.rig, "humanoid")
        root.mt2.rig = "biped"
        plan = pipeline.plan(root)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual(costume_files.read_costume(plan.texts["costumes/test_models_knight.costume"]).actor,
                         "test_models_biped")
        skeleton = model.read_model(plan.files["skeletons/test_models_biped.vmb"])
        humanoid = model.read_model(game.game_data().read("skeletons/humanoid.vmb"))
        new = {n.name: (d, n.translation) for n, d in skeleton.walk()}
        old = {n.name: (d, n.translation) for n, d in humanoid.walk()}
        self.assertEqual({k: v[0] for k, v in new.items()}, {k: v[0] for k, v in old.items()})
        for name, (_, translation) in old.items():
            for x, y in zip(new[name][1], translation):
                self.assertAlmostEqual(x, y, places=4, msg=name)
        written = animations.read_animations(plan.texts["skeletons/test_models_biped.van"])
        self.assertEqual(len(written), 48)
        select_only(self.bone(root, "torso"))
        bpy.context.scene.cursor.location = (0.5, 0.0, 1.5)
        self.assertEqual(bpy.ops.mt2.add_bone(name="wingleft"), {"FINISHED"})
        wing = bpy.context.view_layer.objects.active
        self.assertAlmostEqual(wing.matrix_world.translation.x, 0.5, places=4)
        part = add_cube("Wing", size=0.3, location=(0.6, 0.0, 1.5))
        game_material(part, "costume")
        part.parent = wing
        part.matrix_parent_inverse = wing.matrix_world.inverted()
        self.assertTrue(module("costume_objects").is_loose_part(part))
        self.assertTrue(any("Make asset" in f.message for f in pipeline.plan(root).findings))
        bpy.ops.mt2.make_asset()
        self.assertEqual((part.mt2.asset, part.mt2.bone), ("costume_part", "wingleft"))
        plan = pipeline.plan(root)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        names = [n.name for n, _ in model.read_model(plan.files["skeletons/test_models_biped.vmb"]).walk()]
        self.assertIn("wingleft", names)
        parts = {p.bone: p for p in costume_files.read_costume(plan.texts["costumes/test_models_knight.costume"]).parts}
        self.assertEqual(parts["wingleft"].model_file, "costumes/test_models_knight/wingleft.vmb")
        select_only(root)
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        self.assertTrue((PROJECT / "skeletons/test_models_biped.vmb").is_file())
        self.assertTrue((PROJECT / "skeletons/test_models_biped.van").is_file())

    def test_mod_changes_to_a_game_rig_add_to_its_animations(self):
        nod = animations.Animation("idle", "Loop", [animations.Timeline("head", rotation=[(0.0, (0.0, 0.0, 0.0, 1.0))])])
        partial = PROJECT / "skeletons/humanoid.van"
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(animations.write_animations([nod]))
        try:
            root = self.costume()
            self.assertEqual(bpy.ops.mt2.import_animations(), {"FINISHED"})
            self.assertEqual(len([a for a in bpy.data.actions if a.get("mt2_owner") == root]), 48)
            root.mt2.rig = "biped"
            written = animations.read_animations(pipeline.plan(root).texts["skeletons/test_models_biped.van"])
            self.assertEqual(len(written), 48)
            idle = next(a for a in written if a.name == "idle")
            self.assertEqual(([t.node for t in idle.timelines], idle.playback), (["head"], "Loop"))
            root.mt2.rig = "humanoid"
            run_action = next(a for a in bpy.data.actions if a.get("mt2_owner") == root and a.get("mt2_name") == "run")
            run_action["mt2_playback"] = "Once"
            written = animations.read_animations(pipeline.plan(root).texts["skeletons/humanoid.van"])
            self.assertEqual([a.name for a in written], ["idle", "run"])
        finally:
            partial.unlink()

    def test_set_rest_pose_moves_the_animations_along(self):
        root = self.costume()
        root.mt2.rig = "biped"
        before = next(t for t in animations.read_animations(game.game_data().read("skeletons/humanoid.van"))
                      if t.name == "idle")
        head_before = next(t for t in before.timelines if t.node == "head").translation[0][1]
        head = self.bone(root, "head")
        head.location.z += 0.1
        findings = [f.message for f in pipeline.plan(root).findings]
        self.assertTrue(any("Set rest pose" in m for m in findings), findings)
        select_only(head)
        self.assertEqual(bpy.ops.mt2.set_rest_pose(), {"FINISHED"})
        self.assertEqual(len([a for a in bpy.data.actions if a.get("mt2_owner") == root]), 48)
        self.assertEqual(root.mt2.animation, "MT2_REST_POSE")
        self.assertIsNone(head.animation_data.action)
        plan = pipeline.plan(root)
        self.assertFalse(any("Set rest pose" in f.message for f in plan.findings))
        written = next(a for a in animations.read_animations(plan.texts["skeletons/test_models_biped.van"])
                       if a.name == "idle")
        head_after = next(t for t in written.timelines if t.node == "head").translation[0][1]
        self.assertAlmostEqual(head_after[1] - head_before[1], 0.1, places=3)
        skeleton = model.read_model(plan.files["skeletons/test_models_biped.vmb"])
        rest = next(n for n, _ in skeleton.walk() if n.name == "head")
        self.assertAlmostEqual(rest.translation[1], 0.32 + 0.1, delta=0.01)
        idle = next(a for a in bpy.data.actions if a.get("mt2_owner") == root and a.get("mt2_name") == "idle")
        root.mt2.animation = idle.name
        self.assertEqual(head.animation_data.action, idle)

    def test_game_rigs_stay_unless_bones_are_added(self):
        root = self.costume()
        plan = pipeline.plan(root)
        self.assertFalse(plan.files)
        root.mt2.rig = "quadruped"
        self.assertFalse(pipeline.plan(root).ok)
        root.mt2.rig = "humanoid"
        select_only(root)
        self.assertEqual(run(bpy.ops.mt2.set_rest_pose), {"CANCELLED"})
        select_only(self.bone(root, "head"))
        bpy.ops.mt2.add_bone(name="jaw")
        plan = pipeline.plan(root)
        self.assertIn("skeletons/humanoid.vmb", plan.files)
        self.assertTrue(any("every humanoid" in f.message for f in plan.findings))

    def test_creature_type(self):
        root = self.costume()
        root.mt2.creature_type = "monster"
        root.mt2.display_name = "Tin Knight"
        plan = pipeline.plan(root)
        definition = records.parse(plan.texts["default/monsters/test_models_knight.vrt"])[0].child("def")
        self.assertEqual((definition.prop("name"), definition.prop("costumeName")), ("Tin Knight", "test_models_knight"))

    def test_mount_rig_needs_a_torso(self):
        root = self.costume("costumes/raven.costume")
        self.assertEqual(root.mt2.rig, "bird")
        root.mt2.rig = "griffin"
        plan = pipeline.plan(root)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual([a.name for a in animations.read_animations(plan.texts["skeletons/test_models_griffin.van"])],
                         ["flying", "idle"])
        self.assertEqual(plan.parts, [], "a mount in the game's colors can share the game's part files")
        root.mt2.palette[0].color = (1.0, 0.0, 0.0, 1.0)
        plan = pipeline.plan(root)
        parts = [o for o in root.children_recursive if o.mt2.asset == "costume_part"]
        self.assertEqual(sorted(p.rel for p in plan.parts),
                         sorted(f"costumes/test_models_raven/{o.mt2.bone}.vmb" for o in parts))
        placed = costume_files.read_costume(plan.texts["costumes/test_models_raven.costume"]).parts
        self.assertTrue(all(p.model_file.startswith("costumes/test_models_raven/") for p in placed if p.model_file))
        torso = self.bone(root, "torso")
        torso["mt2_node"] = "body"
        self.assertTrue(any("torso" in f.message and f.level == "error" for f in pipeline.plan(root).findings))

    def test_flight_point_creature(self):
        roost = import_game("buildings/flightpoint/owl_roost.vmb")
        self.assertEqual((roost.mt2.creature, roost.mt2.creature_animation), ("owl", "idle"))
        spot = next(c for c in roost.children if c.mt2.role == "CREATURE")
        self.assertAlmostEqual(spot.matrix_world.translation.z, 5.0, places=4)
        roost.mt2.name = "griffin_roost"
        roost.mt2.creature = "griffin"
        spot.location.z += 1.0
        plan = pipeline.plan(roost)
        variant = records.parse(plan.texts["buildings/flightpoint/test_models_griffin_roost.variant"])[0]
        self.assertEqual(variant.prop("actor"), "test_models_griffin")
        self.assertAlmostEqual(variant.child("actorOffset").floats()[1], 6.0, places=4)
        rotation = variant.child("actorRotation").floats()
        self.assertAlmostEqual(abs(rotation[1]), 1.0, places=4)
        self.assertTrue(any("griffin" in f.message for f in plan.findings))

    def action_of(self, root, name):
        return next(a for a in bpy.data.actions if a.get("mt2_owner") == root and a.get("mt2_name") == name)

    def test_renamed_objects_keep_their_animation(self):
        root = self.costume()
        self.assertEqual(bpy.ops.mt2.import_animations(), {"FINISHED"})
        idle = self.action_of(root, "idle")
        head = self.bone(root, "head")
        head.name = "Head in the Outliner"
        root.mt2.animation = idle.name
        self.assertEqual(head.animation_data.action_slot.name_display, "head")
        wave = self.action_of(root, "run")
        legacy = next(s for s in wave.slots if s.name_display == "torso")
        torso = self.bone(root, "torso")
        torso.name = "Torso object"
        legacy.name_display = torso.name
        root.mt2.animation = wave.name
        self.assertEqual(legacy.name_display, "torso", "slots named after the object in older files are renamed")
        head.keyframe_insert("rotation_quaternion", frame=1)
        written = next(a for a in animations.read_animations(pipeline.plan(root).texts["skeletons/humanoid.van"])
                       if a.name == "run")
        self.assertIn("head", [t.node for t in written.timelines])
        self.assertIn("torso", [t.node for t in written.timelines])

    def test_rename_bones_on_an_own_rig(self):
        root = self.costume()
        select_only(self.bone(root, "armright"))
        self.assertEqual(run(bpy.ops.mt2.rename_bone, name="arm_r"), {"CANCELLED"}, "game rigs keep their names")
        root.mt2.rig = "biped"
        for taken in ("head", "hand", ""):
            self.assertEqual(run(bpy.ops.mt2.rename_bone, name=taken), {"CANCELLED"}, taken)
        self.assertEqual(run(bpy.ops.mt2.rename_bone, name="arm_a"), {"FINISHED"})
        arm = self.bone(root, "arm_a")
        self.assertEqual(arm.name, "arm_a")
        other = PROJECT / "costumes/test_models_other.costume"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("\n".join([
            "mmoCostume {",
            '\tname "test_models_other";',
            '\tactorName "test_models_biped";',
            "\tcostumePart {",
            "\t\tmmoCostumePartDescriptor {",
            '\t\t\tboneName "armright"',
            '\t\t\tmodelFilename "costumes/knight/armright.vmb"',
            "\t\t}",
            "\t}",
            "}",
            "",
        ]))
        try:
            plan = pipeline.plan(root)
            self.assertTrue(plan.ok, [f.message for f in plan.findings])
            self.assertTrue(any("'arm_a' was 'armright'" in f.message for f in plan.findings))
            costume = records.parse(plan.texts["costumes/test_models_knight.costume"])[0]
            descriptors = costume.child("costumePart").children_named("mmoCostumePartDescriptor")
            by_bone = {d.prop("boneName"): d for d in descriptors}
            self.assertNotIn("armright", by_bone)
            self.assertIsNotNone(by_bone["arm_a"].child("attachment"), "the hand attachment moves with the bone")
            self.assertEqual(by_bone["arm_a"].prop("modelFilename"), "costumes/knight/armright.vmb")
            written = animations.read_animations(plan.texts["skeletons/test_models_biped.van"])
            nodes = {t.node for a in written for t in a.timelines}
            self.assertIn("arm_a", nodes)
            self.assertNotIn("armright", nodes)
            self.assertEqual(costume_files.read_costume(plan.texts["costumes/test_models_other.costume"]).parts[0].bone,
                             "arm_a")
            self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
            select_only(arm)
            self.assertEqual(run(bpy.ops.mt2.rename_bone, name="arm_b"), {"FINISHED"})
            plan = pipeline.plan(root)
            nodes = {t.node for a in animations.read_animations(plan.texts["skeletons/test_models_biped.van"])
                     for t in a.timelines}
            self.assertIn("arm_b", nodes)
            self.assertFalse(nodes & {"arm_a", "armright"}, "names from earlier exports are renamed too")
            self.assertEqual(run(bpy.ops.mt2.rename_bone, name="armright"), {"FINISHED"})
            plan = pipeline.plan(root)
            self.assertFalse(any("was 'armright'" in f.message for f in plan.findings))
            self.assertEqual(module("rig_objects").bone_renames(root), {"arm_a": "armright", "arm_b": "armright"})
            twin = self.costume()
            twin.mt2.rig = "biped"
            select_only(self.bone(twin, "head"))
            bpy.ops.mt2.rename_bone(name="skull")
            self.assertTrue(any("same rig with other bones" in f.message for f in pipeline.plan(root).findings))
        finally:
            other.unlink()
            for rel in ("skeletons/test_models_biped.van", "skeletons/test_models_biped.vmb",
                        "costumes/test_models_knight.costume"):
                (PROJECT / rel).unlink(missing_ok=True)

    def test_change_a_game_gizmos_animation(self):
        door = import_game("gizmo/door/base1.vmb")
        self.assertEqual(len([a for a in bpy.data.actions if a.get("mt2_owner") == door]), 4)
        door.mt2.edit_game = True
        plan = pipeline.plan(door)
        self.assertFalse(plan.ok)
        self.assertTrue(any("no animation is changed" in f.message for f in plan.findings))
        opening = self.action_of(door, "open")
        door.mt2.animation = opening.name
        bag = module("anim_objects").channelbag(opening, opening.slots[0])
        point = bag.fcurves[0].keyframe_points[-1]
        point.co.y += 0.5
        plan = pipeline.plan(door)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual(list(plan.texts), ["gizmo/door/base1.van"])
        self.assertEqual([a.name for a in animations.read_animations(plan.texts["gizmo/door/base1.van"])], ["open"])
        mesh = next(o for o in door.children_recursive if o.type == "MESH")
        mesh.data.vertices[0].co.x += 0.1
        self.assertTrue(any("model itself" in f.message for f in pipeline.plan(door).findings))
        mesh.data.vertices[0].co.x -= 0.1
        self.assertEqual(bpy.ops.mt2.new_animation(name="wobble"), {"FINISHED"})
        mesh.keyframe_insert("location", frame=1)
        self.assertTrue(any("never plays 'wobble'" in f.message for f in pipeline.plan(door).findings))
        bpy.data.actions.remove(self.action_of(door, "wobble"))
        door.mt2.animation = opening.name
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        self.assertEqual(door.mt2.exported_path, "")
        try:
            game.forget()
            again = import_game("gizmo/door/base1.vmb")
            loaded = [a for a in bpy.data.actions if a.get("mt2_owner") == again]
            self.assertEqual(len(loaded), 4, "the game's animations with the mod's change merged in")
            door.mt2.edit_game = False
            door.mt2.name = "door2"
            plan = pipeline.plan(door)
            self.assertIn("gizmo/door/test_models_door2.variant", plan.texts)
        finally:
            (PROJECT / "gizmo/door/base1.van").unlink(missing_ok=True)

    def test_door_parts_that_jump_between_animations(self):
        for rel in ("gizmo/door/base1.vmb", "gizmo/door/base5.vmb", "gizmo/bossdoor/boss2.vmb"):
            door = import_game(rel)
            door.mt2.name = "calm_" + rel.split("/")[-1][:-4]
            self.assertFalse(any("jumps" in f.message for f in pipeline.plan(door).findings), rel)
        door = import_game("gizmo/door/base1.vmb")
        door.mt2.edit_game = True
        unlock = self.action_of(door, "unlock")
        lock = next(o for o in door.children_recursive if o.get("mt2_node") == "lock1")
        slot = module("anim_objects").find_slot(unlock, "lock1", lock)
        bag = module("anim_objects").channelbag(unlock, slot)
        curve = next(c for c in bag.fcurves if c.data_path == "location" and c.array_index == 2)
        curve.keyframe_points[-1].co.y += 0.05
        messages = [f.message for f in pipeline.plan(door).findings]
        self.assertTrue(any("'lock1' jumps from the end of unlock to the start of open" in m for m in messages), messages)

    def test_bridge_ramp_path_and_obstruction(self):
        bridges = module("mt2model.bridges")
        rel = "bridge_themes/castle.vrt"
        vanilla = bridges.read_bridge(game.game_data().sources[-1].read(rel))
        ramp = import_game("bridge_themes/castle/ramp_castle.vmb")
        path = module("bridge_objects").ramp_path_object(ramp)
        self.assertIsNotNone(path)
        plan = pipeline.plan(ramp)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertIn("__replace", plan.texts[rel])
        written = bridges.read_bridge(plan.texts[rel])
        self.assertEqual(len(written.ramp_path), len(vanilla.ramp_path))
        for old, new in zip(vanilla.ramp_path, written.ramp_path):
            for a, b in zip(old, new):
                self.assertAlmostEqual(a, b, places=3)
        path.data.vertices[len(path.data.vertices) - 1].co.z += 2.0
        written = bridges.read_bridge(pipeline.plan(ramp).texts[rel])
        self.assertAlmostEqual(written.height, vanilla.height + 2.0, places=3)
        path.data.vertices[len(path.data.vertices) - 1].co.y -= 20.0
        self.assertTrue(any("ramp model ends" in f.message for f in pipeline.plan(ramp).findings))
        span = import_game("bridge_themes/castle/bridge_castle.vmb")
        shape = next(c for c in span.children if c.mt2.role == "OBSTRUCTION")
        self.assertEqual(len(shape.data.polygons), len(vanilla.obstruction))
        span.mt2.fully_obstructed = True
        written = bridges.read_bridge(pipeline.plan(span).texts[rel])
        self.assertTrue(written.fully_obstructed)
        self.assertAlmostEqual(written.depth, vanilla.depth, places=3)
        expected = sorted(sorted(polygon) for polygon in vanilla.obstruction)
        for old, new in zip(expected, sorted(sorted(polygon) for polygon in written.obstruction)):
            for a, b in zip(old, new):
                self.assertAlmostEqual(a[0], b[0], places=3)
                self.assertAlmostEqual(a[1], b[1], places=3)
        self.assertEqual(run(bpy.ops.mt2.new_theme, family="bridge", source="rope", name="moat"), {"FINISHED"})
        own = PROJECT / "bridge_themes/test_models_moat/ramp_test_models_moat.vmb"
        bpy.ops.mt2.import_file(filepath=str(own))
        moat = bpy.context.view_layer.objects.active
        bpy.data.objects.remove(module("bridge_objects").ramp_path_object(moat))
        self.assertEqual(bpy.ops.mt2.add_ramp_path(), {"FINISHED"})
        select_only(moat)
        self.assertEqual(run(bpy.ops.mt2.export), {"FINISHED"}, [f.message for f in bpy.context.scene.mt2.findings])
        text = (PROJECT / "bridge_themes/test_models_moat.vrt").read_text()
        self.assertNotIn("__replace", text)
        self.assertAlmostEqual(bridges.read_bridge(text).height, 5.0, places=3)

    def test_play_door(self):
        door = import_game("gizmo/door/base1.vmb")
        preview_module = module("door_preview")
        self.assertTrue(preview_module.is_door(door))
        self.assertEqual(bpy.ops.mt2.play_door(), {"FINISHED"})
        preview = preview_module.door_preview_action(door)
        self.assertIsNotNone(preview)
        self.assertEqual(door.mt2.animation, preview.name)
        markers = [m.name for m in bpy.context.scene.timeline_markers if m.name.startswith("door: ")]
        self.assertEqual(markers, ["door: unlock", "door: open", "door: close", "door: open"])
        self.assertNotIn(preview, module("anim_objects").owned_actions(door))
        self.assertFalse(any("Door preview" in text for text in pipeline.plan(door).texts.values()))
        door.mt2.animation = self.action_of(door, "open").name
        self.assertIsNone(preview_module.door_preview_action(door))
        self.assertFalse([m for m in bpy.context.scene.timeline_markers if m.name.startswith("door: ")])
        chest = import_game("gizmo/container/chest.vmb")
        self.assertFalse(preview_module.is_door(chest))

    def test_swatch_profiles(self):
        settings = bpy.context.scene.mt2
        colors = [(1.0, 0.0, 0.0, 1.0), (0.0, 0.5, 0.0, 1.0)]
        settings.recent_colors.clear()
        for color in colors:
            settings.recent_colors.add().color = color
        self.assertEqual(bpy.ops.mt2.save_swatches(name="Forest", ask=False), {"FINISHED"})
        self.assertEqual(settings.swatch_profile, "Forest")
        self.assertEqual(bpy.ops.mt2.new_swatches(), {"FINISHED"})
        self.assertEqual((len(settings.recent_colors), settings.swatch_profile), (0, ""))
        self.assertEqual(run(bpy.ops.mt2.load_swatches, name="Missing"), {"CANCELLED"})
        self.assertEqual(bpy.ops.mt2.load_swatches(name="Forest"), {"FINISHED"})
        loaded = [tuple(round(c, 3) for c in entry.color) for entry in settings.recent_colors]
        self.assertEqual(loaded, colors)
        profiles = module("swatch_profiles")
        profiles.profiles_file().write_text("not json")
        self.assertEqual(profiles.read_profiles(), {})
        self.assertEqual(bpy.ops.mt2.save_swatches(name="Forest", ask=False), {"FINISHED"})
        self.assertEqual(bpy.ops.mt2.delete_swatches(name="Forest"), {"FINISHED"})
        self.assertEqual(profiles.read_profiles(), {})

    def test_dungeon_theme_and_tile(self):
        self.assertEqual(run(bpy.ops.mt2.new_theme, family="dungeon", source="arid", name="crypt"), {"FINISHED"})
        theme = PROJECT / "dungeon/themes/testmodelscrypt"
        self.assertEqual(len([p for p in theme.rglob("*") if p.is_file()]), 62)
        self.assertTrue((PROJECT / "scenery/tagged/f_prop_small_testmodelscrypt_pot4.vmb").is_file())
        tile_file = theme / "walls/N/d_testmodelscrypt_N.vmb"
        bpy.ops.mt2.import_file(filepath=str(tile_file))
        tile = bpy.context.view_layer.objects.active
        self.assertEqual((tile.mt2.asset, tile.mt2.dungeon_theme, tile.mt2.shape), ("dungeon_tile", "testmodelscrypt", "N"))
        original = dungeons.read_sockets((theme / "walls/N/d_testmodelscrypt_N.vrt").read_text())
        self.assertEqual(len([c for c in tile.children_recursive if c.mt2.role == "SOCKET"]), len(original))
        plan = pipeline.plan(tile)
        self.assertTrue(plan.ok, [f.message for f in plan.findings])
        self.assertEqual(plan.rel, "dungeon/themes/testmodelscrypt/walls/N/d_testmodelscrypt_N.vmb")
        written = dungeons.read_sockets(plan.texts["dungeon/themes/testmodelscrypt/walls/N/d_testmodelscrypt_N.vrt"])
        for old, new in zip(original, written):
            self.assertEqual(old.tags, new.tags)
            for a, b in zip(old.position, new.position):
                self.assertAlmostEqual(a, b, places=4)
            sign = 1 if sum(x * y for x, y in zip(old.orientation, new.orientation)) >= 0 else -1
            for a, b in zip(old.orientation, new.orientation):
                self.assertAlmostEqual(a, sign * b, places=4)

    def test_convert_wizard(self):
        parts = []
        for x in (0, 3):
            cube = add_cube(f"Download{x}", size=1.0, location=(x, 0, 5))
            cube.scale = (2, 2, 2)
            cube.data.materials.append(textured_material())
            bpy.ops.object.modifier_add(type="SUBSURF")
            bpy.ops.object.modifier_apply(modifier="Subdivision")
            parts.append(cube)
        for cube in parts:
            cube.select_set(True)
        self.assertEqual(bpy.ops.mt2.convert(target="scenery", scenery_type="prop", height=4.0, faces=20,
                                             colors="BAKE", name="shed"), {"FINISHED"})
        obj = bpy.context.view_layer.objects.active
        self.assertEqual(len([o for o in bpy.data.objects if o.type == "MESH"]), 1)
        self.assertEqual((obj.mt2.asset, obj.mt2.scenery_type, obj.mt2.name), ("scenery", "prop", "shed"))
        heights = [v.co.z for v in obj.data.vertices]
        self.assertAlmostEqual(min(heights), 0.0, places=4)
        self.assertAlmostEqual(max(heights), 4.0, places=4)
        self.assertTrue(any(m.type == "DECIMATE" for m in obj.modifiers))
        self.assertEqual(obj.material_slots[0].material.mt2.game_name, "Material_tint")
        self.assertTrue(pipeline.plan(obj).ok, [f.message for f in pipeline.plan(obj).findings])

    def test_convert_keeps_texture(self):
        cube = add_cube("Crate download", size=2.0)
        cube.data.materials.append(textured_material())
        select_only(cube)
        self.assertEqual(bpy.ops.mt2.convert(target="scenery", height=2.0, colors="TEXTURE", name="dl_crate"),
                         {"FINISHED"})
        self.assertEqual(cube.material_slots[0].material.mt2.game_name, "test_models_dl_crate")
        self.assertTrue((PROJECT / "textures/test_models_dl_crate.png").is_file())
        self.assertEqual(pipeline.plan(cube).built.root.fragments[0].format, "PCNT")

    def test_gltf_conversion_matches_blender_export(self):
        bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1))
        monkey = bpy.context.active_object
        monkey.rotation_euler = (0.3, 0.2, 1.1)
        game_material(monkey, "Material_tint")
        bpy.context.scene.mt2.paint_color = (0.8, 0.2, 0.1, 1.0)
        bpy.ops.mt2.fill_color()
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        glb = PROJECT / "monkey.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), use_selection=True, export_format="GLB")
        converted = gltf.convert(glb)
        bpy.ops.mt2.make_asset()
        monkey.mt2.name = "monkey"
        exported = pipeline.plan(monkey).built.root
        def shape(root):
            points = [v[:3] for f in root.fragments for v in f.vertices]
            low = [min(p[i] for p in points) for i in range(3)]
            high = [max(p[i] for p in points) for i in range(3)]
            centroid = [sum(p[i] for p in points) / len(points) for i in range(3)]
            return [high[i] - low[i] for i in range(3)] + [centroid[i] - (low[i] + high[i]) / 2 for i in range(3)]
        for a1, a2 in zip(shape(converted), shape(exported)):
            self.assertAlmostEqual(a1, a2, delta=0.01)
        fragment = converted.fragments[0]
        a, b, c = (fragment.vertices[i] for i in fragment.indices[:3])
        u = [b[i] - a[i] for i in range(3)]
        w = [c[i] - a[i] for i in range(3)]
        cross = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        self.assertLess(sum(x * n for x, n in zip(cross, a[7:10])), 0, "game triangles are clockwise")
        self.assertAlmostEqual(a[3], 0.8, delta=0.02)
        self.assertAlmostEqual(a[4], 0.2, delta=0.02)

    def test_bake_texture_to_colors(self):
        bpy.ops.mesh.primitive_plane_add(size=2)
        plane = bpy.context.active_object
        image = bpy.data.images.new("tex", 4, 4)
        image.pixels = [0.0, 1.0, 0.0, 1.0] * 16
        material = bpy.data.materials.new("textured")
        if material.node_tree is None:
            material.use_nodes = True
        nodes = material.node_tree.nodes
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        material.node_tree.links.new(texture.outputs["Color"], nodes["Principled BSDF"].inputs["Base Color"])
        plane.data.materials.append(material)
        self.assertEqual(bpy.ops.mt2.bake_colors(), {"FINISHED"})
        colors = [tuple(d.color_srgb) for d in plane.data.color_attributes.active_color.data]
        self.assertTrue(all(c[1] > 0.9 and c[0] < 0.1 for c in colors), colors[:2])


class FakeLayout:
    def __init__(self, case, log):
        self.case, self.log = case, log

    def _child(self, *args, **kwargs):
        return FakeLayout(self.case, self.log)

    row = column = box = grid_flow = _child

    def separator(self, *args, **kwargs):
        pass

    def label(self, *args, **kwargs):
        self.log.append(("label", kwargs.get("text", "")))

    def prop(self, data, name, **kwargs):
        self.case.assertIn(name, data.bl_rna.properties.keys(), f"missing property {name}")
        self.log.append(("prop", name))

    def prop_search(self, data, name, search_data, search_name, **kwargs):
        self.case.assertIn(name, data.bl_rna.properties.keys())
        self.case.assertTrue(hasattr(search_data, search_name))

    def template_list(self, *args, **kwargs):
        self.log.append(("list", args[0]))

    def menu(self, idname, **kwargs):
        self.case.assertTrue(hasattr(bpy.types, idname), f"missing menu {idname}")
        self.log.append(("menu", idname))

    def operator(self, idname, **kwargs):
        category, name = idname.split(".")
        self.case.assertTrue(hasattr(getattr(bpy.ops, category), name), f"missing operator {idname}")
        self.log.append(("operator", idname))

        return type("Properties", (), {})()


class UI(unittest.TestCase):
    def draw_all(self):
        log = []
        ui = module("ui")
        for panel in ui.CLASSES:
            if hasattr(panel, "poll") and not panel.poll(bpy.context):
                continue
            fake = type("Panel", (), {"layout": FakeLayout(self, log)})()
            panel.draw(fake, bpy.context)

        return log

    def test_swatch_menu_draws(self):
        log = []
        menu = module("ops_swatches").MT2_MT_swatches
        menu.draw(type("Menu", (), {"layout": FakeLayout(self, log)})(), bpy.context)
        self.assertIn(("operator", "mt2.new_swatches"), log)
        self.assertIn(("menu", "MT2_MT_swatches"), self.draw_all())

    def test_panels_draw_without_an_asset(self):
        reset_scene()
        log = self.draw_all()
        self.assertIn(("operator", "mt2.make_asset"), log)
        self.assertIn(("operator", "mt2.import_game"), log)

    def test_every_icon_exists(self):
        icons = bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys()
        folder = Path(module("ui").__file__).parent
        for path in folder.glob("*.py"):
            for icon in re.findall(r'icon\s*=\s*"([A-Z0-9_]+)"', path.read_text()):
                self.assertIn(icon, icons, f"{path.name}: {icon}")
        for icon in module("ui").LEVEL_ICONS.values():
            self.assertIn(icon, icons)

    def test_findings_only_show_for_their_asset(self):
        reset_scene()
        broken = add_cube("Broken")
        bpy.ops.mt2.make_asset()
        run(bpy.ops.mt2.check)
        self.assertTrue(bpy.context.scene.mt2.findings)
        bpy.context.scene.mt2.show_notes = True
        message = bpy.context.scene.mt2.findings[0].message
        self.assertTrue(any(message.startswith(text) for kind, text in self.draw_all() if kind == "label" and text))
        other = add_cube("Other", location=(5, 0, 1))
        bpy.ops.mt2.make_asset()
        self.assertFalse(any(text and message.startswith(text) for kind, text in self.draw_all() if kind == "label"))
        select_only(broken)
        broken.mt2.name = "renamed"
        self.assertFalse(bpy.context.scene.mt2.findings)

    def test_setup_shows_while_the_mod_id_is_invalid(self):
        reset_scene()
        settings = bpy.context.scene.mt2
        settings.mod_id = "ui_test"
        self.assertNotIn(("operator", "mt2.setup"), self.draw_all())
        settings.mod_id = "9lives"
        self.assertIn(("operator", "mt2.setup"), self.draw_all())
        settings.mod_id = "ui_test"

    def test_panels_draw_for_every_asset_type(self):
        reset_scene()
        bpy.context.scene.mt2.mod_id = "ui_test"
        cube = add_cube("UI")
        game_material(cube, "Material_tint")
        bpy.ops.mt2.make_asset()
        for asset in module("mt2model.assets").ASSET_TYPES:
            with self.subTest(asset=asset):
                cube.mt2.asset = asset
                log = self.draw_all()
                self.assertIn(("operator", "mt2.export"), log)


def main():
    game.preferences().game_path = str(GAME) if GAME else ""
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for case in (Setup, RoundTrip, NewModels, UI):
        suite.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


main()
