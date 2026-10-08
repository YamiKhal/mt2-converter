import unittest

from helpers import cube, fake_game

from mt2model import model, records
from mt2model.animations import Animation, Timeline, chain, door_order, pose_jumps
from mt2model.artpacks import art_pack, pack_content, weapon_pack
from mt2model.bridges import read_bridge, set_obstruction, set_ramp_path
from mt2model.costume_files import PartPlacement, read_costume, rename_bones, write_costume
from mt2model.formats import layout
from mt2model.gamedata import GameData
from mt2model.naming import dungeon_theme_name
from mt2model.recolor import remap_colors
from mt2model.rigs import (
    CHARACTER_ANIMATIONS,
    creature_costume,
    creature_type,
    merge_animations,
    mod_animations,
    rename_nodes,
)
from mt2model.themes import theme_props
from mt2model.variants import Creature, read_creature, set_creature
from mt2model.vehicle_tool import offer_vehicle, offered_vehicles, vehicle_tool_file


class ArtPackTests(unittest.TestCase):
    def test_content_by_section(self):
        content = pack_content(
            [
                "scenery/stone/m_rock.vmb",
                "scenery/tagged/f_prop_m_pot.vmb",
                "bridge_themes/m_moat/bridge_m_moat.vmb",
                "wall_themes/castle/wall_castle.vmb",
                "weapons/m_blades/015_m_sword.vmb",
                "weapons/swords/015_m_sword.vmb",
            ],
            lambda prefix: prefix in ("wall_themes/castle/", "weapons/swords/"),
        )
        self.assertEqual(content["scenery"], ["stone/m_rock.vmb"])
        self.assertEqual(content["bridges"], ["m_moat"])
        self.assertEqual(content["walls"], [])
        self.assertEqual(content["weaponCategories"], ["m_blades"])

    def test_weapon_categories_get_their_own_pack(self):
        art = records.parse(
            art_pack("m", 2000, False, {"scenery": ["stone/m_rock.vmb"], "weaponCategories": ["m_blades"]})
        )
        self.assertIsNone(art[0].child("content").child("weaponCategories"))
        weapons = records.parse(weapon_pack("m_blades", 2000))[0]
        self.assertEqual(weapons.prop("type"), "weapons")
        self.assertEqual(weapons.prop("key"), "m_blades")
        self.assertEqual(weapons.child("content").child("weaponCategories").children[0].first(), "m_blades")


class VehicleToolTests(unittest.TestCase):
    def test_names_are_added_once(self):
        text = offer_vehicle(offer_vehicle("", "m_raft"), "m_blimp")
        self.assertEqual(offered_vehicles(offer_vehicle(text, "m_raft")), ["m_raft", "m_blimp"])

    def test_standalone_keeps_the_game_file(self):
        game = 'mmoCursorBehaviourBuild\n{\n\tname "@Build";\n}\n' + offer_vehicle("", "ship")
        own = offer_vehicle("", "m_raft")
        text = vehicle_tool_file(game, own, "m_blimp", standalone=True)
        self.assertIn("@Build", text)
        self.assertEqual(offered_vehicles(text), ["ship", "m_raft", "m_blimp"])
        self.assertEqual(
            offered_vehicles(vehicle_tool_file(game, own, "m_blimp", standalone=False)), ["m_raft", "m_blimp"]
        )


class DungeonThemeTests(unittest.TestCase):
    def test_theme_name_is_one_tag(self):
        self.assertEqual(dungeon_theme_name("my_mod", "Dark Crypt"), "mymoddarkcrypt")

    def test_props_are_copied_under_the_new_tag(self):
        root = fake_game().sources[0].root
        folder = root / "scenery" / "tagged"
        folder.mkdir(parents=True)
        for name in ("f_prop_small_arid_pot1", "w_light_cave_torch"):
            (folder / f"{name}.vmb").write_bytes(b"x")
        data = GameData.open(root)
        self.assertEqual(list(theme_props(data, "arid", "mcrypt")), ["scenery/tagged/f_prop_small_mcrypt_pot1.vmb"])

    def test_recolor_keeps_the_shade(self):
        node = cube(fmt="PCN")
        remap_colors(node, [(0.5, 0.5, 0.5, 1.0)], [(0.2, 0.4, 0.8, 1.0)])
        at = layout("PCN").color
        self.assertEqual(tuple(round(c, 3) for c in node.fragments[0].vertices[0][at : at + 3]), (0.2, 0.4, 0.8))
        model.read_model(model.write_model(node))


