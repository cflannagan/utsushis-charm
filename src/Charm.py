import json
import re

from .parse_errors import ParseError


def _encoded_frame_suffix(frame_loc):
    """`,fr123` when ``frame_loc`` points at ``frame123.png`` (under ``frames/`` or elsewhere)."""
    if not frame_loc:
        return ""
    path = str(frame_loc).replace("\\", "/")
    m = re.search(r"(?i)frame(\d+)\.png", path)
    return f",fr{m.group(1)}" if m else ""


class Charm:
    def __init__(self, slots, skills=None, frame_loc=None, rarity=None):
        if not skills:
            skills = {}
        self.slots = list(sorted(slots, reverse=True))
        self.skills = skills
        self.frame_loc = frame_loc
        self.rarity = rarity if rarity in range(1, 11) else None

    def __eq__(self, other):
        return self.is_identical(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        hashcumulator = ""
        for i in self.slots:
            hashcumulator += str(hash(i))
        for s in self.skills:
            k = self.skills[s]
            hashcumulator += str(hash(f"{s}_{k}"))
        return hash(hashcumulator)

    def add_skill(self, skill, level):
        self.skills[skill.strip()] = level

    @staticmethod
    def from_dict(json_data):
        r = json_data.get("rarity")
        if r is not None:
            try:
                r = int(r)
                if r not in range(1, 11):
                    r = None
            except (TypeError, ValueError):
                r = None
        elif json_data.get("rarity7") is True:
            r = 7
        else:
            r = None
        return Charm(
            json_data["slots"],
            json_data["skills"],
            frame_loc=json_data.get("frame_loc"),
            rarity=r,
        )

    def to_dict(self):
        d = {"slots": self.slots, "skills": self.skills}
        if self.rarity is not None:
            d["rarity"] = self.rarity
        if self.frame_loc is not None:
            d["frame_loc"] = self.frame_loc
        return d

    def is_identical(self, charm):
        if (
            self.slots[0] != charm.slots[0]
            or self.slots[1] != charm.slots[1]
            or self.slots[2] != charm.slots[2]
        ):
            return False

        if len(self.skills) != len(charm.skills):
            return False

        for skill in self.skills:
            if skill not in charm.skills or self.skills[skill] != charm.skills[skill]:
                return False

        return True

    def to_simple_encode(self):
        acc = ""
        for skill in self.skills:
            acc += f"{skill},{self.skills[skill]},"
        if len(self.skills) == 0:  # should be impossible
            acc += ",0,"
        if len(self.skills) <= 1:
            acc += ",0,"

        for level in self.slots:
            acc += f"{level},"
        acc = acc[:-1]
        if self.rarity is not None:
            acc += f",rar{self.rarity}"
        else:
            acc += ",rar0"
        acc += _encoded_frame_suffix(self.frame_loc)
        return acc

    def has_skills(self):
        return len(self.skills)


class InvalidCharm(Charm):
    def __init__(self, charm: Charm, skill_errors: [(list, str, int, ParseError)]):
        super().__init__(
            charm.slots,
            charm.skills,
            frame_loc=charm.frame_loc,
            rarity=getattr(charm, "rarity", None),
        )
        self.skill_errors = skill_errors

    def get_errors(self):
        yield from self.skill_errors

    def repair(self, fixed_skills):
        return Charm(
            self.slots, fixed_skills, self.frame_loc, rarity=self.rarity
        )

    def to_dict(self):
        base = super().to_dict()
        simpler_errors = list(map(lambda x: list(map(str, x[1:])), self.skill_errors))
        base["errors"] = simpler_errors
        return base

    def has_skills(self):
        return True


class CharmList(set):
    def __init__(self, *args, **kwargs):
        if args and len(args) > 0:
            for item in args[0]:
                self._test_item(item)
        super(CharmList, self).__init__(*args, **kwargs)

    def encode_all(self):
        acc = ""
        for charm in self:
            acc += f"{charm.to_simple_encode()}\n"
        return acc

    def to_json(self):
        return CharmList

    def add(self, item: Charm):
        self._test_item(item)
        super().add(item)

    def to_dict(self):
        return list(map(lambda x: x.to_dict(), self))

    def __add__(self, other):
        ns = CharmList()
        for item in self:
            ns.add(item)
        for item in other:
            ns.add(item)
        return ns

    @staticmethod
    def from_file(file_path):
        with open(file_path, "r", encoding="utf-8") as charm_file:
            data = json.load(charm_file)
        return CharmList.from_dict(data)

    @staticmethod
    def from_dict(charm_dict):
        new_list = CharmList()
        for item in charm_dict:
            new_list.add(Charm.from_dict(item))
        return new_list

    @staticmethod
    def _test_item(obj):
        if not (type(obj) == Charm or type(obj) == InvalidCharm):
            raise TypeError("Items must be charms")

    def has_invalids(self):
        return any(filter(lambda x: type(x) == InvalidCharm, self))
