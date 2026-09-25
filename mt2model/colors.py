Color = tuple[float, float, float, float]


def srgb_to_linear(color) -> Color:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (channel(color[0]), channel(color[1]), channel(color[2]), color[3] if len(color) > 3 else 1.0)


def linear_to_srgb(color) -> Color:
    def channel(c: float) -> float:
        c = min(max(c, 0.0), 1.0)

        return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    return (channel(color[0]), channel(color[1]), channel(color[2]), color[3] if len(color) > 3 else 1.0)