class RigTests(unittest.TestCase):
    def test_character_animation_names(self):
        self.assertEqual(len(CHARACTER_ANIMATIONS), 49)
        self.assertEqual(CHARACTER_ANIMATIONS.index("death"), 0x2E)

    def test_changed_animations_replace_by_name(self):
        base = [Animation("idle"), Animation("run")]
        merged = merge_animations(base, [Animation("run", "Loop"), Animation("death")])
        self.assertEqual([(a.name, a.playback) for a in merged], [("idle", "Once"), ("run", "Loop"), ("death", "Once")])

    def test_standalone_animations(self):
        game = [Animation("idle"), Animation("run")]
        own = [Animation("idle"), Animation("run", "Loop")]
        changed = [Animation("death")]
        self.assertEqual(
            [(a.name, a.playback) for a in mod_animations(game, own, changed, standalone=True)],
            [("idle", "Once"), ("run", "Loop"), ("death", "Once")],
        )
        self.assertEqual(
            [(a.name, a.playback) for a in mod_animations(game, own, changed, standalone=False)],
            [("run", "Loop"), ("death", "Once")],
        )

    def test_costume_gets_its_rig(self):
        template = 'mmoCostume {\n\tname "bear";\n\tactorName "quadruped";\n\tcostumePart {\n\t}\n}\n'
        written = read_costume(
            write_costume(
                template, "m_griffin", [PartPlacement("wingleft", "costumes/m/wingleft.vmb")], actor="m_griffin"
            )
        )
        self.assertEqual((written.name, written.actor), ("m_griffin", "m_griffin"))
        self.assertEqual([p.bone for p in written.parts], ["wingleft"])

    def test_renamed_bones_keep_their_entries(self):
        template = "\n".join(
            [
                "mmoCostume {",
                '\tname "k";',
                '\tactorName "m_biped";',
                "\tcostumePart {",
                "\t\tmmoCostumePartDescriptor {",
                '\t\t\tboneName "armright"',
                "\t\t\tattachment {",
                "\t\t\t}",
                "\t\t}",
                "\t}",
                "}",
                "",
            ]
        )
        renamed = records.parse(rename_bones(template, {"armright": "arm_r"}))[0]
        descriptor = renamed.child("costumePart").children[0]
        self.assertEqual(descriptor.prop("boneName"), "arm_r")
        self.assertIsNotNone(descriptor.child("attachment"))
        written = read_costume(
            write_costume(template, "k", [PartPlacement("arm_r", "a.vmb")], renames={"armright": "arm_r"})
        )
        self.assertEqual([p.bone for p in written.parts], ["arm_r"])

    def test_renamed_nodes_in_animations(self):
        animation = Animation("idle", timelines=[Timeline("armright"), Timeline("head")])
        rename_nodes([animation], {"armright": "arm_r"})
        self.assertEqual([t.node for t in animation.timelines], ["arm_r", "head"])

    def test_pose_jumps_between_animations(self):
        unlock = Animation(
            "unlock",
            timelines=[
                Timeline("lock", translation=[(0.0, (0, 0, 0)), (1.0, (0, 0, 1))], rotation=[(0.0, (0, 0, 0, 1))])
            ],
        )
        opening = Animation(
            "open", timelines=[Timeline("lock", translation=[(0.0, (0, 0, 0.5))], rotation=[(0.0, (0, 0, 0, -1))])]
        )
        self.assertEqual(pose_jumps(unlock, opening), {"lock": (0.5, 0.0, 0.0)})

    def test_creature_type_from_a_prefab(self):
        template = 'mmoCharacterType\n{\n\tdef\n\t{\n\tname "Bear"\n\tcostumeName "bear"\n\tspeed 4.0\n\t}\n}\n'
        text = creature_type(template, "Griffin", "m_griffin")
        self.assertEqual(creature_costume(text), "m_griffin")
        definition = records.parse(text)[0].child("def")
        self.assertEqual((definition.prop("name"), definition.prop("speed")), ("Griffin", "4.0"))

    def test_flight_point_creature(self):
        variant = (
            'mmoBuildingVariant\n{\n\tname "owl";\n\tmodelFile "a.vmb";\n\tactor "owl";\n\tactorOffset 0 5 0;\n}\n'
        )
        self.assertEqual(read_creature(variant), Creature("owl", "idle", (0.0, 5.0, 0.0), None))
        griffin = Creature("m_griffin", "idle", (1.0, 2.0, 3.0), (0.0, -1.0, 0.0, 0.0))
        self.assertEqual(read_creature(set_creature(variant, griffin)), griffin)


class BridgeTests(unittest.TestCase):
    VARIANT = "\n".join(
        [
            "mmoBridgeVariant",
            "{",
            'name "rope";',
            "height 3.0",
            "rampPath",
            "{",
            "mmoPadPath",
            "{",
            "path",
            "{",
            "0 0 0;",
            "0 3 22;",
            "}",
            "}",
            "}",
            "fullyObstructed false;",
            "obstruction",
            "{",
            "}",
            "}",
            "",
        ]
    )

    def test_ramp_path_sets_the_height(self):
        text = set_ramp_path(self.VARIANT, [(0, 0, 0), (0, 2, 10), (0, 6, 30)], replaces_game=False)
        bridge = read_bridge(text)
        self.assertEqual((bridge.height, len(bridge.ramp_path)), (6.0, 3))
        self.assertNotIn("__replace", text)

    def test_obstruction_and_one_replace_marker(self):
        text = set_obstruction(self.VARIANT, [[(-2, 10), (2, 10), (2, 20)]], True, replaces_game=True)
        text = set_obstruction(text, [[(-2, 10), (2, 10), (2, 20)]], True, replaces_game=True)
        bridge = read_bridge(text)
        self.assertTrue(bridge.fully_obstructed)
        self.assertEqual(len(bridge.obstruction), 1)
        self.assertEqual(text.count("__replace"), 1)
        self.assertEqual(read_bridge(text).ramp_path, read_bridge(self.VARIANT).ramp_path)


class DoorChainTests(unittest.TestCase):
    def test_doors_play_unlock_open_close_open(self):
        self.assertEqual(door_order({"close", "open", "unlock", "full animation"}), ["unlock", "open", "close", "open"])

    def test_chained_animations_follow_each_other(self):
        unlock = Animation("unlock", timelines=[Timeline("lock", rotation=[(0.0, (0, 0, 0, 1)), (1.0, (0, 0, 0, 1))])])
        opening = Animation("open", timelines=[Timeline("lock", rotation=[(0.0, (0, 0, 0, -1))])])
        chained, starts = chain("preview", [unlock, opening], 0.5)
        self.assertEqual(starts, [0.0, 1.5])
        self.assertEqual(chained.timelines[0].rotation[-1], (1.5, (0, 0, 0, 1)))


if __name__ == "__main__":
    unittest.main()
