#!/usr/bin/env python3
"""
Find charms in charms.encoded.txt that are strictly Pareto-dominated by another
line with the same (skill1, skill2) strings:

  Dominator >= victim on every (lvl1, lvl2, slot1, slot2, slot3), strictly > on at least one.

Output is written to find pareto dominated charms results.txt (overwritten each run):
  loser_line < winner_line, pareto dominated

Run from repo root:
  python3 scripts/find_pareto_dominated_charms.py
  python3 scripts/find_pareto_dominated_charms.py -i path/to/charms.encoded.txt
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedCharm:
    skill1: str
    lvl1: int
    skill2: str
    lvl2: int
    slot1: int
    slot2: int
    slot3: int
    line: str
    line_index: int

    @property
    def skill_key(self) -> tuple[str, str]:
        return (self.skill1, self.skill2)

    def numeric_vector(self) -> tuple[int, ...]:
        return (self.lvl1, self.lvl2, self.slot1, self.slot2, self.slot3)


def parse_line(line: str, line_index: int) -> ParsedCharm:
    s = line.strip()
    if not s or s.startswith("#"):
        raise ValueError("empty or comment")
    parts = s.split(",")
    if len(parts) != 7:
        raise ValueError(f"expected 7 comma-separated fields, got {len(parts)}")
    skill1, l1, skill2, l2, sl1, sl2, sl3 = parts
    return ParsedCharm(
        skill1=skill1.strip(),
        lvl1=int(l1),
        skill2=skill2.strip(),
        lvl2=int(l2),
        slot1=int(sl1),
        slot2=int(sl2),
        slot3=int(sl3),
        line=s,
        line_index=line_index,
    )


def strictly_dominates(a: ParsedCharm, b: ParsedCharm) -> bool:
    if a.skill_key != b.skill_key:
        return False
    va = a.numeric_vector()
    vb = b.numeric_vector()
    ge = all(x >= y for x, y in zip(va, vb))
    gt = any(x > y for x, y in zip(va, vb))
    return ge and gt


def find_pareto_dominated(charms: list[ParsedCharm]) -> list[tuple[ParsedCharm, ParsedCharm]]:
    results: list[tuple[ParsedCharm, ParsedCharm]] = []
    for y in charms:
        for cand in charms:
            if cand is y:
                continue
            if strictly_dominates(cand, y):
                results.append((y, cand))
                break
    return results


def load_charms(path: str) -> list[ParsedCharm]:
    out: list[ParsedCharm] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            try:
                out.append(parse_line(line, i))
            except ValueError:
                continue
    return out


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="List Pareto-dominated charm lines.")
    p.add_argument(
        "--input",
        "-i",
        default=str(repo_root / "charms.encoded.txt"),
        help="Path to encoded charms file",
    )
    p.add_argument(
        "--output",
        "-o",
        default=str(repo_root / "find pareto dominated charms results.txt"),
        help="Results file (overwritten each run)",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Less stdout (results file still written)",
    )
    args = p.parse_args()

    charms = load_charms(args.input)
    pareto_pairs = find_pareto_dominated(charms)

    out_path = Path(args.output)
    lines: list[str] = [
        f"Total parsed lines: {len(charms)}",
        f"Pareto-dominated lines: {len(pareto_pairs)}",
        "",
    ]
    for victim, dominator in pareto_pairs:
        lines.append(f"{victim.line} < {dominator.line}, pareto dominated")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"Total parsed lines: {len(charms)}")
        print(f"Pareto-dominated lines: {len(pareto_pairs)}")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
