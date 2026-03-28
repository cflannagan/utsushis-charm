#!/usr/bin/env python3
"""
Charm discard test per `charm-discard-criteria.txt` (rules A–C, D, E, F).

For each charm (subject), finds whether any other charm in the pool can beat it using native
skills plus decorations from `decorations.txt` (disjoint slots, greedy smallest fitting hole per
jewel in the enumerator).

Default output: `find pareto dominated charms results.txt` (overwritten each run):
  loser_line < winner_line, discard dominated

Legacy same-(skill1, skill2) numeric Pareto check: pass --pareto-only.

Run from repo root:
  python3 scripts/find_pareto_dominated_charms.py
  python3 scripts/find_pareto_dominated_charms.py -i path/to/charms.encoded.txt
  python3 scripts/find_pareto_dominated_charms.py --pareto-only
"""

from __future__ import annotations

import argparse
from collections import defaultdict
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

    def slot_sizes(self) -> list[int]:
        return [self.slot1, self.slot2, self.slot3]


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


def load_charms(path: str) -> list[ParsedCharm]:
    out: list[ParsedCharm] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            try:
                out.append(parse_line(line, i))
            except ValueError:
                continue
    return out


@dataclass(frozen=True)
class Decoration:
    name: str
    size: int
    skill: str
    points: int


def load_decorations(path: str) -> list[Decoration]:
    out: list[Decoration] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split(",")
            if len(parts) != 4:
                continue
            name, sz, skill, pts = parts[0].strip(), int(parts[1]), parts[2].strip(), int(parts[3])
            out.append(Decoration(name=name, size=sz, skill=skill, points=pts))
    return out


def native_skill_entries(ch: ParsedCharm) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    if ch.skill1:
        out.append((ch.skill1, ch.lvl1))
    if ch.skill2:
        out.append((ch.skill2, ch.lvl2))
    return out


def subject_skill_levels(ch: ParsedCharm) -> dict[str, int]:
    """Merge native subject skills by name (max level if duplicated)."""
    d: dict[str, int] = {}
    for name, lv in native_skill_entries(ch):
        d[name] = max(d.get(name, 0), lv)
    return d


def native_level_for_skill(ch: ParsedCharm, skill: str) -> int:
    m = 0
    if ch.skill1 == skill:
        m = max(m, ch.lvl1)
    if ch.skill2 == skill:
        m = max(m, ch.lvl2)
    return m


def sorted_slot_tuple(slot1: int, slot2: int, slot3: int) -> tuple[int, int, int]:
    return tuple(sorted((slot1, slot2, slot3), reverse=True))


def cmp_slot_multiset(
    cand_residual: tuple[int, int, int], subj_slots: tuple[int, int, int]
) -> int:
    """
    Rule D: both triples sorted descending (same length). Cand **wins** only if component-wise
    cand >= subject at every index and cand > subject at at least one (strict dominance on the
    triple). **Tie** only if the two triples are equal. Anything else (e.g. (2,0,0) vs (1,1,1)) is
    a **loss** for the challenger on D—no E/F.
    """
    if cand_residual == subj_slots:
        return 0
    ge = all(c >= s for c, s in zip(cand_residual, subj_slots))
    gt = any(c > s for c, s in zip(cand_residual, subj_slots))
    if ge and gt:
        return 1
    return -1


def strictly_dominates_pareto(a: ParsedCharm, b: ParsedCharm) -> bool:
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
            if strictly_dominates_pareto(cand, y):
                results.append((y, cand))
                break
    return results


def jewel_points_by_skill(plan: list[tuple[int, Decoration]]) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for _si, j in plan:
        d[j.skill] += j.points
    return dict(d)


def residual_slots_after_plan(cand: ParsedCharm, plan: list[tuple[int, Decoration]]) -> tuple[int, int, int]:
    used = {si for si, _ in plan}
    free = [cand.slot1, cand.slot2, cand.slot3]
    resid = [free[i] for i in range(3) if i not in used]
    while len(resid) < 3:
        resid.append(0)
    return sorted_slot_tuple(resid[0], resid[1], resid[2])


def decorations_for_skill(decs: list[Decoration], skill: str) -> list[Decoration]:
    return [d for d in decs if d.skill == skill]


def smallest_fitting_slot(used: set[int], slot_sizes: list[int], j: Decoration) -> int | None:
    """Smallest unused hole that fits jewel j (rule C); tie-break lower slot index."""
    best_i: int | None = None
    best_sz = 0
    for i in range(3):
        if i in used:
            continue
        sz = slot_sizes[i]
        if sz < j.size:
            continue
        if best_i is None or sz < best_sz or (sz == best_sz and i < best_i):
            best_i = i
            best_sz = sz
    return best_i


