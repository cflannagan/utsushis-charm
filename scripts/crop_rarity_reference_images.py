#!/usr/bin/env python3
"""
Crop full-screen rarity reference shots to a fixed pixel rectangle.

Default input:  ``reference images for rarities/`` (repo root)
Default output: ``reference images for rarities/cropped/``

Edit CROP_X, CROP_Y (and W/H if needed) and re-run until crops line up.

Usage (from repo root):
  python3 scripts/crop_rarity_reference_images.py
  python3 scripts/crop_rarity_reference_images.py --input "reference images for rarities"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

# --- tune these (top-left of crop on 1280×720 full screenshots) ---
# Charm panel origin in frame_extraction.crop_frame is (620, 175). Rarity templates are matched on
# the 630×440 panel only; panel-relative top-left for this crop is approximately:
#   (CROP_X - 620, CROP_Y - 175)  →  see src/rarity_ocr.py RARITY_TEMPLATE_SEARCH_* if you tighten ROI.
CROP_X = 1189
CROP_Y = 180
CROP_W = 62
CROP_H = 20

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
OUTPUT_SUBDIR = "cropped"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Folder of reference images (default: <repo>/reference images for rarities)",
    )
    parser.add_argument(
        "--x",
        type=int,
        default=None,
        help=f"override CROP_X (default {CROP_X})",
    )
    parser.add_argument(
        "--y",
        type=int,
        default=None,
        help=f"override CROP_Y (default {CROP_Y})",
    )
    parser.add_argument(
        "--w",
        type=int,
        default=None,
        help=f"override CROP_W (default {CROP_W})",
    )
    parser.add_argument(
        "--h",
        type=int,
        default=None,
        help=f"override CROP_H (default {CROP_H})",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    in_dir = args.input or (repo_root / "reference images for rarities")
    if not in_dir.is_dir():
        print(f"Input folder not found: {in_dir}", file=sys.stderr)
        return 1

    out_dir = in_dir / OUTPUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    x = args.x if args.x is not None else CROP_X
    y = args.y if args.y is not None else CROP_Y
    w = args.w if args.w is not None else CROP_W
    h = args.h if args.h is not None else CROP_H

    print(f"Crop rect: x={x}, y={y}, w={w}, h={h}")
    print(f"Input:  {in_dir}")
    print(f"Output: {out_dir}")

    count = 0
    for path in sorted(in_dir.iterdir()):
        if path.is_dir():
            if path.name == OUTPUT_SUBDIR:
                continue
            continue
        if path.suffix.lower() not in EXTENSIONS:
            continue

        img = cv2.imread(str(path))
        if img is None:
            print(f"Skip (unreadable): {path.name}", file=sys.stderr)
            continue

        ih, iw = img.shape[:2]
        if x + w > iw or y + h > ih:
            print(
                f"Skip {path.name}: crop outside image bounds ({iw}×{ih})",
                file=sys.stderr,
            )
            continue

        patch = img[y : y + h, x : x + w]
        out_path = out_dir / path.name
        if not cv2.imwrite(str(out_path), patch):
            print(f"Failed to write: {out_path}", file=sys.stderr)
            return 1
        count += 1
        print(f"  wrote {out_path.name}")

    print(f"Done. {count} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
