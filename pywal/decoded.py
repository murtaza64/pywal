"""Images whose pixels were decoded outside Pillow, by path.

The palette depends on exact pixel values, and JPEG decoders differ by a level here and there. The
desktop reads pixels through Pillow (libjpeg-turbo). Pyodide's Pillow is built on IJG libjpeg, but
the browser's own decoder (Chromium: libjpeg-turbo) matches the desktop, so the browser hands its
pixels over and generation reads them from here.
"""

PIXELS = {}


def open_image(path):
    """The image at `path`: its registered pixels if any, else Pillow's decode."""
    from PIL import Image

    if path in PIXELS:
        return PIXELS[path].copy()
    return Image.open(path)


def register(path, width, height, rgba):
    """Use `rgba` (packed, straight alpha) for `path` if it is the same picture Pillow sees.

    Returns whether it was kept. A browser may apply EXIF orientation or colour management that
    Pillow does not; those decodes are refused, so the palette falls back to Pillow's pixels.
    """
    from PIL import Image, ImageChops, ImageStat

    PIXELS.pop(path, None)
    img = Image.frombytes("RGBA", (width, height), bytes(rgba))
    with Image.open(path) as ref:
        if ref.size != img.size:
            return False
        alpha = "A" in ref.getbands() or (ref.mode == "P" and "transparency" in ref.info)
        ref = ref.convert("RGBA" if alpha else "RGB")
    img = img if alpha else img.convert("RGB")
    if max(ImageStat.Stat(ImageChops.difference(img, ref)).mean) > 2:
        return False
    PIXELS[path] = img
    return True
