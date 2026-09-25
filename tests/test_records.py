import unittest

from mt2model import records
from mt2model.costume import read_defaults
from mt2model.i18n import set_strings
from mt2model.obstruction import read_obstruction, write_obstruction
from mt2model.variants import derive_variant

VARIANT = """mmoBuildingVariant
{
\tname "base";
\tmodelFile "buildings/tavern/base.vmb";
\tpad
\t{
\t\tmmoPad
\t\t{
\t\t\tname "a";
\t\t\tcs
\t\t\t{
\t\t\t\tvertex
\t\t\t\t{
\t\t\t\t\t-1.000000 0.792156 -4.408974;
\t\t\t\t\t1.000000 0.792156 -4.408974;
\t\t\t\t}
\t\t\t}
\t\t}
\t}
}
"""


class RecordTests(unittest.TestCase):
    def test_parse_and_render_is_stable(self):
        parsed = records.parse(VARIANT)

        self.assertEqual(records.render(records.parse(records.render(parsed))), records.render(parsed))
        self.assertEqual(parsed[0].prop("modelFile"), "buildings/tavern/base.vmb")
        vertex = parsed[0].child("pad").child("mmoPad").child("cs").child("vertex")
        self.assertEqual(vertex.children[0].floats(), [-1.0, 0.792156, -4.408974])

    def test_brace_on_same_line_and_comments(self):
        parsed = records.parse('Material {\n\tcolor 1 0 0 1 # red\n\tshininess: 0.0\n}\n')

        self.assertEqual(parsed[0].child("color").floats(), [1.0, 0.0, 0.0, 1.0])

    def test_defaults_use_commas(self):
        text = "mmoCostumeDefaults\n{\n\tcolors {\n\t\t0.1,0.2,0.3,1.0\n\t\t0,0,0,1\n\t}\n}\n"
        palette = read_defaults(text)

        self.assertEqual(len(palette), 8)
        self.assertEqual(palette[0], (0.1, 0.2, 0.3, 1.0))

    def test_derive_variant_changes_only_name_and_model(self):
        text = derive_variant(VARIANT, "mymod_blue", "buildings/tavern/mymod_blue.vmb")
        variant = records.parse(text)[0]

        self.assertEqual(variant.prop("name"), "mymod_blue")
        self.assertEqual(variant.prop("modelFile"), "buildings/tavern/mymod_blue.vmb")
        self.assertIsNotNone(variant.child("pad"))

    def test_obstruction_round_trip(self):
        polygons = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], [(-2.0, -2.0), (-1.0, -2.0), (-1.0, -1.0), (-2.0, -1.0)]]

        self.assertEqual(read_obstruction(write_obstruction(polygons)), polygons)

    def test_strings_are_added_and_replaced(self):
        text = set_strings('a_displayname "Old"\n', {"a_displayname": "New", "b_displayname": 'Say "hi"'})
        parsed = records.parse(text)

        self.assertEqual([(r.label, r.first()) for r in parsed], [("a_displayname", "New"), ("b_displayname", 'Say "hi"')])


if __name__ == "__main__":
    unittest.main()
