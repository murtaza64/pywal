"""Build the static browser export site into site/dist.

engine.zip carries the fork's palette pipeline and exporters (no Studio server, no builtin themes),
walexport.py, and the pure-Python colorthief port (BSD, Shipeng Feng; header kept) that Pyodide uses
in place of the modern_colorthief Rust wheel.
Run: uv run python site/build.py
"""

import shutil
import zipfile
from pathlib import Path

import colorthief

SITE = Path(__file__).parent
ROOT = SITE.parent
DIST = SITE / "dist"
SKIP = {"studio", "colorschemes", "__pycache__"}

shutil.rmtree(DIST, ignore_errors=True)
DIST.mkdir()
for name in ("index.html", "app.js", "worker.js", "style.css"):
    shutil.copy(SITE / name, DIST / name)
shutil.copy(ROOT / "desktop/walstudio/icon/walstudio-1024.png", DIST / "icon.png")

with zipfile.ZipFile(DIST / "engine.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted((ROOT / "pywal").rglob("*")):
        rel = path.relative_to(ROOT)
        if path.is_file() and not SKIP & set(rel.parts) and path.suffix != ".pyc":
            z.write(path, rel)
    z.write(SITE / "walexport.py", "walexport.py")
    z.write(colorthief.__file__, "colorthief.py")
print(DIST, sum(f.stat().st_size for f in DIST.iterdir()) // 1024, "KiB")
