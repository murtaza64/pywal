"""Pure-Python port of the desktop quantizer, for the browser (Pyodide has no Rust wheel).

Desktop palettes come from `modern_colorthief` 0.1.7, which decodes with the Rust `image` crate and
runs color-thief-rs 0.2.2 (MIT, Reizner Evgeniy). This module reproduces that pipeline step for step,
including its sampling (every `channels * quality`-th pixel), its cut rules and its integer averages,
so the same pixels give the same palette. Pixels come from pywal.decoded: Pillow's, or the
browser's own decode where that matches the desktop's.
"""

import math

SIGBITS = 5
RSHIFT = 8 - SIGBITS
MULT = 1 << RSHIFT
VBOX_LENGTH = 1 << SIGBITS
FRACTION_BY_POPULATION = 0.75
MAX_ITERATIONS = 1000


def index(r, g, b):
    return (r << (2 * SIGBITS)) + (g << SIGBITS) + b


class VBox:
    __slots__ = ("r1", "r2", "g1", "g2", "b1", "b2", "average", "volume", "count")

    def __init__(self, r1, r2, g1, g2, b1, b2):
        self.r1, self.r2, self.g1, self.g2, self.b1, self.b2 = r1, r2, g1, g2, b1, b2

    def copy(self):
        v = VBox(self.r1, self.r2, self.g1, self.g2, self.b1, self.b2)
        v.average, v.volume, v.count = self.average, self.volume, self.count
        return v

    def recalc(self, hist):
        ntot = rs = gs = bs = 0
        for i in range(self.r1, self.r2 + 1):
            for j in range(self.g1, self.g2 + 1):
                base = index(i, j, 0)
                for k in range(self.b1, self.b2 + 1):
                    h = hist[base + k]
                    if h:
                        ntot += h
                        # Rust truncates each f64 product to i32 before summing.
                        rs += int(h * (i + 0.5) * MULT)
                        gs += int(h * (j + 0.5) * MULT)
                        bs += int(h * (k + 0.5) * MULT)
        if ntot:
            self.average = (rs // ntot, gs // ntot, bs // ntot)
        else:
            self.average = tuple(min(MULT * (lo + hi + 1) // 2, 255) for lo, hi in ((self.r1, self.r2), (self.g1, self.g2), (self.b1, self.b2)))
        self.count = ntot
        self.volume = (self.r2 - self.r1 + 1) * (self.g2 - self.g1 + 1) * (self.b2 - self.b1 + 1)

    def widest(self):
        rw, gw, bw = self.r2 - self.r1, self.g2 - self.g1, self.b2 - self.b1
        m = max(rw, gw, bw)
        return "r" if m == rw else "g" if m == gw else "b"


def histogram(pixels, channels, quality):
    """Histogram and bounding box of the sampled pixels; `pixels` is packed RGB or RGBA bytes."""
    hist = [0] * (1 << (3 * SIGBITS))
    step = channels * channels * quality  # Rust advances the pixel index by channels * quality
    r, g, b = pixels[0::step], pixels[1::step], pixels[2::step]
    a = pixels[3::step] if channels == 4 else None
    rmin = gmin = bmin = 255
    rmax = gmax = bmax = 0
    for n in range(len(b)):
        rv, gv, bv = r[n], g[n], b[n]
        if (a is not None and a[n] < 125) or (rv > 250 and gv > 250 and bv > 250):
            continue
        rv, gv, bv = rv >> RSHIFT, gv >> RSHIFT, bv >> RSHIFT
        rmin, rmax = min(rmin, rv), max(rmax, rv)
        gmin, gmax = min(gmin, gv), max(gmax, gv)
        bmin, bmax = min(bmin, bv), max(bmax, bv)
        hist[index(rv, gv, bv)] += 1
    box = VBox(rmin, rmax, gmin, gmax, bmin, bmax)
    box.recalc(hist)
    return box, hist


def median_cut(hist, box):
    if box.count == 0:
        raise ValueError("an invalid VBox")
    if box.count == 1:
        return box.copy(), None
    axis = box.widest()
    lo, hi = {"r": (box.r1, box.r2), "g": (box.g1, box.g2), "b": (box.b1, box.b2)}[axis]
    partial = [-1] * VBOX_LENGTH
    total = 0
    for i in range(lo, hi + 1):
        s = 0
        if axis == "r":
            for j in range(box.g1, box.g2 + 1):
                for k in range(box.b1, box.b2 + 1):
                    s += hist[index(i, j, k)]
        elif axis == "g":
            for j in range(box.r1, box.r2 + 1):
                for k in range(box.b1, box.b2 + 1):
                    s += hist[index(j, i, k)]
        else:
            for j in range(box.r1, box.r2 + 1):
                for k in range(box.g1, box.g2 + 1):
                    s += hist[index(j, k, i)]
        total += s
        partial[i] = total
    ahead = [total - p if p != -1 else -1 for p in partial]

    for i in range(lo, hi + 1):
        if partial[i] <= total // 2:
            continue
        left, right = i - lo, hi - i
        d2 = min(hi - 1, i + right // 2) if left <= right else max(lo, math.trunc((i - 1) - left / 2.0))
        while d2 < 0 or partial[d2] <= 0:
            d2 += 1
        count2 = ahead[d2]
        while count2 == 0 and d2 > 0 and partial[d2 - 1] > 0:
            d2 -= 1
            count2 = ahead[d2]
        b1, b2 = box.copy(), box.copy()
        setattr(b1, axis + "2", d2)
        setattr(b2, axis + "1", d2 + 1)
        b1.recalc(hist)
        b2.recalc(hist)
        return b1, b2
    raise ValueError("failed to cut a VBox")


def by_count(v):
    return v.count


def by_product(v):
    # Rust compares volume when counts tie, else count*volume. With equal nonzero counts the
    # product already orders by volume; only empty boxes need volume as a tiebreak.
    return v.count * v.volume, v.volume if v.count == 0 else 0


def iterate(queue, key, target, hist):
    color = 1
    for _ in range(MAX_ITERATIONS):
        if not queue:
            continue
        box = queue[-1]
        if box.count == 0:
            queue.sort(key=key)
            continue
        queue.pop()
        b1, b2 = median_cut(hist, box)
        queue.append(b1)
        if b2 is not None:
            queue.append(b2)
            color += 1
        queue.sort(key=key)
        if color >= target:
            break


def quantize(pixels, channels, quality=10, max_colors=10):
    assert 0 < quality <= 10 and max_colors > 1
    box, hist = histogram(pixels, channels, quality)
    pq = [box]
    target = math.ceil(FRACTION_BY_POPULATION * max_colors)
    iterate(pq, by_count, target, hist)
    pq.sort(key=by_product)
    iterate(pq, by_product, max_colors - len(pq), hist)
    pq.reverse()
    out = []
    for v in pq[:max_colors]:
        if v.average not in out:  # modern_colorthief dedupes, keeping first occurrences
            out.append(v.average)
    return out


def get_palette(img, color_count=10, quality=10):
    """modern_colorthief.get_palette for a path, reading pixels as pywal.colorthief.rgb_source does."""
    from .decoded import open_image

    with open_image(img) as im:
        im.load()
        alpha = "A" in im.getbands() or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if alpha else "RGB")
        return quantize(im.tobytes(), 4 if alpha else 3, quality, color_count)
