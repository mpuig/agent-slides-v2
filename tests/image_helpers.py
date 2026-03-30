from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum)
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", checksum & 0xFFFFFFFF)
    )


def write_png(
    path: Path, *, width: int, height: int, color: tuple[int, int, int] = (64, 128, 192)
) -> Path:
    rows = []
    pixel = bytes(color)
    for _ in range(height):
        rows.append(b"\x00" + (pixel * width))
    compressed = zlib.compress(b"".join(rows))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"IDAT", compressed),
            _png_chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(payload)
    return path
