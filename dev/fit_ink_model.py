"""Fit the per-ink constants in backend/printmich/ink.py to Canon's published PRO-310 yields.

    python dev/fit_ink_model.py /path/to/photos

Canon rates each PFI-5100 tank (14.4 ml) in 4×6 prints on Photo Paper Pro Platinum (ISO/IEC 29102,
continuous printing). Matte black is never printed on glossy paper, so its yield is pure head-cleaning
use, which every tank shares. For the other inks, the constant is chosen so that a folder of typical
photos, printed borderless at 4×6, averages Canon's per-print use.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from printmich.ink import INK_KEYS, coverage, image_array

TANK_ML = 14.4
AREA = 4 * 6
YIELD_4X6 = {"MBK": 1679, "PBK": 450, "GY": 233, "C": 842, "PC": 704, "M": 610, "PM": 430, "Y": 551, "R": 969,
             "CO": 256}


def main(folder: str) -> None:
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".heic"))
    if not files:
        raise SystemExit("no photos found")
    covs = [coverage(image_array(f), matte=False) for f in files]
    clean = TANK_ML / YIELD_4X6["MBK"] / AREA
    print(f"{len(files)} photos; cleaning {clean:.6f} ml per sq in per ink")
    out = {}
    for ink in INK_KEYS:
        if ink == "MBK":
            continue
        mean = float(np.mean([c[ink] for c in covs]))
        printed = TANK_ML / YIELD_4X6[ink] / AREA - clean
        out[ink] = printed / mean if mean > 0 else float("nan")
        print(f"{ink:4s} mean coverage {mean:.3f}  ml per sq in at full coverage {out[ink]:.4f}")
    print("ML_PER_SQ_IN =", {k: round(v, 4) for k, v in out.items()})


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo/lib")
