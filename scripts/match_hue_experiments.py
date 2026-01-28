#!/usr/bin/env -S uv run --script

"""Try hue-classification tweaks without changing pywal.

This script generates synthetic OKLCH colors and compares:
- baseline: match.get_closest_target() (OKLab distance)
- hue-penalty: OKLab distance + k * OKLCH-hue-distance
- optional yellow gating: require minimum L/C for yellow

Use this to validate heuristics before touching `pywal/match.py`.
"""

from __future__ import annotations

import argparse
import math

from pywal import match
from pywal import oklab
from pywal.color import Color


RESET = "\033[0m"


def _square(c: Color, width: int = 2) -> str:
    r, g, b = c.rgb8
    return f"\033[48;2;{r};{g};{b}m" + (" " * width) + RESET


def _hdeg(c: Color) -> float:
    return (c.oklch.h_rad * 180.0 / math.pi) % 360.0


def _circle_dist_rad(a: float, b: float) -> float:
    d = abs(a - b) % (2.0 * math.pi)
    return min(d, 2.0 * math.pi - d)


def _oklab_dist(a: oklab.OKLab, b: oklab.OKLab) -> float:
    return ((a.L - b.L) ** 2 + (a.a - b.a) ** 2 + (a.b - b.b) ** 2) ** 0.5


def _baseline(c: Color) -> str:
    return match.get_closest_target(c)


def _nearest_target_by_oklch_hue(c: Color) -> str:
    h = float(c.oklch.h_rad)
    return min(match.TARGET_OKLCH_HUE_RAD, key=lambda t: _circle_dist_rad(h, match.TARGET_OKLCH_HUE_RAD[t]))


def _score_hue_penalty(c: Color, target: str, k: float) -> float:
    d_lab = _oklab_dist(c.oklab, match.TARGET_OKLAB[target])
    d_h = _circle_dist_rad(c.oklch.h_rad, match.TARGET_OKLCH_HUE_RAD[target])
    return d_lab + k * d_h


def classify_hue_penalty(c: Color, k: float) -> str:
    return min(match.TARGET_OKLAB.keys(), key=lambda t: _score_hue_penalty(c, t, k))


def classify_hue_penalty_with_yellow_gating(c: Color, k: float, yellow_min_L: float, yellow_min_C: float) -> str:
    def score(t: str) -> float:
        if t == "yellow":
            if c.oklch.L < yellow_min_L or c.oklch.C < yellow_min_C:
                return float("inf")
        return _score_hue_penalty(c, t, k)

    return min(match.TARGET_OKLAB.keys(), key=score)


