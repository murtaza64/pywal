"""wal-palette/1 contract guarantees consumers rely on."""

import glob
import json
import os
import unittest
from pathlib import Path

from pywal import contract

THEMES = sorted(glob.glob(os.path.join(os.path.dirname(contract.__file__), "colorschemes", "*", "*.json")))


def as_colors_json(path):
    """Builtin themes carry only color0-15; give them the named slots the fork exports."""
    data = json.loads(Path(path).read_text())
    c = dict(data["colors"])
    for i, n in enumerate(contract.ANSI):
        c.setdefault(n, c[f"color{i}"])
        c.setdefault(f"bright_{n}", c[f"color{i + 8}"])
    return {"special": data["special"], "colors": c, "wallpaper": "/home/someone/private.png"}


class TestContract(unittest.TestCase):
    def test_text_roles_meet_4_5_and_graphics_3_on_surface_for_every_builtin_theme(self):
        failures = []
        for path in THEMES:
            checks = contract.build(as_colors_json(path))["checks"]
            if checks["text_min"] < 4.5 or checks["graphic_min"] < 3:
                failures.append((os.path.basename(path), checks))
        self.assertEqual(failures, [])

    def test_ok_and_risk_stay_apart_under_colour_vision_deficiency_or_are_flagged(self):
        flagged = []
        for path in THEMES:
            checks = contract.build(as_colors_json(path))["checks"]
            self.assertEqual(checks["ok_risk_cvd_safe"], checks["ok_risk_cvd"] >= contract.CVD_MINIMUM)
            if not checks["ok_risk_cvd_safe"]:
                flagged.append(os.path.basename(path))
        # 2 of 271 builtin themes have surfaces too mid-grey for any readable separated pair.
        self.assertLessEqual(len(flagged), 2, flagged)

    def test_contract_never_carries_the_wallpaper_path(self):
        built = contract.build(as_colors_json(THEMES[0]))
        self.assertNotIn("private.png", json.dumps(built))

    def test_revision_changes_with_colours_and_only_with_colours(self):
        a = contract.build(as_colors_json(THEMES[0]))
        self.assertEqual(a["revision"], contract.build(as_colors_json(THEMES[0]))["revision"])
        self.assertNotEqual(a["revision"], contract.build(as_colors_json(THEMES[1]))["revision"])

    def test_inject_is_idempotent_and_replaces_the_previous_palette(self):
        first = contract.build(as_colors_json(THEMES[0]))
        second = contract.build(as_colors_json(THEMES[1]))
        page = "<html><head><title>x</title></head><body></body></html>"
        once = contract.inject(page, first)
        twice = contract.inject(contract.inject(once, first), second)
        self.assertEqual(twice.count('id="wal-palette"'), 1)
        self.assertIn(second["revision"], twice)
        self.assertNotIn(first["revision"], twice)

    def test_css_exposes_namespaced_and_brief_role_names(self):
        css = contract.css(contract.build(as_colors_json(THEMES[0])))
        for name in ("--wal-accent:", "--wal-hl8:", "--accent:var(--wal-accent)", "--risk:var(--wal-risk)", "--hl1:var(--wal-hl1)"):
            self.assertIn(name, css)

    def test_hl1_to_hl4_stay_apart_under_every_simulated_vision_or_are_flagged(self):
        flagged = []
        for path in THEMES:
            checks = contract.build(as_colors_json(path))["checks"]
            self.assertEqual(checks["hl_distinct_safe"], checks["hl_distinct"] >= contract.HL_DISTINCT)
            if not checks["hl_distinct_safe"]:
                flagged.append(os.path.basename(path))
        # Mid-grey dark surfaces leave too little lightness room for four rungs.
        self.assertLessEqual(len(flagged), 2, flagged)

    def test_highlight_fills_keep_body_text_at_7_or_fall_back_to_surface(self):
        for path in THEMES:
            built = contract.build(as_colors_json(path))
            roles = built["roles"]
            for i in range(1, 5):
                fill = roles[f"hl{i}_bg"]
                self.assertTrue(contract.contrast(roles["fg"], fill) >= 7 or fill == roles["surface"], (os.path.basename(path), i, fill))

    def test_hl1_takes_the_first_generated_hue(self):
        colours = as_colors_json(THEMES[0])
        first = next(colours["colors"][f"color{i}"] for i in range(8) if contract.oklch(colours["colors"][f"color{i}"])[1] >= 0.04)
        hl1 = contract.build(colours)["highlights"][0]
        self.assertLess(contract.hue_gap(contract.oklch(hl1)[2], contract.oklch(first)[2]), 3)

    def test_fork_palette_vector(self):
        """Golden output for a real fork palette (hades-2-mel, subtractive, colorthief)."""
        built = contract.build(HADES)
        self.assertEqual(built["highlights"][:4], ["#89b1fc", "#f23e86", "#2ffb86", "#a6560b"])
        self.assertEqual([built["roles"][f"hl{i}_bg"] for i in range(1, 5)], HADES_HL_BG)
        self.assertGreaterEqual(built["checks"]["hl_distinct"], contract.HL_DISTINCT)


HADES = {
    "special": {"background": "#000001", "foreground": "#c4dee5", "cursor": "#c4dee5"},
    "colors": {
        **{f"color{i}": c for i, c in enumerate(["#3159a9", "#3763c9", "#59bee7", "#3a5c9d", "#a5526c", "#42b76b", "#7a553c", "#213dff",
                                                   "#6a87bf", "#8097c9", "#97c1d2", "#6786be", "#c6798f", "#6dc188", "#b3764f", "#8496cb"])},
        "black": "#000001", "red": "#a5526c", "green": "#42b76b", "yellow": "#847500", "blue": "#213dff", "magenta": "#3763c9", "cyan": "#59bee7", "white": "#abdce8",
        "bright_black": "#3c4149", "bright_red": "#c6798f", "bright_green": "#6dc188", "bright_yellow": "#998d42", "bright_blue": "#8496cb",
        "bright_magenta": "#8097c9", "bright_cyan": "#97c1d2", "bright_white": "#c4dee5",
        **{f"surface{i}": c for i, c in enumerate(["#02050c", "#10151f", "#242933", "#383e49", "#4e5460", "#656c78"])},
    },
}
HADES_HL_BG = ["#32415d", "#54213e", "#174c38", "#3d2819"]


if __name__ == "__main__":
    unittest.main()
