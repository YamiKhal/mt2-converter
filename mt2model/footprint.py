import math

from .model import Node

Point = tuple[float, float]

SCENERY_MAX_HEIGHT = 10.0
SCENERY_MIN_AREA = 6.0
SCENERY_MIN_TALL = 4.0
BUILDING_MAX_HEIGHT = 2.0
BUILDING_EXPAND = 1.0
SIMPLIFY_FRACTION = 0.01


def _rotate(q, v):
    x, y, z, w = q
    tx = 2 * (y * v[2] - z * v[1])
    ty = 2 * (z * v[0] - x * v[2])
    tz = 2 * (x * v[1] - y * v[0])

    return (v[0] + w * tx + y * tz - z * ty,
            v[1] + w * ty + z * tx - x * tz,
            v[2] + w * tz + x * ty - y * tx)


def _transform(node: Node, p):
    scaled = (p[0] * node.scale[0], p[1] * node.scale[1], p[2] * node.scale[2])
    r = _rotate(node.rotation, scaled)

    return (r[0] + node.translation[0], r[1] + node.translation[1], r[2] + node.translation[2])


def model_points(node: Node, skip: frozenset[str] = frozenset({"light", "obstruction", "collision", "navmesh"})):
    points = []
    for fragment in node.fragments:
        if fragment.material in skip:
            continue
        points += [tuple(v[:3]) for v in fragment.vertices]
    for child in node.children:
        points += model_points(child, skip)

    return [_transform(node, p) for p in points]


def convex_hull(points: list[Point]) -> list[Point]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def area(polygon: list[Point]) -> float:
    total = 0.0
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        total += a[0] * b[1] - b[0] * a[1]

    return total / 2


def simplify(polygon: list[Point], fraction: float = SIMPLIFY_FRACTION) -> list[Point]:
    budget = abs(area(polygon)) * fraction
    poly = list(polygon)
    while len(poly) > 3:
        costs = [abs(area([poly[i - 1], poly[i], poly[(i + 1) % len(poly)]])) for i in range(len(poly))]
        cheapest = min(range(len(poly)), key=costs.__getitem__)
        if costs[cheapest] > budget:
            break
        budget -= costs[cheapest]
        poly.pop(cheapest)

    return poly


def expand(polygon: list[Point], distance: float) -> list[Point]:
    if len(polygon) < 3:
        return polygon
    sign = 1.0 if area(polygon) > 0 else -1.0
    lines = []
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = sign * dy / length, -sign * dx / length
        lines.append(((a[0] + nx * distance, a[1] + ny * distance), (dx, dy)))
    out = []
    for i in range(len(lines)):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-12:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / det
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))

    return out


def _hull_below(points, max_height: float) -> list[Point]:
    return convex_hull([(p[0], p[2]) for p in points if p[1] <= max_height])


def scenery_footprint(node: Node) -> list[Point] | None:
    points = model_points(node)
    if not points:
        return None
    hull = simplify(_hull_below(points, SCENERY_MAX_HEIGHT))
    heights = [p[1] for p in points]
    tall = max(heights) - min(heights) > SCENERY_MIN_TALL
    if len(hull) < 3 or not (abs(area(hull)) > SCENERY_MIN_AREA or tall):
        return None

    return hull


def building_footprint(node: Node) -> list[Point] | None:
    hull = _hull_below(model_points(node), BUILDING_MAX_HEIGHT)
    if len(hull) < 3:
        return None

    return expand(simplify(hull), BUILDING_EXPAND)


def is_convex(polygon: list[Point]) -> bool:
    if len(polygon) < 3:
        return False
    sign = 0
    for i in range(len(polygon)):
        a, b, c = polygon[i], polygon[(i + 1) % len(polygon)], polygon[(i + 2) % len(polygon)]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) < 1e-9:
            continue
        if sign == 0:
            sign = 1 if cross > 0 else -1
        elif (cross > 0) != (sign > 0):
            return False

    return sign != 0


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    x, y = point
    inside = False
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[i - 1]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside

    return inside
