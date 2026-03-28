# Rarity label (game UI): top of the charm crop, above jewel slots (slots ~y=26 in utils).
# Template match: images/rarities/rarity1.png … rarity10.png on the unmasked 630×440 charm crop.
# Winner = highest TM_CCOEFF_NORMED among loaded templates (same threshold as before; tune later).
# Fallback: trunc OCR on full panel (invert+trunc like skills, but **no** skill_mask — mask hides rarity),
# then legacy multi-variant ROI OCR.
#
# Coordinate spaces (important):
# - All ROIs below are on the **630×440 charm panel** image saved as frames (see frame_extraction.crop_frame).
# - ``scripts/crop_rarity_reference_images.py`` uses **1280×720 full-frame** pixels (CROP_X, CROP_Y, …).
#   To compare or tighten the template search box, convert:
#     panel_x = CROP_X - 620
#     panel_y = CROP_Y - 175
#   (620, 175) is the charm panel top-left after ``apply_pre_crop_mask`` in crop_frame — keep in sync if that moves.
# - Do **not** paste CROP_X/CROP_Y directly into the constants below; subtract the panel origin first.

import os
import re

import cv2

from .resources import get_resource_path
from .tesseract.tesseract_utils import process_image_with_tesseract
from .utils import apply_trunc_threshold

# Search window on the charm panel only: (y1, y2, x1, x2) in [0..440) × [0..630).
RARITY_TEMPLATE_SEARCH_Y1, RARITY_TEMPLATE_SEARCH_Y2 = 0, 50
RARITY_TEMPLATE_SEARCH_X1, RARITY_TEMPLATE_SEARCH_X2 = 350, 630

# TM_CCOEFF_NORMED peak for the *winning* template must be >= this (unchanged for test runs).
RARITY_TEMPLATE_NCC_MIN = 0.78

_rarity_templates_cache = None

# Space for "Rarity 1" … "Rarity 9"; "Rarity10" has no space before 10 in-game.
RARITY_OCR_WHITELIST = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz 0123456789"
)

# Slightly looser last-resort pass (punctuation from UI separators).
RARITY_OCR_WHITELIST_LOOSE = RARITY_OCR_WHITELIST + ".,;:-–—"


