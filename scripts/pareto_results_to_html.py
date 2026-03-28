#!/usr/bin/env python3
"""
Build a readable HTML table from ``find pareto dominated charms results.txt``.

Usage (from repo root):
  python3 scripts/pareto_results_to_html.py
  python3 scripts/pareto_results_to_html.py -i path/to/results.txt -o path/to/out.html
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_IN = REPO / "find pareto dominated charms results.txt"
DEFAULT_OUT = REPO / "find pareto dominated charms results.html"


def parse_charm_fields(encoded: str) -> tuple[str, str, str, str, str, str] | None:
    """
    From one encoded charm line (raw ``loser`` or ``winner`` side of a results line), return:
    (skill1_display, skill2_display, skill3_placeholder, slots_dash, rarity_num, frame_num)
    """
    encoded = encoded.strip()
    parts = encoded.split(",")
    if len(parts) < 8:
        return None
    last = parts[-1].strip()
    if not re.match(r"^fr\d+$", last):
        return None
    frame_num = last[2:] if last.startswith("fr") else last

    rar = parts[-2].strip()
    if not rar.startswith("rar"):
        return None
    rarity_num = rar[3:]

    s1, s2, s3 = parts[-5], parts[-4], parts[-3]
    slots_dash = f"{s1}-{s2}-{s3}"

    sk = parts[:-5]
    if len(sk) < 4:
        return None
    n1, l1, n2, l2 = sk[0], sk[1], sk[2], sk[3]
    col1 = f"{n1} {l1}".strip() if n1 else (l1 or "")
    col2 = f"{n2} {l2}".strip() if n2 else ""
    col3 = ""
    return (col1, col2, col3, slots_dash, rarity_num, frame_num)


_LEGACY_WIN_SUFFIXES = (
    ", discard dominated",
    " discard dominated",
    ", pareto dominated",
    " pareto dominated",
)


def _strip_winner_suffix(win: str) -> str:
    w = win.strip()
    for suf in _LEGACY_WIN_SUFFIXES:
        if w.endswith(suf):
            return w[: -len(suf)].strip()
    return w


def split_winner_encoded_and_jewel_annotation(s: str) -> tuple[str, str]:
    """
    After ``loser < ``, the winner may be only the encoded charm or encoded plus
    ``, Name size*count, ...`` (decoration witness from find_pareto_dominated_charms).
    """
    t = s.strip()
    m = re.search(r",rar\d+,fr\d+", t)
    if not m:
        return t, ""
    encoded = t[: m.end()].strip()
    rest = t[m.end() :].strip()
    if rest.startswith(","):
        rest = rest[1:].strip()
    return encoded, rest


def parse_result_line(line: str) -> tuple[str, str, str, str, str, str, str, str] | None:
    """Return loser columns + winner encoded + jewel witness text (may be empty), or None."""
    line = line.strip()
    if (
        not line
        or line.startswith("Total ")
        or line.startswith("Discard-dominated")
        or line.startswith("Pareto-dominated")
    ):
        return None
    if " < " not in line:
        return None
    left, right = line.split(" < ", 1)
    win_full = _strip_winner_suffix(right)
    win, jewel_ann = split_winner_encoded_and_jewel_annotation(win_full)

    loser = parse_charm_fields(left)
    if loser is None:
        return None
    c1, c2, c3, slots, rar, fr = loser
    return (c1, c2, c3, slots, rar, fr, win, jewel_ann)


def format_dominating_charm_display(encoded: str) -> str:
    """
    Human-readable dominating charm for HTML, e.g.
    ``Partbreaker 2, Bubbly Dance 2, 2-1-1 (Rarity 7)``.
    Falls back to the raw string if parsing fails.
    """
    parsed = parse_charm_fields(encoded.strip())
    if not parsed:
        return encoded.strip()
    c1, c2, _c3, slots_dash, rarity_num, _frame_num = parsed
    skills = [s for s in (c1, c2) if s and s.strip()]
    skill_part = ", ".join(skills)
    out = f"{skill_part}, {slots_dash} (Rarity {rarity_num})"
    # Frame omitted from display; uncomment to append for troubleshooting:
    # out = f"{out} (frame {_frame_num})"
    return out


def format_dominating_charm_cell(encoded: str, jewel_ann: str) -> str:
    """Human-readable dominating charm plus optional ``, Jewel size*count, ...`` (txt format)."""
    base = format_dominating_charm_display(encoded)
    j = jewel_ann.strip()
    if not j:
        return base
    return f"{base}, {j}"


def slated_for_from_loser_rarity(rarity_str: str) -> str:
    """
    Recycling meld hint for the dominated (loser) charm: Rarity 1–7 → Rebirth;
    8+ → Reincarnation or Cyclus (indistinguishable from data alone).
    """
    try:
        n = int(rarity_str.strip(), 10)
    except ValueError:
        return "Reincarnation/Cyclus"
    if n <= 7:
        return "Rebirth"
    return "Reincarnation/Cyclus"


def _attr(s: str) -> str:
    """Escape for use inside double-quoted HTML attributes."""
    return html.escape(s, quote=True)


def build_html(rows: list[tuple[str, str, str, str, str, str, str, str]], meta_lines: list[str]) -> str:
    esc = html.escape
    # Optional columns (Skill 3, Frame): hidden for a cleaner table. To restore:
    #   1. Add these two lines back inside <tr> in head_rows (after Skill 2):
    #        <th scope="col">Skill 3</th>
    #        <th scope="col">Frame</th>
    #   2. Add these two lines back in the body.append() (after Skill 2 <td>):
    #        f"<td>{esc(c3)}</td>"
    #        f"<td>{esc(fr)}</td>"
    #   3. Set COL_RARITY in the <script> block to 4 (was 3 with columns hidden).
    head_rows = """
    <tr>
      <th class="sortable" data-sort-type="skill" data-label="Skill 1" scope="col" title="Click to sort">Skill 1</th>
      <th class="sortable" data-sort-type="skill" data-label="Skill 2" scope="col" title="Click to sort">Skill 2</th>
      <th scope="col">Slots</th>
      <th class="sortable" data-sort-type="rarity" data-label="Rarity" scope="col" title="Click to sort">Rarity</th>
      <th scope="col">Slated For</th>
      <th scope="col">Dominating charm</th>
    </tr>
