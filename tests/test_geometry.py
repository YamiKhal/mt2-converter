import unittest

from helpers import cube
from mt2model.axes import swap_position, swap_rotation, swap_scale
from mt2model.colors import linear_to_srgb, srgb_to_linear
from mt2model.costume import extent, normalise, slot_of, slot_u
from mt2model.footprint import area, building_footprint, convex_hull, expand, is_convex, scenery_footprint, simplify
from mt2model.murmur import murmur3_32


class GeometryTests(unittest.TestCase):
    def test_hull_drops_inner_points(self):
        hull = convex_hull([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)])

        self.assertEqual(len(hull), 4)
        self.assertAlmostEqual(abs(area(hull)), 4.0)

    def test_simplify_removes_nearly_straight_points(self):
        polygon = [(0, 0), (1, 0.001), (2, 0), (2, 2), (0, 2)]

        self.assertEqual(len(simplify(polygon)), 4)

    def test_expand_grows_a_square(self):
        grown = expand([(0, 0), (2, 0), (2, 2), (0, 2)], 1.0)

        self.assertAlmostEqual(abs(area(grown)), 16.0)

    def test_convexity(self):
        self.assertTrue(is_convex([(0, 0), (2, 0), (2, 2), (0, 2)]))
        self.assertFalse(is_convex([(0, 0), (2, 0), (1, 0.5), (2, 2), (0, 2)]))

    def test_small_scenery_has_no_footprint_and_big_has_one(self):
        self.assertIsNone(scenery_footprint(cube(size=0.5)))
        self.assertIsNotNone(scenery_footprint(cube(size=3.0)))

    def test_building_needs_geometry_near_the_ground(self):
        self.assertIsNotNone(building_footprint(cube(size=3.0)))
        self.assertIsNone(building_footprint(cube(size=3.0, lift=5.0)))

    def test_axis_swaps_are_their_own_inverse(self):
        self.assertEqual(swap_position(swap_position((1, 2, 3))), (1, 2, 3))
        self.assertEqual(swap_scale(swap_scale((1, 2, 3))), (1, 2, 3))
        self.assertEqual(swap_rotation(swap_rotation((0.1, 0.2, 0.3, 0.9))), (0.1, 0.2, 0.3, 0.9))

    def test_axis_swap_does_not_mirror(self):
        right, front, up = swap_position((1, 0, 0)), swap_position((0, -1, 0)), swap_position((0, 0, 1))

        self.assertAlmostEqual(_dot(_cross(right, up), front), 1.0)
        self.assertEqual(up, (0, 1, 0))
        self.assertEqual(front, (0, 0, -1))

    def test_rotations_follow_positions(self):
        q = (0.3, -0.5, 0.1, 0.806)
        v = (0.2, 1.5, -0.7)

        self.assertEqual(
            [round(x, 6) for x in swap_position(_rotate(q, v))],
            [round(x, 6) for x in _rotate(swap_rotation(q), swap_position(v))],
        )

    def test_srgb_round_trip(self):
        color = (0.91, 0.686, 0.078, 1.0)

        self.assertEqual([round(c, 6) for c in linear_to_srgb(srgb_to_linear(color))], list(color))

    def test_murmur_matches_reference_values(self):
        self.assertEqual(murmur3_32(b"", 0), 0)
        self.assertEqual(murmur3_32(b"", 1), 0x514E28B7)
        self.assertEqual(murmur3_32(b"hello", 0), 0x248BFA47)
        self.assertEqual(murmur3_32(b"The quick brown fox jumps over the lazy dog", 0), 0x2E4FF723)

    def test_palette_slots(self):
        self.assertEqual([slot_of(slot_u(s)) for s in range(8)], list(range(8)))
        self.assertEqual(slot_of(slot_u(2, 4), 4), 2)

    def test_normalise_scales_to_unit_size(self):
        part = cube("costume", "PNT", size=2.0)
        scale = normalise(part)

        self.assertAlmostEqual(scale, 4.0)
        self.assertAlmostEqual(extent(part), 1.0)
        self.assertEqual(part.fragments[0].vertices[0][3:], (0.0, 1.0, 0.0, 0.0625, 0.2))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _rotate(q, v):
    axis, w = q[:3], q[3]
    t = tuple(2 * c for c in _cross(axis, v))
    turn = _cross(axis, t)

    return tuple(v[i] + w * t[i] + turn[i] for i in range(3))


if __name__ == "__main__":
    unittest.main()