def iter_jewel_plans(
    cand: ParsedCharm,
    remaining: dict[str, int],
    decs: list[Decoration],
) -> list[list[tuple[int, Decoration]]]:
    """
    Assign jewels to distinct slots until every remaining[skill] <= 0.
    Each step picks a decoration, then places it in the smallest unused slot that fits (rule C).
    """
    slot_sizes = cand.slot_sizes()
    if all(v <= 0 for v in remaining.values()):
        return [[]]

    out: list[list[tuple[int, Decoration]]] = []
    seen: set[tuple[tuple[int, str, int, int], ...]] = set()

    def rec(used_slots: set[int], rem: dict[str, int], acc: list[tuple[int, Decoration]]) -> None:
        if all(v <= 0 for v in rem.values()):
            key = tuple(sorted((si, j.skill, j.size, j.points) for si, j in acc))
            if key not in seen:
                seen.add(key)
                out.append(list(acc))
            return
        if len(used_slots) >= 3:
            return

        need_skills = [s for s, v in rem.items() if v > 0]
        candidates: list[Decoration] = []
        for sk in need_skills:
            candidates.extend(decorations_for_skill(decs, sk))
        # Prefer larger point jewels first (fewer decorations), then smaller physical size.
        candidates.sort(key=lambda j: (-j.points, j.size, j.name))

        for j in candidates:
            if j.skill not in rem or rem[j.skill] <= 0:
                continue
            si = smallest_fitting_slot(used_slots, slot_sizes, j)
            if si is None:
                continue
            r2 = dict(rem)
            r2[j.skill] = r2[j.skill] - j.points
            rec(used_slots | {si}, r2, acc + [(si, j)])

    rec(set(), dict(remaining), [])
    return out


def plan_satisfies_A(
    subj_levels: dict[str, int], cand: ParsedCharm, plan: list[tuple[int, Decoration]]
) -> bool:
    jp = jewel_points_by_skill(plan)
    for name, L in subj_levels.items():
        total = native_level_for_skill(cand, name) + jp.get(name, 0)
        if total < L:
            return False
    return True


def strict_native_beat(subj_levels: dict[str, int], cand: ParsedCharm) -> bool:
    for name, L in subj_levels.items():
        if native_level_for_skill(cand, name) > L:
            return True
    return False


def exact_skill_tie(
    subj_levels: dict[str, int], cand: ParsedCharm, plan: list[tuple[int, Decoration]]
) -> bool:
    jp = jewel_points_by_skill(plan)
    if strict_native_beat(subj_levels, cand):
        return False
    for name, L in subj_levels.items():
        nat = native_level_for_skill(cand, name)
        total = nat + jp.get(name, 0)
        if total != L:
            return False
        if nat > L:
            return False
    return True


def flexibility_F(
    subj_levels: dict[str, int], cand: ParsedCharm, plan: list[tuple[int, Decoration]]
) -> bool:
    jp = jewel_points_by_skill(plan)
    for name, L in subj_levels.items():
        if native_level_for_skill(cand, name) == 0 and jp.get(name, 0) == L:
            return True
    return False


def challenger_discards_subject(
    subj: ParsedCharm, cand: ParsedCharm, decs: list[Decoration]
) -> bool:
    subj_levels = subject_skill_levels(subj)
    if not subj_levels:
        return False

    # Every subject skill name has an entry so empty rem does not vacuously succeed.
    remaining: dict[str, int] = {}
    for name, L in subj_levels.items():
        remaining[name] = max(0, L - native_level_for_skill(cand, name))

    plans = iter_jewel_plans(cand, remaining, decs)
    subj_slot_t = sorted_slot_tuple(subj.slot1, subj.slot2, subj.slot3)

    for plan in plans:
        if not plan_satisfies_A(subj_levels, cand, plan):
            continue
        resid = residual_slots_after_plan(cand, plan)
        dcmp = cmp_slot_multiset(resid, subj_slot_t)
        if dcmp > 0:
            return True
        if dcmp < 0:
            continue
        # D tie → E / F
        if strict_native_beat(subj_levels, cand):
            return True
        if exact_skill_tie(subj_levels, cand, plan):
            if flexibility_F(subj_levels, cand, plan):
                return True
        # overcoverage on tie: fail E
    return False


def find_discard_dominated(
    charms: list[ParsedCharm], decs: list[Decoration]
) -> list[tuple[ParsedCharm, ParsedCharm]]:
    results: list[tuple[ParsedCharm, ParsedCharm]] = []
    for y in charms:
        for cand in charms:
            if cand is y:
                continue
            if challenger_discards_subject(y, cand, decs):
                results.append((y, cand))
                break
    return results


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(
        description="Charm discard test (charm-discard-criteria.txt) or --pareto-only."
    )
    p.add_argument(
        "--input",
        "-i",
        default=str(repo_root / "charms.encoded.txt"),
        help="Path to encoded charms file",
    )
    p.add_argument(
        "--decorations",
        "-d",
        default=str(repo_root / "decorations.txt"),
        help="Path to decorations.txt (ignored for --pareto-only)",
    )
    p.add_argument(
        "--output",
        "-o",
        default=str(repo_root / "find pareto dominated charms results.txt"),
        help="Results file (overwritten each run)",
    )
    p.add_argument(
        "--pareto-only",
        action="store_true",
        help="Same (skill1, skill2) strict Pareto only; no decorations.",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Less stdout (results file still written)",
    )
    args = p.parse_args()

    charms = load_charms(args.input)
    out_path = Path(args.output)

    if args.pareto_only:
        pairs = find_pareto_dominated(charms)
        label = "Pareto-dominated"
        line_suffix = "pareto dominated"
    else:
        decs = load_decorations(args.decorations)
        pairs = find_discard_dominated(charms, decs)
        label = "Discard-dominated (charm-discard-criteria)"
        line_suffix = "discard dominated"

    lines: list[str] = [
        f"Total parsed lines: {len(charms)}",
        f"{label} lines: {len(pairs)}",
        "",
    ]
    for victim, dominator in pairs:
        lines.append(f"{victim.line} < {dominator.line}, {line_suffix}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"Total parsed lines: {len(charms)}")
        print(f"{label} lines: {len(pairs)}")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
