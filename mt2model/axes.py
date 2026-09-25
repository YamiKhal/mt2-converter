Vector = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]
Point = tuple[float, float]

AXES_VERSION = 2


def swap_position(p) -> Vector:
    return (-p[0], p[2], p[1])


def swap_scale(s) -> Vector:
    return (s[0], s[2], s[1])


def swap_rotation(q) -> Quaternion:
    return (-q[0], q[2], q[1], q[3])


def swap_ground(p) -> Point:
    return (-p[0], p[1])
