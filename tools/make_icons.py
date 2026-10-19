"""Generate the complete SoundDial icon set into assets/icons/.

  sounddial.svg                 master vector
  sounddial-{16..1024}.png      app icon rasters
  sounddial.png                 512 px convenience copy
  sounddial.icns                macOS
  sounddial.ico                 Windows
  tray-mono.png / tray-mono-muted.png / tray-mono@2x.png   tray glyphs (white)
  tray-template.png / @2x       macOS menu-bar template (black on transparent)
  tray-dark.png                 for light trays (black)

Only needs Pillow. Run:  python tools/make_icons.py
"""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- vector master
SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2A2A2E"/><stop offset="1" stop-color="#0E0E10"/>
    </linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#9A9A9F"/>
    </linearGradient>
  </defs>
  <rect x="64" y="64" width="896" height="896" rx="200" fill="url(#bg)"/>
  <rect x="64" y="64" width="896" height="896" rx="200" fill="none" stroke="#3A3A3E" stroke-width="6"/>
  <!-- dial arc -->
  <path d="M 294 706 A 290 290 0 1 1 650 706" fill="none" stroke="#3C3C40" stroke-width="56" stroke-linecap="round"/>
  <path d="M 294 706 A 290 290 0 1 1 512 182" fill="none" stroke="url(#ring)" stroke-width="56" stroke-linecap="round"/>
  <!-- knob -->
  <circle cx="472" cy="472" r="150" fill="#1A1A1D" stroke="#4A4A4F" stroke-width="8"/>
  <circle cx="472" cy="472" r="118" fill="#242428"/>
  <!-- pointer -->
  <rect x="460" y="342" width="24" height="96" rx="12" fill="#FFFFFF" transform="rotate(32 472 472)"/>
  <!-- level bars -->
  <rect x="690" y="620" width="52" height="150" rx="16" fill="#FFFFFF" opacity="0.55"/>
  <rect x="764" y="540" width="52" height="230" rx="16" fill="#FFFFFF" opacity="0.8"/>
  <rect x="838" y="440" width="52" height="330" rx="16" fill="#FFFFFF"/>
