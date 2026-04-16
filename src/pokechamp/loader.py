from __future__ import annotations

from pathlib import Path

import yaml

from pokechamp.models import Move, Pokemon, Team


def get_data_dir() -> Path:
    """Return the data/ directory at project root."""
    return Path(__file__).resolve().parent.parent.parent / "data"


def get_teams_dir() -> Path:
    """Return the teams/ directory at project root."""
    return Path(__file__).resolve().parent.parent.parent / "teams"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def _apply_overrides(data: dict, category: str, name: str) -> dict:
    """Apply overrides from data/overrides/ if they exist."""
    overrides_dir = get_data_dir() / "overrides"
    for override_file in overrides_dir.glob("*.yaml"):
        override = _load_yaml(override_file)
        if override.get("target") == f"{category}/{name}":
            changes = override.get("changes", {})
            _deep_merge(data, changes)
    return data


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base dict."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def load_pokemon(name_en: str) -> Pokemon:
    path = get_data_dir() / "pokemon" / f"{name_en}.yaml"
    data = _load_yaml(path)
    data = _apply_overrides(data, "pokemon", name_en)
    return Pokemon(**data)


def load_move(name_en: str) -> Move:
    path = get_data_dir() / "moves" / f"{name_en}.yaml"
    data = _load_yaml(path)
    data = _apply_overrides(data, "moves", name_en)
    return Move(**data)


def load_item(name_en: str) -> dict:
    path = get_data_dir() / "items" / f"{name_en}.yaml"
    return _load_yaml(path)


def load_team(team_name: str) -> Team:
    """Load a team, preferring team.txt (Showdown format) over team.yaml.

    Falls back to team.yaml if team.txt does not exist.
    """
    teams_dir = get_teams_dir()
    txt_path = teams_dir / team_name / "team.txt"
    if txt_path.exists():
        from pokechamp.showdown_loader import load_showdown_team, showdown_to_team_model
        parsed = load_showdown_team(team_name)
        return showdown_to_team_model(parsed, name=team_name)
    # Fallback: legacy YAML format
    path = teams_dir / team_name / "team.yaml"
    data = _load_yaml(path)
    return Team(**data)


def list_pokemon() -> list[str]:
    return sorted(p.stem for p in (get_data_dir() / "pokemon").glob("*.yaml"))


def list_teams() -> list[str]:
    teams_dir = get_teams_dir()
    return sorted(
        d.name
        for d in teams_dir.iterdir()
        if d.is_dir() and ((d / "team.txt").exists() or (d / "team.yaml").exists())
    )
