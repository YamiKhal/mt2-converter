import unittest

from helpers import cube, fake_game
from mt2model import model, records
from mt2model.artpacks import art_pack, pack_content, weapon_pack
from mt2model.formats import layout
from mt2model.gamedata import GameData
from mt2model.naming import dungeon_theme_name
from mt2model.recolor import remap_colors
from mt2model.themes import theme_props
from mt2model.vehicle_tool import offer_vehicle, offered_vehicles


class ArtPackTests(unittest.TestCase):
    def test_content_by_section(self):
        content = pack_content([
            "scenery/stone/m_rock.vmb", "scenery/tagged/f_prop_m_pot.vmb", "bridge_themes/m_moat/bridge_m_moat.vmb",
            "wall_themes/castle/wall_castle.vmb", "weapons/m_blades/015_m_sword.vmb", "weapons/swords/015_m_sword.vmb",
        ], lambda prefix: prefix in ("wall_themes/castle/", "weapons/swords/"))
        self.assertEqual(content["scenery"], ["stone/m_rock.vmb"])
        self.assertEqual(content["bridges"], ["m_moat"])
        self.assertEqual(content["walls"], [])
        self.assertEqual(content["weaponCategories"], ["m_blades"])

    def test_weapon_categories_get_their_own_pack(self):
        art = records.parse(art_pack("m", 2000, False, {"scenery": ["stone/m_rock.vmb"], "weaponCategories": ["m_blades"]}))
        self.assertIsNone(art[0].child("content").child("weaponCategories"))
        weapons = records.parse(weapon_pack("m_blades", 2000))[0]
        self.assertEqual(weapons.prop("type"), "weapons")
        self.assertEqual(weapons.prop("key"), "m_blades")
        self.assertEqual(weapons.child("content").child("weaponCategories").children[0].first(), "m_blades")


class VehicleToolTests(unittest.TestCase):
    def test_names_are_added_once(self):
        text = offer_vehicle(offer_vehicle("", "m_raft"), "m_blimp")
        self.assertEqual(offered_vehicles(offer_vehicle(text, "m_raft")), ["m_raft", "m_blimp"])


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
        self.assertEqual(tuple(round(c, 3) for c in node.fragments[0].vertices[0][at:at + 3]), (0.2, 0.4, 0.8))
        model.read_model(model.write_model(node))


if __name__ == "__main__":
    unittest.main()
