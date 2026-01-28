#!/usr/bin/env -S uv run --script

"""Visualize ANSI hue acceptance/misclassification.

This prints synthetic colors across OKLCH (L, C, hue) and shows:
- which ANSI target `pywal.match.get_closest_target()` chooses (OKLab distance)
- whether the hue is within that target's tolerance (for red/yellow/green/blue)

Goal: spot cases like "looks yellow but chosen as green".
"""

from __future__ import annotations

import argparse
import math

from pywal.color import Color
from pywal import match
from pywal import oklab


RESET = "\033[0m"


def _square(c: Color, width: int = 2) -> str:
    r, g, b = c.rgb8
    return f"\033[48;2;{r};{g};{b}m" + (" " * width) + RESET


def _hdeg(c: Color) -> float:
    return (c.oklch.h_rad * 180.0 / math.pi) % 360.0


def _norm_rad(h: float) -> float:
    return h % (2.0 * math.pi)


def _circle_dist_deg(a_deg: float, b_deg: float) -> float:
    d = abs(a_deg - b_deg) % 360.0
    return min(d, 360.0 - d)


def _target_hdeg(name: str) -> float:
    return (match.TARGET_OKLCH_HUE_RAD[name] * 180.0 / math.pi) % 360.0


def _nearest_target_by_hue(c: Color) -> str:
    h = _hdeg(c)
    return min(match.TARGET_HUES, key=lambda k: _circle_dist_deg(h, _target_hdeg(k)))


def _within_tolerance(target: str, c: Color) -> bool:
    if target not in match.HUE_TOLERANCES:
        return True
    tol_deg = match.HUE_TOLERANCES[target] * 360.0
    return _circle_dist_deg(_hdeg(c), _target_hdeg(target)) <= tol_deg


def _target_tag(name: str) -> str:
    return {
        "red": "R",
        "yellow": "Y",
        "green": "G",
        "cyan": "C",
        "blue": "B",
        "magenta": "M",
    }[name]


def _fmt_case(target: str, c: Color) -> str:
    chosen = match.get_closest_target(c)
    nearest = _nearest_target_by_hue(c)
    ok = _within_tolerance(target, c)
    dist = _circle_dist_deg(_hdeg(c), _target_hdeg(target))
    return (
        f"{_square(c)}{_square(c)} {c.hex_color} "
        f"L={c.oklch.L:.3f} C={c.oklch.C:.3f} h={_hdeg(c):6.1f} "
        f"dist_to_{target}={dist:5.1f} "
        f"nearest_hue={nearest:<7} chosen_oklab={chosen:<7} "
        f"tol={'ok' if ok else 'NO'}"
    )


