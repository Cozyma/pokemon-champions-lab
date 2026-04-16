"""Load teams from Showdown paste format (.txt files)."""
from __future__ import annotations

import re
from pathlib import Path

from pokechamp.models import EVs, IVs, Nature, Team, TeamMember


def get_teams_dir() -> Path:
    """Return the teams/ directory at project root."""
    return Path(__file__).resolve().parent.parent.parent / "teams"


def parse_showdown_paste(text: str) -> list[dict]:
    """Parse Showdown paste text into structured data.

    Returns list of dicts with:
    {
        "species": str,       # Showdown species name (e.g. "Garchomp", "Aegislash-Shield")
        "item": str,          # Showdown item name (e.g. "Choice Scarf", "Gengarite")
        "ability": str,       # Showdown ability name (e.g. "Rough Skin")
        "nature": str,        # Nature name (e.g. "Jolly")
        "evs": {"hp": int, "atk": int, "def": int, "spa": int, "spd": int, "spe": int},
        "ivs": {"hp": int, "atk": int, "def": int, "spa": int, "spd": int, "spe": int},
        "moves": [str, ...],  # Move names as they appear in the paste
    }
    """
    results: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.strip())

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [line.rstrip() for line in block.splitlines()]
        if not lines:
            continue

        entry: dict = {
            "species": "",
            "item": "",
            "ability": "",
            "nature": "",
            "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "ivs": {"hp": 31, "atk": 31, "def": 31, "spa": 31, "spd": 31, "spe": 31},
            "moves": [],
        }

        # First line: "Species @ Item"  or just "Species"
        first = lines[0]
        if " @ " in first:
            species_part, item_part = first.split(" @ ", 1)
            entry["species"] = species_part.strip()
            entry["item"] = item_part.strip()
        else:
            entry["species"] = first.strip()

        for line in lines[1:]:
            if line.startswith("Ability:"):
                entry["ability"] = line[len("Ability:"):].strip()
            elif line.startswith("EVs:"):
                entry["evs"] = _parse_stats(line[len("EVs:"):].strip())
            elif line.startswith("IVs:"):
                # IVs default to 31; only listed stats are overridden
                iv_overrides = _parse_stats(line[len("IVs:"):].strip())
                for k, v in iv_overrides.items():
                    entry["ivs"][k] = v
            elif line.endswith(" Nature"):
                entry["nature"] = line[: -len(" Nature")].strip()
            elif line.startswith("- "):
                entry["moves"].append(line[2:].strip())

        results.append(entry)

    return results


def _parse_stats(stat_str: str) -> dict[str, int]:
    """Parse EV/IV stat string like '252 Atk / 4 HP / 252 Spe' into a dict.

    Keys use Showdown abbreviations: hp, atk, def, spa, spd, spe.
    """
    _LABEL_MAP = {
        "HP": "hp",
        "Atk": "atk",
        "Def": "def",
        "SpA": "spa",
        "SpD": "spd",
        "Spe": "spe",
    }
    result: dict[str, int] = {}
    for part in stat_str.split("/"):
        part = part.strip()
        m = re.match(r"(\d+)\s+(\w+)", part)
        if m:
            value = int(m.group(1))
            label = m.group(2)
            key = _LABEL_MAP.get(label)
            if key:
                result[key] = value
    return result


def load_showdown_team(team_name: str) -> list[dict]:
    """Load team from teams/{team_name}/team.txt."""
    path = get_teams_dir() / team_name / "team.txt"
    if not path.exists():
        raise FileNotFoundError(f"Showdown team file not found: {path}")
    text = path.read_text(encoding="utf-8")
    return parse_showdown_paste(text)


def list_showdown_teams() -> list[str]:
    """List teams that have team.txt files."""
    teams_dir = get_teams_dir()
    return sorted(
        d.name for d in teams_dir.iterdir()
        if d.is_dir() and (d / "team.txt").exists()
    )


# ---------------------------------------------------------------------------
# Conversion helpers: Showdown parsed data → pokechamp internal models
# ---------------------------------------------------------------------------

# Showdown stat abbreviation → pokechamp EVs/IVs field names
_STAT_KEY_MAP: dict[str, str] = {
    "hp": "hp",
    "atk": "attack",
    "def": "defense",
    "spa": "sp_attack",
    "spd": "sp_defense",
    "spe": "speed",
}

# Showdown species name → pokechamp species slug
# Covers cases where Showdown uses hyphenated forms.
_SPECIES_NAME_MAP: dict[str, str] = {
    "Aegislash-Shield": "aegislash-shield",
    "Floette-Eternal": "floette-eternal",
}


def _showdown_species_to_slug(species: str) -> str:
    """Convert Showdown species name to pokechamp species slug."""
    if species in _SPECIES_NAME_MAP:
        return _SPECIES_NAME_MAP[species]
    return species.lower()


def _showdown_item_to_slug(item: str) -> str:
    """Convert Showdown item display name to pokechamp item slug (kebab-case)."""
    return item.lower().replace(" ", "-").replace("'", "")


def _showdown_ability_to_slug(ability: str) -> str:
    """Convert Showdown ability display name to pokechamp ability slug."""
    return ability.lower().replace(" ", "-")


def _showdown_move_to_slug(move: str) -> str:
    """Convert Showdown move display name to pokechamp move slug."""
    return move.lower().replace(" ", "-").replace("'", "")


def _showdown_nature_to_enum(nature_str: str) -> Nature:
    """Convert nature string like 'Jolly' to Nature enum."""
    return Nature(nature_str.lower())


def showdown_to_team_model(parsed: list[dict], name: str) -> Team:
    """Convert parsed Showdown paste data to pokechamp Team model.

    Parameters
    ----------
    parsed:
        Output of parse_showdown_paste().
    name:
        Team name to assign to the Team model.

    Returns
    -------
    Team
        pokechamp Team model usable by the internal battle engine.
    """
    members: list[TeamMember] = []
    for entry in parsed:
        ev_data = entry["evs"]
        iv_data = entry["ivs"]

        evs = EVs(
            hp=ev_data.get("hp", 0),
            attack=ev_data.get("atk", 0),
            defense=ev_data.get("def", 0),
            sp_attack=ev_data.get("spa", 0),
            sp_defense=ev_data.get("spd", 0),
            speed=ev_data.get("spe", 0),
        )
        ivs = IVs(
            hp=iv_data.get("hp", 31),
            attack=iv_data.get("atk", 31),
            defense=iv_data.get("def", 31),
            sp_attack=iv_data.get("spa", 31),
            sp_defense=iv_data.get("spd", 31),
            speed=iv_data.get("spe", 31),
        )

        member = TeamMember(
            species=_showdown_species_to_slug(entry["species"]),
            ability=_showdown_ability_to_slug(entry["ability"]),
            item=_showdown_item_to_slug(entry["item"]),
            nature=_showdown_nature_to_enum(entry["nature"]),
            evs=evs,
            ivs=ivs,
            moves=[_showdown_move_to_slug(m) for m in entry["moves"]],
        )
        members.append(member)

    return Team(name=name, pokemon=members)
