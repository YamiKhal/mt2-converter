SEED = 42

_C1 = 0xCC9E2D51
_C2 = 0x1B873593
_MASK = 0xFFFFFFFF


def _rotl(x: int, r: int) -> int:
    return ((x << r) | (x >> (32 - r))) & _MASK


def murmur3_32(data: bytes, seed: int = SEED) -> int:
    h = seed & _MASK
    blocks = len(data) // 4
    for i in range(blocks):
        k = int.from_bytes(data[4 * i:4 * i + 4], "little")
        k = _rotl((k * _C1) & _MASK, 15)
        h ^= (k * _C2) & _MASK
        h = (_rotl(h, 13) * 5 + 0xE6546B64) & _MASK
    tail = data[4 * blocks:]
    k = 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if tail:
        k ^= tail[0]
        k = _rotl((k * _C1) & _MASK, 15)
        h ^= (k * _C2) & _MASK
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & _MASK
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & _MASK
    h ^= h >> 16

    return h


def variant_id(file_name: str) -> int:
    value = murmur3_32(file_name.encode("latin-1"))

    return value - (1 << 32) if value >= 1 << 31 else value