def _generate_samples(
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
        hr = _norm_rad(h * math.pi / 180.0)
        for L in Ls:
            for C in Cs:
                out.append(Color.from_oklch(oklab.OKLCH(L=L, C=C, h_rad=hr)))
        h += h_step_deg
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=list(match.TARGET_HUES.keys()) + ["all"], default="all")
    ap.add_argument("--max", type=int, default=80, help="Max lines per section")
    ns = ap.parse_args(argv)

    Ls = [0.25, 0.38, 0.52, 0.66, 0.80]
    Cs = [0.02, 0.04, 0.06, 0.09, 0.12, 0.16, 0.22]

    targets = list(match.TARGET_HUES.keys()) if ns.target == "all" else [ns.target]

    print("Match Hue Acceptance Demo")
    print(f"targets: {', '.join(targets)}")
    print(f"Ls={Ls}")
    print(f"Cs={Cs}")
    print()

    for target in targets:
        tdeg = _target_hdeg(target)
        tol_deg = match.HUE_TOLERANCES.get(target)
        tol_deg = (tol_deg * 360.0) if tol_deg is not None else None

        window = 120.0
        samples = _generate_samples(
            h_start_deg=tdeg - window,
            h_end_deg=tdeg + window,
            h_step_deg=10.0,
            Ls=Ls,
            Cs=Cs,
        )

        # Focus on colors you'd likely describe as the target by hue, but OKLab picks something else.
        confusions: list[tuple[float, Color]] = []
        for c in samples:
            nearest = _nearest_target_by_hue(c)
            chosen = match.get_closest_target(c)
            if nearest != target:
                continue
            if chosen == target:
                continue
            dist = _circle_dist_deg(_hdeg(c), tdeg)
            confusions.append((dist, c))
        confusions.sort(key=lambda x: x[0])

        # Also show the stuff the tolerance would accept for this target.
        accepted: list[tuple[float, Color]] = []
        for c in samples:
            if not _within_tolerance(target, c):
                continue
            dist = _circle_dist_deg(_hdeg(c), tdeg)
            accepted.append((dist, c))
        accepted.sort(key=lambda x: x[0])

        # Potential "looks like X but would pass tolerance for target" cases.
        misaccepted: list[tuple[float, Color]] = []
        for c in samples:
            if not _within_tolerance(target, c):
                continue
            nearest = _nearest_target_by_hue(c)
            if nearest == target:
                continue
            dist = _circle_dist_deg(_hdeg(c), tdeg)
            misaccepted.append((dist, c))
        misaccepted.sort(key=lambda x: x[0])

        print(f"== {target} ({_target_tag(target)})")
        print(f"target_h={tdeg:.1f}deg" + (f" tol={tol_deg:.1f}deg" if tol_deg is not None else ""))
        print(f"confusions: nearest_hue={target} but chosen_oklab!= {target}")
        for _d, c in confusions[: ns.max]:
            print("  " + _fmt_case(target, c))
        if not confusions:
            print("  (none in this synthetic slice)")
        print()

        print(f"tolerance-accepted hues for {target} (regardless of chosen_oklab)")
        for _d, c in accepted[: ns.max]:
            chosen = match.get_closest_target(c)
            mark = "*" if chosen == target else f"({ _target_tag(chosen) })"
            print("  " + mark + " " + _fmt_case(target, c))
        print()

        print(f"tolerance-accepted but nearest_hue!= {target}")
        for _d, c in misaccepted[: ns.max]:
            nearest = _nearest_target_by_hue(c)
            chosen = match.get_closest_target(c)
            print(
                "  "
                + f"[{nearest}->{target}] "
                + f"{_target_tag(nearest)}->{_target_tag(target)} "
                + f"{_target_tag(chosen)} "
                + _fmt_case(target, c)
            )
        if not misaccepted:
            print("  (none)")
        print()

    # A dedicated sweep around yellow/green boundary since that's the common complaint.
    if ns.target in ("all", "yellow", "green"):
        print("== yellow-green sweep")
        print("h=40..140deg at higher chroma, multiple L")
        sweep = _generate_samples(
            h_start_deg=40.0,
            h_end_deg=140.0,
            h_step_deg=5.0,
            Ls=[0.35, 0.50, 0.65],
            Cs=[0.08, 0.12, 0.16, 0.22],
        )
        lines = 0
        for c in sweep:
            nearest = _nearest_target_by_hue(c)
            if nearest != "yellow":
                continue
            if not _within_tolerance("green", c):
                continue
            chosen = match.get_closest_target(c)
            print(
                "  "
                + f"{_square(c)}{_square(c)} {c.hex_color} h={_hdeg(c):6.1f} "
                + f"nearest_hue={nearest:<6} chosen_oklab={chosen:<7} "
                + f"dist_to_y={_circle_dist_deg(_hdeg(c), _target_hdeg('yellow')):5.1f} "
                + f"dist_to_g={_circle_dist_deg(_hdeg(c), _target_hdeg('green')):5.1f} "
                + "green_tol=ok"
            )
            lines += 1
            if lines >= ns.max:
                break
        if lines == 0:
            print("  (none)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