def _rarity_color_roi(frame):
    h, w = frame.shape[:2]
    y1, y2 = 4, min(92, h)
    margin = max(4, w // 32)
    return frame[y1:y2, margin : w - margin]


def _variants_for_rarity_ocr(color_bgr):
    """Several single-channel images for Tesseract; order is most likely first."""
    gray = cv2.cvtColor(color_bgr, cv2.COLOR_BGR2GRAY)
    b, g, r = cv2.split(color_bgr)
    mx = cv2.max(cv2.max(b, g), r)
    mn = cv2.min(cv2.min(b, g), r)
    chroma = cv2.subtract(mx, mn)
    _, chroma_bin = cv2.threshold(chroma, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if chroma_bin.mean() > 127:
        chroma_bin = cv2.bitwise_not(chroma_bin)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_e = clahe.apply(gray)

    variants = [
        ("chroma_otsu", chroma_bin),
        (
            "2x_clahe_trunc",
            apply_trunc_threshold(cv2.bitwise_not(
                cv2.resize(gray_e, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            )),
        ),
        (
            "2x_trunc",
            apply_trunc_threshold(
                cv2.bitwise_not(
                    cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                )
            ),
        ),
        ("clahe_trunc", apply_trunc_threshold(cv2.bitwise_not(gray_e))),
        ("trunc_inv", apply_trunc_threshold(cv2.bitwise_not(gray))),
    ]
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    adapt = cv2.adaptiveThreshold(
        blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        -4,
    )
    if adapt.mean() > 127:
        adapt = cv2.bitwise_not(adapt)
    variants.append(("adaptive", adapt))
    return variants


def _load_rarity_templates_gray():
    """List of (rarity_int 1..10, gray, tw, th) for each existing rarity{n}.png."""
    global _rarity_templates_cache
    if _rarity_templates_cache is not None:
        return _rarity_templates_cache
    out = []
    for n in range(1, 11):
        path = get_resource_path(f"rarity{n}")
        if not os.path.isfile(path):
            continue
        bgr = cv2.imread(path)
        if bgr is None or bgr.size == 0:
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        th, tw = gray.shape[:2]
        out.append((n, gray, tw, th))
    _rarity_templates_cache = out
    return _rarity_templates_cache


def try_match_rarity_templates(frame):
    """
    Match all available ``rarity1``…``rarity10`` templates; return the rarity with the
    highest NCC if it clears ``RARITY_TEMPLATE_NCC_MIN``.
    """
    templates = _load_rarity_templates_gray()
    if not templates:
        return None

    max_th = max(t[3] for t in templates)
    max_tw = max(t[2] for t in templates)

    h, w = frame.shape[:2]
    y2 = min(RARITY_TEMPLATE_SEARCH_Y2, h)
    x2 = min(RARITY_TEMPLATE_SEARCH_X2, w)
    y1 = min(RARITY_TEMPLATE_SEARCH_Y1, y2 - 1)
    x1 = min(RARITY_TEMPLATE_SEARCH_X1, x2 - 1)
    if y2 - y1 < max_th or x2 - x1 < max_tw:
        return None

    roi_gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

    best_n = None
    best_score = -1.0
    for n, gray_full, tw, th in templates:
        if y2 - y1 < th or x2 - x1 < tw:
            continue
        res = cv2.matchTemplate(roi_gray, gray_full, cv2.TM_CCOEFF_NORMED)
        maxv = float(res.max())
        if maxv > best_score:
            best_score = maxv
            best_n = n

    if best_n is None or best_score < RARITY_TEMPLATE_NCC_MIN:
        return None

    detail = f"[template_r{best_n}] ncc={best_score:.3f}"
    return best_n, detail


def _normalize_rarity_ocr_label(s):
    """Fix frequent Tesseract misreads on the in-game rarity line before regex parsing."""
    s = re.sub(r"(?i)\braity\b", "rarity", s)
    s = re.sub(r"(?i)\brariyt\b", "rarity", s)
    s = re.sub(r"(?i)\braritv\b", "rarity", s)
    return s


def parse_rarity_from_ocr_text(ocr_text):
    """
    Match 'Rarity 1' … 'Rarity 9', 'Rarity10', and common OCR drops of the final 'y'
    ('Rarit …'). Reject single-digit matches not immediately after the label.
    """
    if not ocr_text:
        return None
    s = re.sub(r"\s+", " ", ocr_text.strip())
    s = _normalize_rarity_ocr_label(s)

    if re.search(r"(?i)Rarit(?:y)?\s*10", s):
        return 10
    m = re.search(r"(?i)Rarit(?:y)?\s+([1-9])\b", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(?i)Rarit(?:y)?\s*([1-9])(?!\d)", s)
    if m:
        return int(m.group(1))
    return None


def get_skill_aligned_rarity_crop(frame):
    """
    BGR crop for Tess: **full** charm panel → ``bitwise_not`` → ``apply_trunc_threshold`` (same ops as
    skill OCR after masking), then rarity ROI. We intentionally skip ``remove_non_skill_info`` because
    the skill mask clears the top of the panel where “Rarity N” lives.
    """
    if frame is None or frame.size == 0:
        return None

    inverted = cv2.bitwise_not(frame)
    trunc_tr = apply_trunc_threshold(inverted)

    h, w = trunc_tr.shape[:2]
    y2 = min(RARITY_TEMPLATE_SEARCH_Y2, h)
    x2 = min(RARITY_TEMPLATE_SEARCH_X2, w)
    y1 = min(RARITY_TEMPLATE_SEARCH_Y1, y2 - 1)
    x1 = min(RARITY_TEMPLATE_SEARCH_X1, x2 - 1)
    if y2 <= y1 or x2 <= x1:
        return None

    crop = trunc_tr[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    return crop


def _raw_rarity_color_crop(frame):
    """Same pixel window as template / trunc ROI, but **unprocessed** BGR from the charm panel."""
    if frame is None or frame.size == 0:
        return None
    h, w = frame.shape[:2]
    y2 = min(RARITY_TEMPLATE_SEARCH_Y2, h)
    x2 = min(RARITY_TEMPLATE_SEARCH_X2, w)
    y1 = min(RARITY_TEMPLATE_SEARCH_Y1, y2 - 1)
    x1 = min(RARITY_TEMPLATE_SEARCH_X1, x2 - 1)
    if y2 <= y1 or x2 <= x1:
        return None
    crop = frame[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def try_rarity_ocr_skill_aligned(tess, frame):
    """
    1) **Raw color** crop of the rarity band — keeps low-contrast yellow digits that invert+trunc can
    wash out. 2) **Trunc** crop (full panel invert+trunc, same ROI) — matches skill-name preprocessing
    when raw OCR mis-reads (e.g. noisy layout).
    """
    last_detail = ""

    raw_color = _raw_rarity_color_crop(frame)
    if raw_color is not None:
        raw_text = process_image_with_tesseract(tess, raw_color)
        parsed = parse_rarity_from_ocr_text(raw_text)
        detail = f"[skill_aligned/raw_color_roi] {raw_text or ''}".rstrip()
        last_detail = detail
        if parsed is not None:
            return parsed, detail

    trunc_crop = get_skill_aligned_rarity_crop(frame)
    if trunc_crop is not None:
        raw_text = process_image_with_tesseract(tess, trunc_crop)
        parsed = parse_rarity_from_ocr_text(raw_text)
        detail = f"[skill_aligned/trunc_bgr] {raw_text or ''}".rstrip()
        last_detail = detail
        if parsed is not None:
            return parsed, detail

    return None, last_detail


def read_rarity_with_tesseract(tess, frame):
    """
    Template match (if ``images/rarities`` PNGs exist and NCC clears threshold), then
    skill-aligned trunc OCR, then legacy multi-variant Tesseract fallback.
    """
    template_hit = try_match_rarity_templates(frame)
    if template_hit is not None:
        return template_hit

    parsed, detail = try_rarity_ocr_skill_aligned(tess, frame)
    if parsed is not None:
        return parsed, detail

    roi_color = _rarity_color_roi(frame)
    if roi_color.size == 0:
        return None, ""

    variants = _variants_for_rarity_ocr(roi_color)
    best_raw = ""
    for whitelist in (RARITY_OCR_WHITELIST, RARITY_OCR_WHITELIST_LOOSE):
        for name, mono in variants:
            raw = process_image_with_tesseract(
                tess,
                mono,
                whitelist,
                resolution=140,
                pageseg_mode=7,
            )
            parsed = parse_rarity_from_ocr_text(raw)
            if parsed is not None:
                return parsed, f"[{name}] {raw}"
            if len(raw) > len(best_raw):
                best_raw = f"[{name}] {raw}"

    return None, best_raw


def collect_rarity_diagnostics(frame, tess):
    """
    Run the same template + OCR pipeline as production, but record every template NCC
    and every OCR variant for troubleshooting (single-frame scripts, etc.).

    Returns a plain dict (JSON-serializable except numpy values are already floats).
    """
    h, w = frame.shape[:2]
    templates = _load_rarity_templates_gray()

    y2 = min(RARITY_TEMPLATE_SEARCH_Y2, h)
    x2 = min(RARITY_TEMPLATE_SEARCH_X2, w)
    y1 = min(RARITY_TEMPLATE_SEARCH_Y1, y2 - 1)
    x1 = min(RARITY_TEMPLATE_SEARCH_X1, x2 - 1)

    template_scores = []
    winner_n = None
    winner_score = -1.0
    roi_gray = None

    if templates:
        max_th = max(t[3] for t in templates)
        max_tw = max(t[2] for t in templates)
        if y2 - y1 >= max_th and x2 - x1 >= max_tw:
            roi_gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            for n, gray_full, tw, th in templates:
                if y2 - y1 < th or x2 - x1 < tw:
                    continue
                res = cv2.matchTemplate(roi_gray, gray_full, cv2.TM_CCOEFF_NORMED)
                maxv = float(res.max())
                template_scores.append(
                    {"rarity": n, "ncc_max": maxv, "template_w": tw, "template_h": th}
                )
                if maxv > winner_score:
                    winner_score = maxv
                    winner_n = n

    template_scores.sort(key=lambda r: -r["ncc_max"])
    template_ok = (
        winner_n is not None and winner_score >= RARITY_TEMPLATE_NCC_MIN
    )

    skill_aligned_parsed, skill_aligned_detail = try_rarity_ocr_skill_aligned(tess, frame)

    ocr_rows = []
    roi_color = _rarity_color_roi(frame)
    if roi_color.size > 0:
        variants = _variants_for_rarity_ocr(roi_color)
        for wl_label, whitelist in (
            ("strict", RARITY_OCR_WHITELIST),
            ("loose", RARITY_OCR_WHITELIST_LOOSE),
        ):
            for name, mono in variants:
                raw = process_image_with_tesseract(
                    tess,
                    mono,
                    whitelist,
                    resolution=140,
                    pageseg_mode=7,
                )
                parsed = parse_rarity_from_ocr_text(raw)
                ocr_rows.append(
                    {
                        "whitelist": wl_label,
                        "variant": name,
                        "raw": raw or "",
                        "parsed": parsed,
                    }
                )

    final_rarity, final_detail = read_rarity_with_tesseract(tess, frame)

    return {
        "frame_hw": (h, w),
        "template_search_roi": (y1, y2, x1, x2),
        "ncc_threshold": RARITY_TEMPLATE_NCC_MIN,
        "template_scores": template_scores,
        "template_winner_rarity": winner_n,
        "template_winner_ncc": None if winner_n is None else float(winner_score),
        "template_would_accept": template_ok,
        "skill_aligned": {
            "parsed": skill_aligned_parsed,
            "detail": skill_aligned_detail,
        },
        "ocr_rows": ocr_rows,
        "final_rarity": final_rarity,
        "final_detail": final_detail,
        "template_roi_gray_shape": None
        if roi_gray is None
        else tuple(roi_gray.shape),
    }
