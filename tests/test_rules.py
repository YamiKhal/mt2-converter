import unittest

from helpers import cube, fake_game

from mt2model.assets import asset_type, guess_from_path
from mt2model.glow import glow_material, glow_shader
from mt2model.materials import MaterialCatalog, classify
from mt2model.naming import ExportTarget, model_path, prefixed, target_problems
from mt2model.validate import has_errors, validate


def levels(findings) -> list[str]:
    return [f.level for f in findings]


class NamingTests(unittest.TestCase):
    def test_paths_for_each_asset_type(self):
        def path(**kw):
            return model_path(ExportTarget(mod_id="mymod", name="Big Rock", **kw))

        self.assertEqual(path(asset="scenery", scenery_type="stone"), "scenery/stone/mymod_big_rock.vmb")
        self.assertEqual(
            path(asset="weapon", weapon_category="swords", item_level=45), "weapons/swords/045_mymod_big_rock.vmb"
        )
        self.assertEqual(
            path(asset="tagged", tag_place="wall", tag_kind="light", tag_small=True, tag_extra=["cave"]),
            "scenery/tagged/w_light_small_cave_mymod_big_rock.vmb",
        )
        self.assertEqual(
            path(asset="costume_part", costume_set="mymod_knight", bone="hat"), "costumes/mymod_knight/hat.vmb"
        )
        self.assertEqual(
            path(asset="modular", theme="castle2", slot="tops_end"),
            "building_themes/castle2/tops_end/mymod_big_rock.vmb",
        )
        self.assertEqual(
            path(asset="modular", theme="mymod_town", slot="tops_end"),
            "building_themes/mymod_town/tops_end/big_rock.vmb",
        )
        self.assertEqual(
            path(asset="wall", theme="mymod_town", wall_piece="turret"), "wall_themes/mymod_town/turret_mymod_town.vmb"
        )
        self.assertEqual(path(asset="building", building_dir="buildings/inn"), "buildings/inn/mymod_big_rock.vmb")

    def test_prefix_is_added_once(self):
        self.assertEqual(prefixed("mymod", "mymod_rock"), "mymod_rock")
        self.assertEqual(prefixed("mymod", "Rock 2"), "mymod_rock_2")

    def test_problems(self):
        self.assertTrue(target_problems(ExportTarget("scenery", "rock", "MyMod")))
        self.assertTrue(target_problems(ExportTarget("scenery", "rock", "mymod", scenery_type="tagged")))
        self.assertTrue(target_problems(ExportTarget("weapon", "rock", "mymod", item_level=1000)))
        self.assertFalse(target_problems(ExportTarget("scenery", "rock", "mymod")))

    def test_guess_asset_from_game_path(self):
        self.assertEqual(guess_from_path("scenery/stone/rock.vmb"), "scenery")
        self.assertEqual(guess_from_path("scenery/tagged/f_prop_x.vmb"), "tagged")
        self.assertEqual(guess_from_path("costumes/knight/head.vmb"), "costume_part")
        self.assertEqual(guess_from_path("building_themes/castle2/sides/a.vmb"), "modular")
        self.assertEqual(guess_from_path("buildit.vmb"), "raw")


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.catalog = MaterialCatalog(fake_game())

    def test_clean_scenery_passes(self):
        self.assertFalse(has_errors(validate(cube(size=3.0), asset_type("scenery"), self.catalog)))

    def test_missing_material_is_an_error(self):
        findings = validate(cube("Nope_tint"), asset_type("scenery"), self.catalog)

        self.assertIn("error", levels(findings))
        self.assertIn("closes", findings[0].message)

    def test_collision_outside_dungeons_is_an_error(self):
        self.assertTrue(has_errors(validate(cube("collision"), asset_type("scenery"), self.catalog)))
        self.assertFalse(has_errors(validate(cube("light", size=3.0), asset_type("scenery"), self.catalog)))

    def test_broken_indices_are_errors(self):
        root = cube()
        root.fragments[0].indices[0] = 99

        self.assertTrue(has_errors(validate(root, asset_type("scenery"), self.catalog)))

    def test_glowing_costume_material_keeps_the_palette(self):
        text = glow_material(self.catalog.data.read("materials/costume.mat").decode(), "test_costume_glow_f.glsl")
        info = classify("test_costume_glow", text)
        self.assertEqual((info.kind, info.glow), ("costume", True))
        self.assertIn('"costume_v.glsl" "test_costume_glow_f.glsl"', text)
        self.assertFalse(self.catalog.get("costume").glow)
        self.assertEqual(glow_material(text, "test_costume_glow_f.glsl"), text)

    def test_glow_shader_ignores_the_light(self):
        shader = (
            "\tcolor.rgb = mix( color.rgb, frontColor.rgb, frontColor.a );\r\n"
            "\tcolor.rgb = shade(color.rgb);\r\n"
            "\tif ( distanceCull )\r\n"
        )
        glowing = glow_shader(shader)
        self.assertLess(glowing.index("vec3 glowColor = color.rgb;"), glowing.index("shade("))
        self.assertLess(glowing.index("shade("), glowing.index("max( color.rgb, mix( glowColor"))
        self.assertLess(glowing.index("nowGlow = 1.0;"), glowing.index("if ( distanceCull )"))
        with self.assertRaises(ValueError):
            glow_shader("void main() {}")

    def test_palette_material_needs_uvs(self):
        self.assertTrue(has_errors(validate(cube("costume", "PN"), asset_type("costume_part"), self.catalog)))
        self.assertFalse(has_errors(validate(cube("costume", "PNT"), asset_type("costume_part"), self.catalog)))

    def test_floating_scenery_is_warned(self):
        findings = validate(cube(size=3.0, lift=2.0), asset_type("scenery"), self.catalog)

        self.assertTrue(any("float" in f.message for f in findings))

    def test_override_is_warned(self):
        findings = validate(cube(size=3.0), asset_type("scenery"), self.catalog, replaces_vanilla=True)

        self.assertTrue(any("replaces" in f.message for f in findings))

    def test_missing_texture_is_an_error(self):
        findings = validate(cube("crate", "PCNT", size=3.0), asset_type("scenery"), self.catalog)

        self.assertTrue(any("a.png" in f.message and f.level == "error" for f in findings))

    def test_existing_texture_passes_in_any_case(self):
        (self.catalog.data.sources[0].root / "A.PNG").write_bytes(b"png")
        catalog = MaterialCatalog(self.catalog.data)

        self.assertFalse(has_errors(validate(cube("crate", "PCNT", size=3.0), asset_type("scenery"), catalog)))


if __name__ == "__main__":
    unittest.main()