</svg>
"""


# ---------------------------------------------------------------- raster (Pillow)
def _arc_points(cx, cy, r, a0, a1, step=1.0):
    pts = []
    a = a0
    while a <= a1:
        pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
        a += step
    return pts



def _thick_arc_mask(W, cx, cy, r, w, a0, a1):
    """Clean anti-aliasable arc: annular sector + round caps, as an L mask."""
    m = Image.new("L", (W, W), 0)
    md = ImageDraw.Draw(m)
    ro, ri = r + w / 2, r - w / 2
    md.pieslice([cx - ro, cy - ro, cx + ro, cy + ro], a0, a1, fill=255)
    md.pieslice([cx - ri, cy - ri, cx + ri, cy + ri], a0 - 1, a1 + 1, fill=0)
    # cut everything outside the annulus cleanly
    for ang in (a0, a1):
        px, py = cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))
        md.ellipse([px - w / 2, py - w / 2, px + w / 2, py + w / 2], fill=255)
    return m


def _paint_arc(img, cx, cy, r, w, a0, a1, color):
    m = _thick_arc_mask(img.width, cx, cy, r, w, a0, a1)
    layer = Image.new("RGBA", img.size, color)
    img.paste(layer, (0, 0), m)

def render_app_icon(size: int) -> Image.Image:
    S = 8  # supersample
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = W / 1024.0
    # background with vertical gradient
    bg = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gd = ImageDraw.Draw(bg)
    for y in range(int(64 * u), int(960 * u)):
        t = (y - 64 * u) / (896 * u)
        c = (int(42 + (14 - 42) * t), int(42 + (14 - 42) * t), int(46 + (16 - 46) * t), 255)
        gd.line([(64 * u, y), (960 * u, y)], fill=c)
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([64 * u, 64 * u, 960 * u, 960 * u], radius=200 * u, fill=255)
    img.paste(bg, (0, 0), mask)
    d.rounded_rectangle([64 * u, 64 * u, 960 * u, 960 * u], radius=200 * u, outline=(58, 58, 62, 255), width=int(6 * u))
    # arc track + fill
    cx, cy, r = 472 * u, 472 * u, 290 * u
    w = int(56 * u)
    _paint_arc(img, cx, cy, r, w, 135, 405, (60, 60, 64, 255))
    # gradient fill arc: draw the arc shape into a mask, then paste a diagonal gradient through it
    amask = _thick_arc_mask(W, cx, cy, r, w, 135, 270)
    grad = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gp = grad.load()
    for yy in range(0, W, 4):
        for xx in range(0, W, 4):
            t = max(0.0, min(1.0, (xx + yy) / (2.0 * W)))
            g = int(255 + (154 - 255) * t)
            for dy in range(4):
                for dx in range(4):
                    if xx + dx < W and yy + dy < W:
                        gp[xx + dx, yy + dy] = (g, g, min(255, g + 5), 255)
    img.paste(grad, (0, 0), amask)
    # knob
    d.ellipse([cx - 150 * u, cy - 150 * u, cx + 150 * u, cy + 150 * u], fill=(26, 26, 29, 255), outline=(74, 74, 79, 255), width=int(8 * u))
    d.ellipse([cx - 118 * u, cy - 118 * u, cx + 118 * u, cy + 118 * u], fill=(36, 36, 40, 255))
    # pointer (rotated 32°)
    ang = math.radians(32)
    def rot(x, y):
        x, y = x - 472, y - 472
        return (cx + (x * math.cos(ang) - y * math.sin(ang)) * u, cy + (x * math.sin(ang) + y * math.cos(ang)) * u)
    p0, p1 = rot(472, 354), rot(472, 426)
    d.line([p0, p1], fill=(255, 255, 255, 255), width=int(24 * u))
    for p in (p0, p1):
        d.ellipse([p[0] - 12 * u, p[1] - 12 * u, p[0] + 12 * u, p[1] + 12 * u], fill=(255, 255, 255, 255))
    # level bars
    for x, y, h, a in ((690, 620, 150, 140), (764, 540, 230, 204), (838, 440, 330, 255)):
        d.rounded_rectangle([x * u, y * u, (x + 52) * u, (y + h) * u], radius=16 * u, fill=(255, 255, 255, a))
    return img.resize((size, size), Image.LANCZOS)


def render_tray(size: int, color=(255, 255, 255, 255), muted=False) -> Image.Image:
    S = 8
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = W / 24.0
    cx, cy, r = 9.5 * u, 11.5 * u, 6.2 * u
    w = int(2.1 * u)
    _paint_arc(img, cx, cy, r, w, 135, 405, color)
    d = ImageDraw.Draw(img)
    # pointer
    ang = math.radians(-50)
    p0 = (cx, cy)
    p1 = (cx + 3.6 * u * math.cos(ang), cy + 3.6 * u * math.sin(ang))
    d.line([p0, p1], fill=color, width=w)
    d.ellipse([p1[0] - w / 2, p1[1] - w / 2, p1[0] + w / 2, p1[1] + w / 2], fill=color)
    if muted:
        d.line([(cx - 8 * u, cy + 8 * u), (cx + 8 * u, cy - 8 * u)], fill=color, width=w)
    else:
        for i, h in enumerate((3.0, 5.0, 7.5)):
            x = 17.6 * u + i * 2.3 * u
            d.rounded_rectangle([x, 18.5 * u - h * u, x + 1.4 * u, 18.5 * u], radius=0.6 * u, fill=color)
    return img.resize((size, size), Image.LANCZOS)


def write_ico(images: list[Image.Image], path: Path) -> None:
    images[0].save(path, format="ICO", sizes=[(i.width, i.height) for i in images], append_images=images[1:])


def write_icns(images: dict[int, Image.Image], path: Path) -> None:
    """Minimal ICNS writer (PNG-encoded entries). Works on every modern macOS."""
    types = {16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07", 256: b"ic08", 512: b"ic09", 1024: b"ic10"}
    retina = {32: b"ic11", 64: b"ic12", 256: b"ic13", 512: b"ic14"}  # @2x of 16/32/128/256
    entries = b""
    import io
    for size, tag in types.items():
        if size in images:
            buf = io.BytesIO()
            images[size].save(buf, format="PNG")
            data = buf.getvalue()
            entries += tag + struct.pack(">I", 8 + len(data)) + data
    for size, tag in retina.items():
        if size in images:
            buf = io.BytesIO()
            images[size].save(buf, format="PNG")
            data = buf.getvalue()
            entries += tag + struct.pack(">I", 8 + len(data)) + data
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(entries)) + entries)


def main() -> None:
    (OUT / "sounddial.svg").write_text(SVG, encoding="utf-8")
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    rendered = {}
    for s in sizes:
        im = render_app_icon(s)
        rendered[s] = im
        im.save(OUT / f"sounddial-{s}.png")
    rendered[512].save(OUT / "sounddial.png")
    write_ico([rendered[s] for s in (16, 24, 32, 48, 64, 128, 256)], OUT / "sounddial.ico")
    write_icns(rendered, OUT / "sounddial.icns")
    # tray glyphs
    render_tray(22).save(OUT / "tray-mono.png")
    render_tray(44).save(OUT / "tray-mono@2x.png")
    render_tray(22, muted=True).save(OUT / "tray-mono-muted.png")
    render_tray(44, muted=True).save(OUT / "tray-mono-muted@2x.png")
    render_tray(22, (0, 0, 0, 255)).save(OUT / "tray-dark.png")
    render_tray(22, (0, 0, 0, 255)).save(OUT / "trayTemplate.png")
    render_tray(44, (0, 0, 0, 255)).save(OUT / "trayTemplate@2x.png")
    # preview sheet
    sheet = Image.new("RGBA", (1024 + 40 + 256 + 40 + 128 + 40 + 64 + 40 + 32 + 40 + 16 + 40, 1024 + 80), (245, 245, 247, 255))
    x = 20
    for s in (1024, 256, 128, 64, 32, 16):
        sheet.paste(rendered[s], (x, 20), rendered[s])
        x += s + 40
    tray_row = Image.new("RGBA", (260, 60), (30, 30, 30, 255))
    for i, name in enumerate(("tray-mono.png", "tray-mono-muted.png")):
        im = Image.open(OUT / name)
        tray_row.paste(im, (20 + i * 50, 19), im)
    sheet.paste(tray_row, (1024 + 60, 300))
    sheet.save(OUT / "icon-preview.png")
    # Tauri icon set (src-tauri/icons) from the same master
    tauri = ROOT / "src-tauri" / "icons"
    tauri.mkdir(parents=True, exist_ok=True)
    for name, sz in [("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256), ("icon.png", 512),
                     ("Square30x30Logo.png", 30), ("Square44x44Logo.png", 44), ("Square71x71Logo.png", 71),
                     ("Square89x89Logo.png", 89), ("Square107x107Logo.png", 107), ("Square142x142Logo.png", 142),
                     ("Square150x150Logo.png", 150), ("Square284x284Logo.png", 284), ("Square310x310Logo.png", 310),
                     ("StoreLogo.png", 50)]:
        rendered[1024].resize((sz, sz), Image.LANCZOS).save(tauri / name)
    import shutil
    shutil.copy(OUT / "sounddial.icns", tauri / "icon.icns")
    shutil.copy(OUT / "sounddial.ico", tauri / "icon.ico")
    shutil.copy(OUT / "trayTemplate@2x.png", tauri / "trayTemplate@2x.png")
    shutil.copy(OUT / "tray-mono.png", tauri / "tray-mono.png")
    print("tauri icons written to", tauri)
    print("icons written to", OUT)
    print(" ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
