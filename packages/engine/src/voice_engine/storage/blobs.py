from __future__ import annotations

import zlib

LEVEL = 6


def compress(data: bytes) -> bytes:
    return zlib.compress(data, LEVEL)


def decompress(data: bytes) -> bytes:
    return zlib.decompress(data)
