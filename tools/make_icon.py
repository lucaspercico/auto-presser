"""Gera assets/icon.ico (formato clássico BMP) e icon.png para o Auto Presser."""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets"
OUT.mkdir(exist_ok=True)

BG = (12, 14, 20, 255)
PANEL = (20, 24, 32, 255)
ACCENT = (76, 141, 255, 255)
KEY = (34, 42, 58, 255)
KEY_MUTED = (48, 56, 74, 255)
WHITE = (238, 242, 250, 255)


def rr(draw: ImageDraw.ImageDraw, xy, r, fill) -> None:
    draw.rounded_rectangle(xy, radius=r, fill=fill)


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 32)
    r = max(4, size // 5)
    rr(d, (pad, pad, size - pad - 1, size - pad - 1), r, BG)
    inset = max(2, size // 10)
    rr(d, (inset, inset, size - inset - 1, size - inset - 1), max(3, r - inset // 2), PANEL)

    kb_l, kb_t = size * 0.18, size * 0.26
    kb_r, kb_b = size * 0.82, size * 0.60
    rr(d, (kb_l, kb_t, kb_r, kb_b), max(2, size // 16), KEY)

    cols, rows = 3, 2
    margin = size * 0.04
    gap = size * 0.025
    usable_w = (kb_r - kb_l) - 2 * margin
    usable_h = (kb_b - kb_t) - 2 * margin
    kw = (usable_w - gap * (cols - 1)) / cols
    kh = (usable_h - gap * (rows - 1)) / rows
    for row in range(rows):
        for col in range(cols):
            x0 = kb_l + margin + col * (kw + gap)
            y0 = kb_t + margin + row * (kh + gap)
            fill = ACCENT if (row == 1 and col == 1) else KEY_MUTED
            rr(d, (x0, y0, x0 + kw, y0 + kh), max(2, size // 28), fill)

    cx, cy = size * 0.72, size * 0.76
    rad = size * 0.12
    d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=ACCENT)
    ir = rad * 0.32
    d.ellipse(
        (cx - ir, cy - ir - rad * 0.12, cx + ir, cy + ir - rad * 0.12),
        fill=WHITE,
    )
    return img


def _bmp_xor_and(im: Image.Image) -> bytes:
    """Bitmap XOR (BGRA, bottom-up) + AND mask para entrada ICO clássica."""
    im = im.convert("RGBA")
    w, h = im.size
    pixels = im.load()

    xor = bytearray()
    for y in range(h - 1, -1, -1):
        row = bytearray()
        for x in range(w):
            r, g, b, a = pixels[x, y]
            row += bytes((b, g, r, a))
        # rows already 4-byte aligned for width*4
        xor += row

    # AND mask: 1 bit per pixel, padded to 32-bit rows
    row_bytes = ((w + 31) // 32) * 4
    and_mask = bytearray(row_bytes * h)
    for y in range(h):
        src_y = h - 1 - y
        for x in range(w):
            _r, _g, _b, a = pixels[x, src_y]
            if a < 128:
                byte_i = y * row_bytes + (x // 8)
                and_mask[byte_i] |= 0x80 >> (x % 8)

    header = struct.pack(
        "<IIIHHIIIIII",
        40,  # biSize
        w,
        h * 2,  # height includes AND mask
        1,  # planes
        32,  # bit count
        0,  # BI_RGB
        len(xor),
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor) + bytes(and_mask)


def write_ico(path: Path, images: list[Image.Image], sizes: list[int]) -> None:
    """ICO clássico (DIB) — compatível com ícone de .exe no Windows Explorer."""
    entries: list[tuple[int, bytes]] = []
    for im, s in zip(images, sizes):
        entries.append((s, _bmp_xor_and(im)))

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    blobs = b""
    for s, data in entries:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        directory += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    path.write_bytes(header + directory + blobs)


def main() -> None:
    # 256 às vezes falha em alguns toolchains; 16–128 cobre Explorer/taskbar
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [make_icon(s) for s in sizes]
    ico = OUT / "icon.ico"
    write_ico(ico, images, sizes)
    make_icon(64).save(OUT / "icon.png")
    print(f"OK {ico} ({ico.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
