#!/usr/bin/env python3
"""Generate the v2 app icon source (1024x1024 PNG) without external deps.

Produces a rounded indigo square with a white document and a downward
export arrow. Output is written to src-tauri/icons/icon-1024.png; the full
icon set is then produced with `npx tauri icon`.
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

SIZE = 1024
OUT = Path(__file__).resolve().parents[1] / "src-tauri" / "icons" / "icon-1024.png"

# colors
INDIGO_TOP = (99, 102, 241)
INDIGO_BOTTOM = (67, 56, 202)
WHITE = (255, 255, 255)
INDIGO = (79, 70, 229)


def inside_rounded_rect(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    dx = x - cx
    dy = y - cy
    return dx * dx + dy * dy <= r * r


def lerp(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build() -> bytes:
    rows = []
    for y in range(SIZE):
        row = bytearray([0])  # filter type 0
        for x in range(SIZE):
            color = (0, 0, 0, 0)
            if inside_rounded_rect(x + 0.5, y + 0.5, 32, 32, SIZE - 32, SIZE - 32, 232):
                t = y / SIZE
                color = (*lerp(INDIGO_TOP, INDIGO_BOTTOM, t), 255)
                # white document card
                if inside_rounded_rect(x + 0.5, y + 0.5, 300, 250, 724, 690, 44):
                    color = (*WHITE, 255)
                    # folded corner (top-right)
                    fx = x - 640
                    fy = 354 - y
                    if 640 <= x <= 724 and 250 <= y <= 354 and fx + fy >= 0:
                        color = (224, 231, 255, 255)
                    # text lines
                    for ly in (360, 448, 536):
                        if ly <= y <= ly + 40:
                            margin_right = 120 if ly == 536 else 524
                            if 372 <= x <= 724 - margin_right:
                                color = (*INDIGO, 255)
                # export arrow badge (bottom-right circle)
                dx = x - 700
                dy = y - 700
                if dx * dx + dy * dy <= 150 * 150:
                    color = (*WHITE, 255)
                    # arrow: shaft then two wing triangles
                    if 660 <= x <= 740 and 620 <= y <= 700:
                        color = (*INDIGO, 255)
                    if 620 <= x <= 780 and 690 <= y <= 790:
                        wl = (y - 690) * 1.0
                        if abs(x - 700) <= 80 - (y - 690) and y >= 690:
                            color = (*INDIGO, 255)
                        _ = wl
            row.extend(color)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">8B", 137, 80, 78, 71, 13, 10, 26, 10)
    ihdr = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)  # RGBA
    return (
        header
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
