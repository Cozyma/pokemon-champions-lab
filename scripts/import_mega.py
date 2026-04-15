"""PokeAPIから既存メガシンカデータを取得し、pokemon YAMLのmegaフィールドに追記する。

Usage:
    cd /home/deploy/pokemon-champions-lab
    source .venv/bin/activate
    python scripts/import_mega.py
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx
import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ITEMS_DIR = DATA_DIR / "items"
POKEAPI = "https://pokeapi.co/api/v2/pokemon"

STAT_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}

# 既存メガシンカ (XY/ORAS由来) — PokeAPIのAPIname → (base_species, stone_name_en, stone_name_ja)
# リザードンのみ2形態
EXISTING_MEGAS: list[tuple[str, str, str, str]] = [
    # (api_name, base_species, stone_en, stone_ja)
    ("venusaur-mega", "venusaur", "venusaur-mega-stone", "フシギバナイト"),
    ("charizard-mega-x", "charizard", "charizard-mega-stone-x", "リザードナイトX"),
    ("charizard-mega-y", "charizard", "charizard-mega-stone-y", "リザードナイトY"),
    ("blastoise-mega", "blastoise", "blastoise-mega-stone", "カメックスナイト"),
    ("beedrill-mega", "beedrill", "beedrill-mega-stone", "スピアナイト"),
    ("pidgeot-mega", "pidgeot", "pidgeot-mega-stone", "ピジョットナイト"),
    ("alakazam-mega", "alakazam", "alakazam-mega-stone", "フーディナイト"),
    ("slowbro-mega", "slowbro", "slowbro-mega-stone", "ヤドランナイト"),
    ("gengar-mega", "gengar", "gengar-mega-stone", "ゲンガナイト"),
    ("kangaskhan-mega", "kangaskhan", "kangaskhan-mega-stone", "ガルーラナイト"),
    ("pinsir-mega", "pinsir", "pinsir-mega-stone", "カイロスナイト"),
    ("gyarados-mega", "gyarados", "gyarados-mega-stone", "ギャラドスナイト"),
    ("aerodactyl-mega", "aerodactyl", "aerodactyl-mega-stone", "プテラナイト"),
    ("ampharos-mega", "ampharos", "ampharos-mega-stone", "デンリュウナイト"),
    ("steelix-mega", "steelix", "steelix-mega-stone", "ハガネールナイト"),
    ("scizor-mega", "scizor", "scizor-mega-stone", "ハッサムナイト"),
    ("heracross-mega", "heracross", "heracross-mega-stone", "ヘラクロスナイト"),
    ("houndoom-mega", "houndoom", "houndoom-mega-stone", "ヘルガナイト"),
    ("tyranitar-mega", "tyranitar", "tyranitar-mega-stone", "バンギラスナイト"),
    ("gardevoir-mega", "gardevoir", "gardevoir-mega-stone", "サーナイトナイト"),
    ("sableye-mega", "sableye", "sableye-mega-stone", "ヤミラミナイト"),
    ("aggron-mega", "aggron", "aggron-mega-stone", "ボスゴドラナイト"),
    ("medicham-mega", "medicham", "medicham-mega-stone", "チャーレムナイト"),
    ("manectric-mega", "manectric", "manectric-mega-stone", "ライボルトナイト"),
    ("sharpedo-mega", "sharpedo", "sharpedo-mega-stone", "サメハダナイト"),
    ("camerupt-mega", "camerupt", "camerupt-mega-stone", "バクーダナイト"),
    ("altaria-mega", "altaria", "altaria-mega-stone", "チルタリスナイト"),
    ("banette-mega", "banette", "banette-mega-stone", "ジュペッタナイト"),
    ("absol-mega", "absol", "absol-mega-stone", "アブソルナイト"),
    ("glalie-mega", "glalie", "glalie-mega-stone", "オニゴーリナイト"),
    ("lopunny-mega", "lopunny", "lopunny-mega-stone", "ミミロップナイト"),
    ("garchomp-mega", "garchomp", "garchomp-mega-stone", "ガブリアスナイト"),
    ("lucario-mega", "lucario", "lucario-mega-stone", "ルカリオナイト"),
    ("abomasnow-mega", "abomasnow", "abomasnow-mega-stone", "ユキノオナイト"),
    ("gallade-mega", "gallade", "gallade-mega-stone", "エルレイドナイト"),
    ("audino-mega", "audino", "audino-mega-stone", "タブンネナイト"),
]


def fetch_mega_data(api_name: str) -> dict | None:
    """PokeAPIからメガシンカのデータを取得。"""
    try:
        r = httpx.get(f"{POKEAPI}/{api_name}", timeout=30)
        if r.status_code != 200:
            print(f"  SKIP {api_name}: HTTP {r.status_code}")
            return None
        d = r.json()
        stats = {}
        for s in d["stats"]:
            stats[STAT_MAP[s["stat"]["name"]]] = s["base_stat"]
        types = [t["type"]["name"] for t in d["types"]]
        abilities = [a["ability"]["name"] for a in d["abilities"]]
        return {
            "types": types,
            "ability": abilities[0] if abilities else "",
            "base_stats": stats,
        }
    except Exception as e:
        print(f"  ERROR {api_name}: {e}")
        return None


def update_pokemon_yaml(species: str, mega_data: dict, stone_en: str) -> bool:
    """ポケモンYAMLにmegaフィールドを追記。"""
    yaml_path = DATA_DIR / "pokemon" / f"{species}.yaml"
    if not yaml_path.exists():
        print(f"  SKIP {species}: YAML not found")
        return False

    with open(yaml_path) as f:
        pokemon = yaml.safe_load(f)

    # 既にmegaがある場合はスキップ（garchomp等）
    if "mega" in pokemon and pokemon["mega"]:
        # リザードンの2形態対応: mega_xとmega_yを別々に扱う
        if species == "charizard" and stone_en.endswith("-x"):
            pokemon["mega_x"] = {
                "stone": stone_en,
                "types": mega_data["types"],
                "ability": mega_data["ability"],
                "base_stats": mega_data["base_stats"],
            }
        elif species == "charizard" and stone_en.endswith("-y"):
            pokemon["mega_y"] = {
                "stone": stone_en,
                "types": mega_data["types"],
                "ability": mega_data["ability"],
                "base_stats": mega_data["base_stats"],
            }
        else:
            print(f"  SKIP {species}: mega already exists")
            return False
    else:
        pokemon["mega"] = {
            "stone": stone_en,
            "types": mega_data["types"],
            "ability": mega_data["ability"],
            "base_stats": mega_data["base_stats"],
        }

    with open(yaml_path, "w") as f:
        yaml.dump(pokemon, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return True


def create_mega_stone_yaml(stone_en: str, stone_ja: str) -> None:
    """メガストーンのアイテムYAMLを作成。"""
    path = ITEMS_DIR / f"{stone_en}.yaml"
    if path.exists():
        return
    data = {
        "name": stone_ja,
        "name_en": stone_en,
        "effect": "mega_stone",
        "value": 0,
    }
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def main() -> None:
    print("=== PokeAPI Mega Evolution Import ===\n")
    success = 0
    skip = 0
    fail = 0

    for api_name, species, stone_en, stone_ja in EXISTING_MEGAS:
        print(f"[{api_name}]")
        mega_data = fetch_mega_data(api_name)
        if mega_data is None:
            fail += 1
            continue

        if update_pokemon_yaml(species, mega_data, stone_en):
            create_mega_stone_yaml(stone_en, stone_ja)
            print(f"  OK: {species} → mega (ability={mega_data['ability']}, bst={sum(mega_data['base_stats'].values())})")
            success += 1
        else:
            skip += 1

        time.sleep(0.3)  # Rate limit

    print(f"\nDone: {success} updated, {skip} skipped, {fail} failed")


if __name__ == "__main__":
    main()
