from __future__ import annotations

import binascii
import math
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "confluence_sync_tool" / "assets"
SIZES = (16, 24, 32, 48, 64, 128, 256)


Color = tuple[int, int, int, int]
Point = tuple[float, float]


def rgba(value: str, alpha: int = 255) -> Color:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def lerp(a: Color, b: Color, t: float) -> Color:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))  # type: ignore[return-value]


class Canvas:
    def __init__(self, size: int, scale: int = 4) -> None:
        self.size = size
        self.scale = scale
        self.width = size * scale
        self.pixels = bytearray(self.width * self.width * 4)

    def unit(self, value: float) -> float:
        return value * self.width / 256

    def _blend(self, x: int, y: int, color: Color) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.width:
            return
        sr, sg, sb, sa_i = color
        if sa_i <= 0:
            return
        index = (y * self.width + x) * 4
        dr, dg, db, da_i = self.pixels[index : index + 4]
        sa = sa_i / 255
        da = da_i / 255
        out_a = sa + da * (1 - sa)
        if out_a <= 0:
            self.pixels[index : index + 4] = b"\x00\x00\x00\x00"
            return
        self.pixels[index] = round((sr * sa + dr * da * (1 - sa)) / out_a)
        self.pixels[index + 1] = round((sg * sa + dg * da * (1 - sa)) / out_a)
        self.pixels[index + 2] = round((sb * sa + db * da * (1 - sa)) / out_a)
        self.pixels[index + 3] = round(out_a * 255)

    def fill_circle(self, cx: float, cy: float, radius: float, color: Color) -> None:
        cx_px = self.unit(cx)
        cy_px = self.unit(cy)
        radius_px = self.unit(radius)
        left = max(0, math.floor(cx_px - radius_px))
        right = min(self.width, math.ceil(cx_px + radius_px))
        top = max(0, math.floor(cy_px - radius_px))
        bottom = min(self.width, math.ceil(cy_px + radius_px))
        radius_sq = radius_px * radius_px
        for y in range(top, bottom):
            dy = y + 0.5 - cy_px
            for x in range(left, right):
                dx = x + 0.5 - cx_px
                if dx * dx + dy * dy <= radius_sq:
                    self._blend(x, y, color)

    def fill_rounded_rect(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        radius: float,
        color: Color,
        end_color: Color | None = None,
    ) -> None:
        left_px = self.unit(left)
        top_px = self.unit(top)
        right_px = self.unit(right)
        bottom_px = self.unit(bottom)
        radius_px = self.unit(radius)
        x0 = max(0, math.floor(left_px))
        x1 = min(self.width, math.ceil(right_px))
        y0 = max(0, math.floor(top_px))
        y1 = min(self.width, math.ceil(bottom_px))
        for y in range(y0, y1):
            py = y + 0.5
            for x in range(x0, x1):
                px = x + 0.5
                nearest_x = min(max(px, left_px + radius_px), right_px - radius_px)
                nearest_y = min(max(py, top_px + radius_px), bottom_px - radius_px)
                dx = px - nearest_x
                dy = py - nearest_y
                if dx * dx + dy * dy <= radius_px * radius_px:
                    if end_color is None:
                        fill = color
                    else:
                        tx = (px - left_px) / max(1, right_px - left_px)
                        ty = (py - top_px) / max(1, bottom_px - top_px)
                        fill = lerp(color, end_color, (tx + ty) / 2)
                    self._blend(x, y, fill)

    def fill_polygon(self, points: list[Point], color: Color) -> None:
        px_points = [(self.unit(x), self.unit(y)) for x, y in points]
        min_y = max(0, math.floor(min(y for _, y in px_points)))
        max_y = min(self.width, math.ceil(max(y for _, y in px_points)))
        for y in range(min_y, max_y):
            scan_y = y + 0.5
            intersections: list[float] = []
            for index, (x1, y1) in enumerate(px_points):
                x2, y2 = px_points[(index + 1) % len(px_points)]
                if (y1 <= scan_y < y2) or (y2 <= scan_y < y1):
                    ratio = (scan_y - y1) / (y2 - y1)
                    intersections.append(x1 + ratio * (x2 - x1))
            intersections.sort()
            for left, right in zip(intersections[0::2], intersections[1::2]):
                x0 = max(0, math.floor(left))
                x1 = min(self.width, math.ceil(right))
                for x in range(x0, x1):
                    self._blend(x, y, color)

    def draw_capsule(self, start: Point, end: Point, width: float, color: Color) -> None:
        x1, y1 = self.unit(start[0]), self.unit(start[1])
        x2, y2 = self.unit(end[0]), self.unit(end[1])
        radius = self.unit(width) / 2
        min_x = max(0, math.floor(min(x1, x2) - radius))
        max_x = min(self.width, math.ceil(max(x1, x2) + radius))
        min_y = max(0, math.floor(min(y1, y2) - radius))
        max_y = min(self.width, math.ceil(max(y1, y2) + radius))
        vx = x2 - x1
        vy = y2 - y1
        length_sq = vx * vx + vy * vy
        for y in range(min_y, max_y):
            py = y + 0.5
            for x in range(min_x, max_x):
                px = x + 0.5
                if length_sq == 0:
                    distance_sq = (px - x1) ** 2 + (py - y1) ** 2
                else:
                    t = max(0, min(1, ((px - x1) * vx + (py - y1) * vy) / length_sq))
                    nx = x1 + t * vx
                    ny = y1 + t * vy
                    distance_sq = (px - nx) ** 2 + (py - ny) ** 2
                if distance_sq <= radius * radius:
                    self._blend(x, y, color)

    def draw_arc(
        self,
        center: Point,
        radius: float,
        start_degrees: float,
        end_degrees: float,
        width: float,
        color: Color,
    ) -> None:
        steps = max(8, math.ceil(abs(end_degrees - start_degrees) / 6))
        points: list[Point] = []
        for step in range(steps + 1):
            angle = math.radians(start_degrees + (end_degrees - start_degrees) * step / steps)
            points.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius))
        for start, end in zip(points, points[1:]):
            self.draw_capsule(start, end, width, color)
        self._draw_arrowhead(points[-2], points[-1], width * 2.05, color)

    def _draw_arrowhead(self, previous: Point, end: Point, size: float, color: Color) -> None:
        dx = end[0] - previous[0]
        dy = end[1] - previous[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return
        ux = dx / length
        uy = dy / length
        nx = -uy
        ny = ux
        base_x = end[0] - ux * size
        base_y = end[1] - uy * size
        wing = size * 0.68
        self.fill_polygon(
            [
                end,
                (base_x + nx * wing, base_y + ny * wing),
                (base_x - nx * wing, base_y - ny * wing),
            ],
            color,
        )

    def downsample(self) -> bytes:
        result = bytearray(self.size * self.size * 4)
        block = self.scale * self.scale
        for y in range(self.size):
            for x in range(self.size):
                total = [0, 0, 0, 0]
                for sy in range(self.scale):
                    for sx in range(self.scale):
                        source = ((y * self.scale + sy) * self.width + (x * self.scale + sx)) * 4
                        for channel in range(4):
                            total[channel] += self.pixels[source + channel]
                target = (y * self.size + x) * 4
                for channel in range(4):
                    result[target + channel] = round(total[channel] / block)
        return bytes(result)


def render(size: int) -> bytes:
    canvas = Canvas(size)
    canvas.fill_rounded_rect(24, 24, 232, 232, 46, rgba("#0f5bd8"), rgba("#0f766e"))
    canvas.fill_circle(72, 59, 42, rgba("#ffffff", 34))
    canvas.fill_rounded_rect(39, 33, 219, 226, 37, rgba("#ffffff", 22))

    canvas.fill_rounded_rect(66, 54, 169, 207, 14, rgba("#031b4e", 55))
    canvas.fill_rounded_rect(58, 45, 161, 197, 14, rgba("#f8fafc"))
    canvas.fill_polygon([(130, 45), (161, 76), (130, 76)], rgba("#dbeafe"))
    canvas.fill_polygon([(130, 45), (161, 76), (148, 78), (130, 60)], rgba("#bfdbfe", 170))
    canvas.fill_rounded_rect(75, 88, 129, 99, 5, rgba("#2563eb"))
    canvas.fill_rounded_rect(75, 115, 145, 125, 5, rgba("#94a3b8"))
    canvas.fill_rounded_rect(75, 139, 137, 149, 5, rgba("#94a3b8"))
    canvas.fill_rounded_rect(75, 163, 119, 173, 5, rgba("#94a3b8"))

    canvas.fill_circle(175, 179, 53, rgba("#031b4e", 58))
    canvas.fill_circle(175, 175, 52, rgba("#ffffff", 245))
    canvas.fill_circle(175, 175, 45, rgba("#14b8a6"))
    canvas.fill_circle(160, 158, 19, rgba("#5eead4", 100))
    canvas.draw_arc((175, 176), 24, 170, 350, 8, rgba("#ffffff"))
    canvas.draw_arc((175, 176), 24, 350, 530, 8, rgba("#ffffff"))
    return canvas.downsample()


def png_chunk(name: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", binascii.crc32(name + data) & 0xFFFFFFFF)


def png_bytes(size: int, pixels: bytes) -> bytes:
    raw = bytearray()
    row_stride = size * 4
    for y in range(size):
        raw.append(0)
        raw.extend(pixels[y * row_stride : (y + 1) * row_stride])
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)),
            png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
            png_chunk(b"IEND", b""),
        ]
    )


def ico_bytes(images: dict[int, bytes]) -> bytes:
    sizes = sorted(images)
    header = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + len(sizes) * 16
    image_data = bytearray()
    for size in sizes:
        data = images[size]
        width = 0 if size == 256 else size
        header.extend(struct.pack("<BBBBHHII", width, width, 0, 0, 1, 32, len(data), offset))
        image_data.extend(data)
        offset += len(data)
    return bytes(header + image_data)


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    images: dict[int, bytes] = {}
    for size in SIZES:
        png = png_bytes(size, render(size))
        images[size] = png
        (ASSET_DIR / f"app-{size}.png").write_bytes(png)
    (ASSET_DIR / "app.ico").write_bytes(ico_bytes(images))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