"""
    body = []
    for orig_i, (c1, c2, c3, slots, rar, fr, win, jewel_ann) in enumerate(rows):
        k1 = c1.strip().casefold()
        k2 = c2.strip().casefold()
        try:
            rar_num = int(rar, 10)
        except ValueError:
            rar_num = -1
        body.append(
            f'<tr data-orig="{orig_i}">'
            f'<td data-sort-key="{_attr(k1)}">{esc(c1)}</td>'
            f'<td data-sort-key="{_attr(k2)}">{esc(c2)}</td>'
            # f"<td>{esc(c3)}</td>"  # Skill 3 — uncomment with head_rows + COL_RARITY
            f"<td>{esc(slots)}</td>"
            f'<td data-sort-num="{rar_num}">{esc(rar)}</td>'
            f"<td>{esc(slated_for_from_loser_rarity(rar))}</td>"
            # f"<td>{esc(fr)}</td>"  # Frame — uncomment with head_rows + COL_RARITY
            f"<td>{esc(format_dominating_charm_cell(win, jewel_ann))}</td>"
            "</tr>"
        )

    meta_html = "".join(f"<p class=\"meta\">{esc(m)}</p>\n" for m in meta_lines)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Pareto dominated charms</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      margin: 1.25rem 1.5rem 2rem;
      color: #1a1a1a;
      background: #fff;
      line-height: 1.45;
    }}
    h1 {{
      font-size: 1.25rem;
      font-weight: 600;
      margin: 0 0 0.75rem;
    }}
    .meta {{
      margin: 0.2rem 0;
      font-size: 0.9rem;
      color: #444;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      max-width: 1400px;
      font-size: 0.875rem;
    }}
    /* Slots / Rarity / Slated: stay on one line (hyphens in e.g. 0-0-0 are break points otherwise). */
    th:nth-child(3),
    td:nth-child(3),
    th:nth-child(4),
    td:nth-child(4),
    th:nth-child(5),
    td:nth-child(5) {{
      white-space: nowrap;
      width: 1%;
    }}
    /* Dominating charm: use remaining width; wrap on spaces, not mid-slot-code. */
    th:nth-child(6),
    td:nth-child(6) {{
      word-break: break-word;
      overflow-wrap: break-word;
      min-width: 12rem;
    }}
    th, td {{
      border: 1px solid #ccc;
      padding: 0.45rem 0.55rem;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #e8e8e8;
      font-weight: 600;
    }}
    th.sortable {{
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }}
    th.sortable:hover {{
      background: #d8d8d8;
    }}
    th.sortable.sorted-asc,
    th.sortable.sorted-desc {{
      background: #d0d8e8;
    }}
    tbody tr:nth-child(odd) {{
      background: #fff;
    }}
    tbody tr:nth-child(even) {{
      background: #f2f2f2;
    }}
    tbody tr:hover {{
      background: #e6f0ff;
    }}
    td.mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
      font-size: 0.8rem;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <h1>Pareto dominated charms</h1>
  {meta_html}
  <table>
    <thead>
      {head_rows}
    </thead>
    <tbody>
      {''.join(body)}
    </tbody>
  </table>
  <script>
(function () {{
  const COL_SKILL1 = 0;
  const COL_SKILL2 = 1;
  const COL_RARITY = 3; // was 4 when Skill 3 + Frame columns are shown

  const table = document.querySelector("table");
  if (!table) return;
  const tbody = table.querySelector("tbody");
  const headers = table.querySelectorAll("thead th");

  let sortCol = null;
  let sortDir = 1;

  function skillCompare(aKey, bKey, dir) {{
    const ea = !aKey;
    const eb = !bKey;
    if (ea && eb) return 0;
    if (ea) return dir;
    if (eb) return -dir;
    return dir * aKey.localeCompare(bKey, undefined, {{ sensitivity: "base" }});
  }}

  function rarityCompare(aNum, bNum, dir) {{
    const na = Number.isFinite(aNum) ? aNum : -1;
    const nb = Number.isFinite(bNum) ? bNum : -1;
    if (na !== nb) return dir * (na - nb);
    return 0;
  }}

  function compareRows(trA, trB, col, dir) {{
    if (col === COL_RARITY) {{
      const a = parseInt(trA.cells[col].getAttribute("data-sort-num"), 10);
      const b = parseInt(trB.cells[col].getAttribute("data-sort-num"), 10);
      return rarityCompare(a, b, dir);
    }}
    const a = trA.cells[col].getAttribute("data-sort-key") || "";
    const b = trB.cells[col].getAttribute("data-sort-key") || "";
    return skillCompare(a, b, dir);
  }}

  function updateHeaderIndicators(activeCol) {{
    headers.forEach((th, i) => {{
      if (!th.classList.contains("sortable")) return;
      const label = th.dataset.label || th.textContent.replace(/[\\s▲▼]+$/u, "").trim();
      th.classList.remove("sorted-asc", "sorted-desc");
      if (i === activeCol) {{
        th.classList.add(sortDir > 0 ? "sorted-asc" : "sorted-desc");
        th.textContent = label + (sortDir > 0 ? " \\u25B2" : " \\u25BC");
      }} else {{
        th.textContent = label;
      }}
    }});
  }}

  function sortByCol(col) {{
    if (sortCol === col) sortDir = -sortDir;
    else {{
      sortCol = col;
      sortDir = 1;
    }}
    const rows = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {{
      const c = compareRows(a, b, col, sortDir);
      if (c !== 0) return c;
      return Number(a.dataset.orig) - Number(b.dataset.orig);
    }});
    rows.forEach((r) => tbody.appendChild(r));
    updateHeaderIndicators(col);
  }}

  [COL_SKILL1, COL_SKILL2, COL_RARITY].forEach((colIndex) => {{
    const th = headers[colIndex];
    if (!th || !th.classList.contains("sortable")) return;
    th.addEventListener("click", () => sortByCol(colIndex));
    th.addEventListener("keydown", (e) => {{
      if (e.key === "Enter" || e.key === " ") {{
        e.preventDefault();
        sortByCol(colIndex);
      }}
    }});
    th.setAttribute("tabindex", "0");
    th.setAttribute("role", "button");
  }});
}})();
  </script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--input", type=Path, default=DEFAULT_IN, help="results txt path")
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT, help="output html path")
    args = ap.parse_args()

    text = args.input.read_text(encoding="utf-8")
    meta_lines: list[str] = []
    rows: list[tuple[str, str, str, str, str, str, str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        if (
            s.startswith("Total parsed")
            or s.startswith("Discard-dominated")
            or s.startswith("Pareto-dominated")
        ):
            meta_lines.append(s)
            continue
        parsed = parse_result_line(line)
        if parsed:
            rows.append(parsed)

    out = build_html(rows, meta_lines)
    args.output.write_text(out, encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
