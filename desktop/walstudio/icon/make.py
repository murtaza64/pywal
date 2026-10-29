"""WalStudio icon: wallpaper glass over the palette it yields (8-cell band).
Darkroom language: hard-edged shapes, one tinted dark field, colour only where it carries meaning.
The glass is drawn as the studio's blur ladder: three hard-edged opaque steps, not a gradient.
Outer squircle = macOS platform shape (named exception); everything inside is square.
16/32 px drop the terminal lines and use a 4-cell band so the mark survives at Dock/menu sizes.
Run: uv run --with pillow python desktop/walstudio/icon/make.py && iconutil -c icns desktop/walstudio/icon/WalStudio.iconset"""
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).parent
S, M = 1024, 100
T = S - 2 * M
# Fixed reference palette (the mark must not depend on the user's theme). Saturated, manadj-like;
# neutrals are tinted toward the field hue instead of grey.
FIELD = "#0d1a24"     # tinted near-black (OKLCH ~0.2 / 0.04 / 235)
INK = "#dcecf2"       # cool off-white, tinted to the field
BAND = ["#0d1a24", "#ff4f6d", "#3ee08a", "#ffc93d", "#4a9eff", "#c06bff", "#2fd4e6", "#dcecf2"]
LADDER = ["#0b3d52", "#085f7d", "#0a86a8"]  # OKLCH hue ~225, L 0.33/0.43/0.55, chroma rising
SMALL_BAND = ["#ff4f6d", "#3ee08a", "#ffc93d", "#4a9eff"]


def tile(small):
    t = Image.new("RGBA", (T, T), FIELD)
    d = ImageDraw.Draw(t, "RGBA")
    # Blur ladder: three hard-edged opaque steps of one saturated hue (lighter = less darkened glass).
    for i, c in enumerate(LADDER):
        d.rectangle([T * (0.34 + i * 0.16), 0, T, T * 0.8], fill=c)
    if not small:
        y0, lh, lw = T * 0.16, T * 0.075, T * 0.03
        for i, (w, c) in enumerate([(0.30, "#3ee08a"), (0.52, INK), (0.40, INK), (0.18, "#ffc93d")]):
            d.rectangle([T * 0.12, y0 + i * lh, T * (0.12 + w), y0 + i * lh + lw], fill=c)
        d.rectangle([T * 0.12, y0 + 4 * lh, T * 0.16, y0 + 4 * lh + lw * 1.6], fill=INK)
    band = SMALL_BAND if small else BAND
    by = T * (0.58 if small else 0.8)
    for i, c in enumerate(band):
        d.rectangle([i * T / len(band), by, (i + 1) * T / len(band), T], fill=c)
    return t


def icon(small):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (T, T), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, T - 1, T - 1], radius=int(T * 0.225), fill=255)
    img.paste(tile(small), (M, M), mask)
    return img


big, small = icon(False), icon(True)
big.save(HERE / "walstudio-1024.png")
iconset = HERE / "WalStudio.iconset"
iconset.mkdir(exist_ok=True)
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        px = size * scale
        (small if px <= 32 else big).resize((px, px), Image.LANCZOS).save(iconset / f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png")
print(HERE / "walstudio-1024.png")
