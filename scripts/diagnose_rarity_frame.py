#!/usr/bin/env python3
"""
Troubleshoot rarity detection for one saved charm frame (e.g. frames/frame73.png).

From repo root:
  python3 scripts/diagnose_rarity_frame.py 73
  python3 scripts/diagnose_rarity_frame.py --frame 1641 --frames-dir frames

Prints template NCC scores (vs images/rarities/rarity1.png … rarity10.png), whether the
winner clears RARITY_TEMPLATE_NCC_MIN, every Tesseract variant raw string, and the final
result from the same logic as charm extraction.

Uses game language from app config when available; override with --language eng.

Optional debug PNGs: --save-template-roi, --save-skill-aligned-crop PATH
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "frame_num",
        nargs="?",
        type=int,
        help="Frame index as in frame<N>.png (e.g. 73)",
    )
    parser.add_argument(
        "--frame",
        "-f",
        type=int,
        dest="frame_opt",
        help="Same as positional frame number",
    )
    parser.add_argument(
        "--frames-dir",
        type=Path,
        default=REPO_ROOT / "frames",
        help="Directory containing frame<N>.png (default: <repo>/frames)",
    )
    parser.add_argument(
        "--language",
        "-l",
        default=None,
        help="Tesseract language code (default: from app config, else eng)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print diagnostics as JSON (for piping)",
    )
    parser.add_argument(
        "--save-template-roi",
        type=Path,
        default=None,
        help="Write template search ROI as grayscale PNG for visual check",
    )
    parser.add_argument(
        "--save-skill-aligned-crop",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write skill-aligned trunc crop (exact image sent to default Tess) as PNG",
    )
    args = parser.parse_args()

    n = args.frame_num if args.frame_num is not None else args.frame_opt
    if n is None:
        parser.error("pass frame number, e.g. 73 or --frame 73")

    sys.path.insert(0, str(REPO_ROOT))

    from src.rarity_ocr import (
        RARITY_TEMPLATE_SEARCH_X1,
        RARITY_TEMPLATE_SEARCH_X2,
        RARITY_TEMPLATE_SEARCH_Y1,
        RARITY_TEMPLATE_SEARCH_Y2,
        collect_rarity_diagnostics,
        get_skill_aligned_rarity_crop,
    )
    from src.resources import get_game_language
    from src.tesseract.Tesseract import Tesseract

    lang = args.language or get_game_language()
    path = args.frames_dir / f"frame{n}.png"
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1

    img = cv2.imread(str(path))
    if img is None or img.size == 0:
        print(f"Could not read image: {path}", file=sys.stderr)
        return 1

    tess = Tesseract(language=lang)
    diag = collect_rarity_diagnostics(img, tess)

    if args.save_template_roi:
        y1, y2, x1, x2 = diag["template_search_roi"]
        roi = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        out = args.save_template_roi
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), roi)
        print(f"Wrote template ROI ({roi.shape[1]}×{roi.shape[0]}) to {out}", file=sys.stderr)

    if args.save_skill_aligned_crop:
        out = args.save_skill_aligned_crop.resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        sac = get_skill_aligned_rarity_crop(img)
        if sac is None:
            print("Skill-aligned crop unavailable (empty ROI).", file=sys.stderr)
        else:
            ok = cv2.imwrite(str(out), sac)
            c = sac.shape[2] if sac.ndim == 3 else 1
            if not ok:
                print(f"ERROR: cv2.imwrite failed for {out}", file=sys.stderr)
                return 1
            print(
                f"Wrote skill-aligned crop ({sac.shape[1]}×{sac.shape[0]}, {c} ch) to:\n  {out}",
                file=sys.stderr,
            )

    if args.json:
        print(json.dumps(diag, indent=2))
        return 0

    print(f"File: {path.resolve()}")
    print(f"Image size (H×W): {diag['frame_hw'][0]} × {diag['frame_hw'][1]}")
    y1, y2, x1, x2 = diag["template_search_roi"]
    print(
        "Template search ROI (y1,y2,x1,x2) on charm panel: "
        f"{y1},{y2},{x1},{x2}  [constants: y {RARITY_TEMPLATE_SEARCH_Y1}-{RARITY_TEMPLATE_SEARCH_Y2}, "
        f"x {RARITY_TEMPLATE_SEARCH_X1}-{RARITY_TEMPLATE_SEARCH_X2}]"
    )
    if diag.get("template_roi_gray_shape"):
        print(f"ROI gray shape: {diag['template_roi_gray_shape']}")
    print(f"NCC accept threshold: {diag['ncc_threshold']}")
    print()
    print("Template match (sorted by NCC, highest first):")
    for row in diag["template_scores"]:
        mark = " <-- winner" if row["rarity"] == diag["template_winner_rarity"] else ""
        print(
            f"  rarity{row['rarity']}: ncc_max={row['ncc_max']:.4f}  "
            f"template {row['template_w']}×{row['template_h']}{mark}"
        )
    if not diag["template_scores"]:
        print("  (no template scores — missing templates or ROI too small)")
    print()
    wn, wv = diag["template_winner_rarity"], diag["template_winner_ncc"]
    print(
        f"Template stage: winner=rarity{wn}, ncc={wv}, "
        f"would_accept={diag['template_would_accept']}"
    )
    print()
    sa = diag.get("skill_aligned") or {}
    sap, sad = sa.get("parsed"), sa.get("detail", "")
    sap_s = "—" if sap is None else str(sap)
    sad_disp = (sad or "").replace("\n", "\\n")
    if len(sad_disp) > 140:
        sad_disp = sad_disp[:137] + "..."
    print(
        "Skill-aligned OCR (raw color rarity ROI, then trunc crop if needed; default Tess each pass):"
    )
    print(f"  parsed={sap_s!r}  detail={sad_disp!r}")
    print()
    print("Legacy OCR fallback (multi-variant; runs only if skill-aligned did not parse):")
    for row in diag["ocr_rows"]:
        raw_disp = (row["raw"] or "").replace("\n", "\\n")
        if len(raw_disp) > 120:
            raw_disp = raw_disp[:117] + "..."
        p = row["parsed"]
        p_s = "—" if p is None else str(p)
        print(f"  [{row['whitelist']}/{row['variant']}] parsed={p_s!r}  raw={raw_disp!r}")
    print()
    fr, fd = diag["final_rarity"], diag["final_detail"]
    print("=== Final (read_rarity_with_tesseract) ===")
    print(f"  rarity: {fr if fr is not None else 'None → encoded as rar0'}")
    print(f"  detail: {fd!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
