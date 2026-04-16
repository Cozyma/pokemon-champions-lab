"""Showdown-based battle evaluation via subprocess runner.

Runs actual battles using the fast subprocess runner (no server required).
"""
from __future__ import annotations

FORMAT = "gen9championsbssregma"


_MOVE_NAMES_CACHE: dict[str, str] = {}


def _get_move_display_name(move_id: str) -> str:
    """Showdownの技IDを表示名に変換 (closecombat → Close Combat)。"""
    if not _MOVE_NAMES_CACHE:
        import re
        from pathlib import Path
        moves_path = Path(__file__).resolve().parent.parent.parent / "engines" / "showdown" / "data" / "moves.ts"
        if moves_path.exists():
            with open(moves_path) as f:
                for match in re.finditer(r'(\w+):\s*\{[^}]*?name:\s*"([^"]+)"', f.read()):
                    _MOVE_NAMES_CACHE[match.group(1)] = match.group(2)
    return _MOVE_NAMES_CACHE.get(move_id, move_id.replace("-", " ").title())


def _get_champions_learnset(species: str) -> list[str]:
    """ShowdownのChampions learnsetから有効な技リストを取得。"""
    import re
    from pathlib import Path

    learnset_path = Path(__file__).resolve().parent.parent.parent / "engines" / "showdown" / "data" / "mods" / "champions" / "learnsets.ts"
    if not learnset_path.exists():
        return []

    with open(learnset_path) as f:
        content = f.read()

    # species名を正規化（ハイフン除去、小文字）
    key = species.replace("-", "").lower()
    pattern = rf'{key}:\s*\{{[^}}]*learnset:\s*\{{([^}}]+)\}}'
    match = re.search(pattern, content)
    if not match:
        return []
    return re.findall(r'(\w+):', match.group(1))


# 汎用性の高い技（攻撃技優先で選ぶ用のフォールバック）
_PREFERRED_MOVES = [
    "earthquake", "closecombat", "flamethrower", "icebeam", "thunderbolt",
    "shadowball", "sludgebomb", "psychic", "darkpulse", "flashcannon",
    "moonblast", "dragonclaw", "airslash", "surf", "bodypress",
    "bravebid", "ironhead", "stoneedge", "xscissor", "poisonjab",
    "dracometeor", "outrage", "hydropump", "fireblast", "leafstorm",
    "swordsdance", "nastyplot", "calmmind", "dragondance", "quiverdance",
]


def _species_to_showdown_paste(species: str, item: str = "", ability: str = "") -> str:
    """Convert a species name to Showdown paste format with sensible defaults."""
    from pokechamp.loader import load_pokemon

    pokemon = load_pokemon(species)

    # Pick first ability if not specified
    ability = ability or (pokemon.abilities[0] if pokemon.abilities else "")

    # Showdownのlearnsetから技を選択（優先技リストでソート）
    learnset = _get_champions_learnset(species)
    if learnset:
        # 優先技から選ぶ
        moves = [m for m in _PREFERRED_MOVES if m in learnset][:4]
        # 足りなければlearnsetから追加
        if len(moves) < 4:
            for m in learnset:
                if m not in moves and m not in ("protect", "rest", "sleeptalk", "substitute", "endure", "facade"):
                    moves.append(m)
                    if len(moves) >= 4:
                        break
    else:
        # フォールバック: pokechampデータから
        moves = list(pokemon.learnable_moves[:4])

    # Build display name: kebab-case → Title Case with hyphens preserved for forms
    def _to_display(slug: str) -> str:
        return " ".join(p.title() for p in slug.split("-"))

    species_display = _to_display(species)
    ability_display = _to_display(ability)

    lines: list[str] = []
    if item:
        item_display = _to_display(item)
        lines.append(f"{species_display} @ {item_display}")
    else:
        lines.append(species_display)

    lines.append(f"Ability: {ability_display}")
    lines.append("EVs: 32 Atk / 32 Spe / 2 HP")
    lines.append("Jolly Nature")

    for m in moves:
        lines.append(f"- {_get_move_display_name(m)}")

    lines.append("")
    return "\n".join(lines)


def _build_showdown_team(species_list: list[str]) -> str:
    """Build a full Showdown team (6 pokemon) from species list."""
    fillers = ["garchomp", "corviknight", "primarina", "volcarona", "gengar", "hydreigon"]
    team: list[str] = list(species_list)
    for filler in fillers:
        if len(team) >= 6:
            break
        if filler not in team:
            team.append(filler)

    return "\n".join(_species_to_showdown_paste(s) for s in team[:6])


async def evaluate_candidate(
    current_team_species: list[str],
    candidate_species: str,
    threat_species: list[str],
    n_battles: int = 5,
) -> dict:
    """Evaluate how well a candidate addition performs against threats.

    1. Build team: current_team + candidate (pad to 6 with strong generalists if needed)
    2. Build threat team: top threats (pad to 6 if needed)
    3. Run n_battles via fast subprocess runner
    4. Return {"candidate": str, "win_rate": float, "battles": int}
    """
    from pokechamp.fast_battle import run_battle

    team_species = current_team_species + [candidate_species]
    team_paste = _build_showdown_team(team_species)
    threat_paste = _build_showdown_team(threat_species[:6])

    wins = 0
    played = 0
    for i in range(n_battles):
        try:
            seed = [i * 4 + 1, i * 4 + 2, i * 4 + 3, i * 4 + 4]
            result = run_battle(team_paste, threat_paste, seed=seed)
            if result["winner"] == "p1":
                wins += 1
            played += 1
        except Exception:
            continue

    win_rate = wins / max(1, played)
    return {
        "candidate": candidate_species,
        "win_rate": win_rate,
        "battles": played,
    }


async def evaluate_candidates(
    current_team: list[str],
    candidates: list[str],
    threats: list[str],
    n_battles: int = 3,
) -> list[dict]:
    """Evaluate multiple candidates against threat teams.

    Uses the fast subprocess battle runner (no Showdown server required).

    For each candidate:
    1. team_with = current_team + [candidate] (padded to 6)
    2. threat_team = threats[:6] (padded to 6)
    3. Run n_battles via fast subprocess runner
    4. Record win rate

    Returns sorted list of {candidate, win_rate, battles}
    """
    from pokechamp.fast_battle import run_battle

    results: list[dict] = []

    for candidate in candidates:
        team_species = current_team + [candidate]
        team_paste = _build_showdown_team(team_species)
        threat_paste = _build_showdown_team(threats[:6])

        wins = 0
        played = 0
        for i in range(n_battles):
            try:
                seed = [i * 4 + 1, i * 4 + 2, i * 4 + 3, i * 4 + 4]
                result = run_battle(team_paste, threat_paste, seed=seed)
                if result["winner"] == "p1":
                    wins += 1
                played += 1
            except Exception:
                continue

        win_rate = wins / max(1, played)
        results.append({
            "candidate": candidate,
            "win_rate": win_rate,
            "battles": played,
        })

    results.sort(key=lambda x: x["win_rate"], reverse=True)
    return results