def gen_oklch_grid(
    *,
    h_start_deg: float,
    h_end_deg: float,
    h_step_deg: float,
    Ls: list[float],
    Cs: list[float],
) -> list[Color]:
    out: list[Color] = []
    h = h_start_deg
    while h <= h_end_deg + 1e-9:
        hr = (h * math.pi / 180.0) % (2.0 * math.pi)
        for L in Ls:
            for C in Cs:
                out.append(Color.from_oklch(oklab.OKLCH(L=L, C=C, h_rad=hr)))
        h += h_step_deg
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=float, default=0.35, help="Hue penalty weight (radians)")
    ap.add_argument("--yellow-min-L", type=float, default=0.55)
    ap.add_argument("--yellow-min-C", type=float, default=0.06)
    ap.add_argument("--max", type=int, default=80)
    ap.add_argument(
        "--only-diff",
        action="store_true",
        help="Only print rows where a tweak changes classification",
    )
    ns = ap.parse_args(argv)

    print("Match Hue Experiments")
    print(f"k={ns.k}")
    print(f"yellow gating: L>={ns.yellow_min_L}, C>={ns.yellow_min_C}")
    print()

    # Focus areas that tend to be problematic.
    # Note: bands are in OKLCH hue degrees.
    red_center = (match.TARGET_OKLCH_HUE_RAD["red"] * 180.0 / math.pi) % 360.0
    yellow_center = (match.TARGET_OKLCH_HUE_RAD["yellow"] * 180.0 / math.pi) % 360.0
    green_center = (match.TARGET_OKLCH_HUE_RAD["green"] * 180.0 / math.pi) % 360.0

    cases = [
        ("red vicinity", red_center - 55.0, red_center + 55.0, 5.0, "red"),
        ("yellow vicinity", yellow_center - 55.0, yellow_center + 55.0, 5.0, "yellow"),
        ("yellow->green corridor", yellow_center - 20.0, green_center + 20.0, 5.0, None),
    ]
    Ls = [0.30, 0.42, 0.55, 0.68, 0.80]
    Cs = [0.03, 0.06, 0.09, 0.12, 0.16, 0.22]

    for title, a, b, step, focus in cases:
        print(f"== {title}")
        print(f"h={a:.1f}..{b:.1f}deg")
        grid = gen_oklch_grid(h_start_deg=a, h_end_deg=b, h_step_deg=step, Ls=Ls, Cs=Cs)

        if focus is not None and not ns.only_diff:
            # First: show a few representative samples whose *OKLCH hue* is closest to `focus`.
            reps = [c for c in grid if _nearest_target_by_oklch_hue(c) == focus and c.oklch.C >= 0.06]
            reps.sort(key=lambda c: _circle_dist_rad(c.oklch.h_rad, match.TARGET_OKLCH_HUE_RAD[focus]))
            print(f"representative (nearest_hue={focus}, C>=0.06)")
            for c in reps[: min(20, ns.max)]:
                base = _baseline(c)
                hp = classify_hue_penalty(c, ns.k)
                gated = classify_hue_penalty_with_yellow_gating(c, ns.k, ns.yellow_min_L, ns.yellow_min_C)
                nearest = _nearest_target_by_oklch_hue(c)
                print(
                    f"  {_square(c)}{_square(c)} {c.hex_color} "
                    f"L={c.oklch.L:.3f} C={c.oklch.C:.3f} h={_hdeg(c):6.1f} "
                    f"nearest_hue={nearest:<7} base={base:<7} huepen={hp:<7} gated={gated:<7}"
                )
            if not reps:
                print("  (none)")
            print()

            # Second: show misclassifications where hue suggests `focus` but baseline picks something else.
            wrong = [c for c in reps if _baseline(c) != focus]
            print(f"misclassified by baseline (nearest_hue={focus} but base!= {focus})")
            for c in wrong[: min(20, ns.max)]:
                base = _baseline(c)
                hp = classify_hue_penalty(c, ns.k)
                gated = classify_hue_penalty_with_yellow_gating(c, ns.k, ns.yellow_min_L, ns.yellow_min_C)
                print(
                    f"  {_square(c)}{_square(c)} {c.hex_color} "
                    f"L={c.oklch.L:.3f} C={c.oklch.C:.3f} h={_hdeg(c):6.1f} "
                    f"base={base:<7} huepen={hp:<7} gated={gated:<7}"
                )
            if not wrong:
                print("  (none)")
            print()

        shown = 0
        for c in grid:
            base = _baseline(c)
            hp = classify_hue_penalty(c, ns.k)
            gated = classify_hue_penalty_with_yellow_gating(c, ns.k, ns.yellow_min_L, ns.yellow_min_C)
            nearest = _nearest_target_by_oklch_hue(c)

            # Only print lines where a tweak changes the classification.
            if (base == hp and base == gated) and ns.only_diff:
                continue
            if (base == hp and base == gated) and (not ns.only_diff):
                continue

            print(
                f"  {_square(c)}{_square(c)} {c.hex_color} "
                f"L={c.oklch.L:.3f} C={c.oklch.C:.3f} h={_hdeg(c):6.1f} "
                f"nearest_hue={nearest:<7} base={base:<7} huepen={hp:<7} gated={gated:<7}"
            )
            shown += 1
            if shown >= ns.max:
                break

        if shown == 0:
            print("  (no differences at these settings)")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
