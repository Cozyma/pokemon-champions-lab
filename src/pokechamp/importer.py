from __future__ import annotations

from pathlib import Path

import httpx
import yaml

from pokechamp.loader import get_data_dir

POKEAPI_BASE = "https://pokeapi.co/api/v2"

_STAT_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}


def parse_pokeapi_pokemon(data: dict) -> dict:
    types = [t["type"]["name"] for t in data["types"]]
    base_stats = {}
    for stat_entry in data["stats"]:
        api_name = stat_entry["stat"]["name"]
        internal_name = _STAT_MAP.get(api_name, api_name)
        base_stats[internal_name] = stat_entry["base_stat"]
    abilities = [a["ability"]["name"] for a in data["abilities"]]
    moves = [m["move"]["name"] for m in data["moves"]]
    return {
        "name": data["name"],
        "name_en": data["name"],
        "types": types,
        "base_stats": base_stats,
        "abilities": abilities,
        "learnable_moves": moves,
    }


def parse_pokeapi_move(data: dict) -> dict:
    stat_changes = []
    for sc in data.get("stat_changes", []):
        stat_name = _STAT_MAP.get(sc.get("stat", {}).get("name", ""), "")
        change = sc.get("change", 0)
        if stat_name and change != 0:
            stat_changes.append({"stat": stat_name, "stages": change})
    return {
        "name": data["name"],
        "name_en": data["name"],
        "type": data["type"]["name"],
        "category": data["damage_class"]["name"],
        "power": data.get("power") or 0,
        "accuracy": data.get("accuracy") or 100,
        "pp": data.get("pp") or 1,
        "priority": data.get("priority", 0),
        "effects": [],
        "stat_changes": stat_changes,
    }


async def fetch_pokemon(name: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{POKEAPI_BASE}/pokemon/{name}")
        resp.raise_for_status()
        return parse_pokeapi_pokemon(resp.json())


async def fetch_move(name: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{POKEAPI_BASE}/move/{name}")
        resp.raise_for_status()
        return parse_pokeapi_move(resp.json())


def save_pokemon_yaml(data: dict) -> Path:
    path = get_data_dir() / "pokemon" / f"{data['name_en']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path


def save_move_yaml(data: dict) -> Path:
    path = get_data_dir() / "moves" / f"{data['name_en']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path
