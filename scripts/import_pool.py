"""M-A-1プール全ポケモン + メガシンカデータをPokeAPIから一括インポート。

Usage:
    cd /home/deploy/pokemon-champions-lab
    source .venv/bin/activate
    python scripts/import_pool.py
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx
import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ITEMS_DIR = DATA_DIR / "items"
POKEAPI = "https://pokeapi.co/api/v2"

STAT_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}

# M-A-1 プール: PokeAPI名のリスト
# リージョンフォルムはPokeAPIで別エントリ名を持つ
BASE_POKEMON: list[str] = [
    # Gen 1
    "venusaur", "charizard", "blastoise", "beedrill", "pidgeot",
    "arbok", "pikachu", "raichu", "raichu-alola",
    "clefable", "ninetales", "ninetales-alola",
    "arcanine", "arcanine-hisui",
    "alakazam", "machamp", "victreebel",
    "slowbro", "slowbro-galar",
    "gengar", "kangaskhan", "starmie", "pinsir",
    "tauros", "tauros-paldea-combat", "tauros-paldea-blaze", "tauros-paldea-aqua",
    "gyarados", "ditto",
    "vaporeon", "jolteon", "flareon",
    "aerodactyl", "snorlax", "dragonite",
    # Gen 2
    "meganium", "typhlosion", "typhlosion-hisui",
    "feraligatr",
    "ariados", "ampharos", "azumarill", "politoed",
    "espeon", "umbreon",
    "slowking", "slowking-galar",
    "forretress", "steelix", "scizor", "heracross",
    "skarmory", "houndoom", "tyranitar",
    # Gen 3
    "pelipper", "gardevoir", "sableye", "aggron", "medicham",
    "manectric", "sharpedo", "camerupt", "torkoal",
    "altaria", "milotic", "castform",
    "banette", "chimecho", "absol", "glalie",
    # Gen 4
    "torterra", "infernape", "empoleon",
    "luxray", "roserade", "rampardos", "bastiodon",
    "lopunny", "spiritomb", "garchomp", "lucario",
    "hippowdon", "toxicroak", "abomasnow",
    "weavile", "rhyperior",
    "leafeon", "glaceon",
    "gliscor", "mamoswine", "gallade", "froslass",
    "rotom", "rotom-heat", "rotom-wash", "rotom-frost", "rotom-fan", "rotom-mow",
    # Gen 5
    "serperior", "emboar", "samurott", "samurott-hisui",
    "watchog", "liepard",
    "simisage", "simisear", "simipour",
    "excadrill", "audino", "conkeldurr",
    "whimsicott", "krookodile",
    "cofagrigus", "garbodor",
    "zoroark", "zoroark-hisui",
    "reuniclus", "vanilluxe", "emolga",
    "chandelure", "beartic",
    "stunfisk", "stunfisk-galar",
    "golurk", "hydreigon", "volcarona",
    # Gen 6
    "chesnaught", "delphox", "greninja",
    "diggersby", "talonflame", "vivillon",
    "florges", "pangoro", "furfrou",
    "meowstic-male", "meowstic-female",
    "aegislash-shield",
    "aromatisse", "slurpuff",
    "clawitzer", "heliolisk",
    "tyrantrum", "aurorus",
    "sylveon", "hawlucha", "dedenne",
    "goodra", "goodra-hisui",
    "klefki", "trevenant",
    "gourgeist-average",
    "avalugg", "avalugg-hisui",
    "noivern",
    # Gen 7
    "decidueye", "decidueye-hisui",
    "incineroar", "primarina",
    "toucannon", "crabominable",
    "lycanroc-midday", "lycanroc-midnight", "lycanroc-dusk",
    "toxapex", "mudsdale", "araquanid",
    "salazzle", "tsareena",
    "oranguru", "passimian",
    "mimikyu-disguised", "drampa", "kommo-o",
    # Gen 8
    "corviknight",
    "appletun", "flapple",
    "sandaconda", "polteageist",
    "hatterene", "mr-rime",
    "runerigus", "alcremie",
    "morpeko", "dragapult",
    "wyrdeer", "kleavor",
    "basculegion-male", "basculegion-female",
    "sneasler",
    # Gen 9
    "meowscarada", "skeledirge", "quaquaval",
    "maushold", "garganacl",
    "armarouge", "ceruledge",
    "bellibolt", "scovillain",
    "espathra", "tinkaton",
    "palafin", "orthworm",
    "glimmora", "farigiraf", "kingambit",
    "sinistcha", "archaludon",
]

# 既存メガシンカ (PokeAPIに存在する36形態)
EXISTING_MEGAS: list[tuple[str, str, str, str]] = [
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

client = httpx.Client(timeout=30)


def fetch_pokemon(api_name: str) -> dict | None:
    try:
        r = client.get(f"{POKEAPI}/pokemon/{api_name}")
        if r.status_code != 200:
            return None
        d = r.json()
        stats = {}
        for s in d["stats"]:
            stats[STAT_MAP[s["stat"]["name"]]] = s["base_stat"]
        types = [t["type"]["name"] for t in d["types"]]
        abilities = [a["ability"]["name"] for a in d["abilities"]]
        # 技は多すぎるので上位20件に絞る（後でフィルタ）
        moves = [m["move"]["name"] for m in d["moves"][:50]]
        return {
            "name": d["name"],
            "types": types,
            "base_stats": stats,
            "abilities": abilities,
            "moves": moves,
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def save_base_pokemon(api_name: str, data: dict) -> Path:
    # name_enはハイフン正規化（alola/galar/hisui等はそのまま）
    name_en = api_name
    yaml_data = {
        "name": name_en,  # 日本語名は後で手動追加
        "name_en": name_en,
        "types": data["types"],
        "base_stats": data["base_stats"],
        "abilities": data["abilities"],
        "learnable_moves": data["moves"],
    }
    path = DATA_DIR / "pokemon" / f"{name_en}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    # 既存ファイルがあればmegaフィールドを保持
    if path.exists():
        with open(path) as f:
            existing = yaml.safe_load(f) or {}
        if "mega" in existing:
            yaml_data["mega"] = existing["mega"]
    with open(path, "w") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return path


def add_mega_to_yaml(species: str, mega_data: dict, stone_en: str) -> bool:
    path = DATA_DIR / "pokemon" / f"{species}.yaml"
    if not path.exists():
        return False
    with open(path) as f:
        pokemon = yaml.safe_load(f)
    if not pokemon:
        return False
    # リザードンX/Y対応
    if species == "charizard":
        if stone_en.endswith("-x"):
            key = "mega_x"
        else:
            key = "mega_y"
    else:
        key = "mega"
        if key in pokemon:
            return False  # already has mega
    pokemon[key] = {
        "stone": stone_en,
        "types": mega_data["types"],
        "ability": mega_data["abilities"][0] if mega_data.get("abilities") else mega_data.get("ability", ""),
        "base_stats": mega_data["base_stats"],
    }
    with open(path, "w") as f:
        yaml.dump(pokemon, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return True


def create_mega_stone_item(stone_en: str, stone_ja: str) -> None:
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
    print("=== Phase 1: Import Base Pokemon ===\n")
    ok, fail = 0, 0
    for name in BASE_POKEMON:
        data = fetch_pokemon(name)
        if data:
            save_base_pokemon(name, data)
            bst = sum(data["base_stats"].values())
            print(f"  OK {name} (BST={bst})")
            ok += 1
        else:
            print(f"  FAIL {name}")
            fail += 1
        time.sleep(0.15)
    print(f"\nBase: {ok} OK, {fail} FAIL\n")

    print("=== Phase 2: Import Mega Data ===\n")
    mega_ok, mega_fail = 0, 0
    for api_name, species, stone_en, stone_ja in EXISTING_MEGAS:
        data = fetch_pokemon(api_name)
        if data:
            mega_info = {
                "types": data["types"],
                "abilities": data["abilities"],
                "base_stats": data["base_stats"],
            }
            if add_mega_to_yaml(species, mega_info, stone_en):
                create_mega_stone_item(stone_en, stone_ja)
                print(f"  OK {species} ← {api_name} (ability={data['abilities'][0]})")
                mega_ok += 1
            else:
                print(f"  SKIP {species} (already has mega or YAML missing)")
        else:
            print(f"  FAIL {api_name}")
            mega_fail += 1
        time.sleep(0.15)
    print(f"\nMega: {mega_ok} OK, {mega_fail} FAIL")

    print("\n=== Summary ===")
    print(f"Pokemon YAML: {len(list((DATA_DIR / 'pokemon').glob('*.yaml')))} files")
    print(f"Item YAML: {len(list(ITEMS_DIR.glob('*.yaml')))} files")


if __name__ == "__main__":
    main()
