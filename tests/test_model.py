import unittest

from helpers import cube, real_game

from mt2model import model
from mt2model.formats import layout, make_format
from mt2model.model import Node


class ModelTests(unittest.TestCase):
    def test_round_trip_keeps_every_field(self):
        root = cube("Material_tint", "PCNT")
        root.children.append(Node(name="child", translation=(1.0, 2.0, 3.0), version="ModelV2", lods=[[], []]))
        again = model.read_model(model.write_model(root))

        self.assertEqual(model.write_model(again), model.write_model(root))
        self.assertEqual(again.children[0].name, "child")
        self.assertEqual(len(again.children[0].lods), 2)

    def test_layout_offsets(self):
        self.assertEqual(layout("PCNT"), layout("PCNT"))
        self.assertEqual(
            (layout("PCNT").color, layout("PCNT").normal, layout("PCNT").texel, layout("PCNT").size), (3, 7, 10, 12)
        )
        self.assertEqual((layout("PNT").normal, layout("PNT").texel), (3, 6))
        self.assertEqual(make_format(True, True, False), "PCN")

    def test_unknown_format_is_rejected(self):
        with self.assertRaises(ValueError):
            layout("PX")

    def test_vanilla_models_rewrite_byte_for_byte(self):
        data = real_game()
        if data is None:
            self.skipTest("game not installed")
        for rel in data.files("", ".vmb")[::25]:
            raw = data.read(rel)
            root, used = model.read_model_with_size(raw)

            self.assertEqual(model.write_model(root), raw[:used], rel)


if __name__ == "__main__":
    unittest.main()
