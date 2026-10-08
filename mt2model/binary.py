import struct


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def int16(self) -> int:
        value = struct.unpack_from(">h", self.data, self.pos)[0]
        self.pos += 2

        return value

    def int32(self) -> int:
        value = struct.unpack_from(">i", self.data, self.pos)[0]
        self.pos += 4

        return value

    def int32s(self, count: int) -> tuple[int, ...]:
        values = struct.unpack_from(f">{count}i", self.data, self.pos)
        self.pos += 4 * count

        return values

    def floats(self, count: int) -> tuple[float, ...]:
        values = struct.unpack_from(f"<{count}f", self.data, self.pos)
        self.pos += 4 * count

        return values

    def string(self) -> str:
        length = self.int16()
        value = self.data[self.pos : self.pos + length].decode("latin-1")
        self.pos += length

        return value


class Writer:
    def __init__(self):
        self.parts: list[bytes] = []

    def int16(self, value: int):
        self.parts.append(struct.pack(">h", value))

    def int32(self, value: int):
        self.parts.append(struct.pack(">i", value))

    def int32s(self, values: list[int]):
        self.parts.append(struct.pack(f">{len(values)}i", *values))

    def floats(self, values: list[float]):
        self.parts.append(struct.pack(f"<{len(values)}f", *values))

    def string(self, value: str):
        encoded = value.encode("latin-1")
        self.int16(len(encoded))
        self.parts.append(encoded)

    def bytes(self) -> bytes:
        return b"".join(self.parts)
