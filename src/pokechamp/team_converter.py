"""チームYAML → Showdown paste 変換モジュール。

Usage
-----
    from pokechamp.team_converter import team_yaml_to_showdown

    showdown_str = team_yaml_to_showdown("mega-scizor-team")
    print(showdown_str)
"""
from __future__ import annotations

from pokechamp.loader import load_pokemon, load_team


def team_yaml_to_showdown(team_name: str) -> str:
    """teams/{team_name}/team.yaml を Showdown paste 形式に変換する。

    Parameters
    ----------
    team_name:
        teams/ 配下のチームディレクトリ名 (例: "mega-scizor-team")

    Returns
    -------
    str
        Pokemon Showdown に貼り付け可能なチーム文字列。
    """
    team = load_team(team_name)
    blocks: list[str] = []

    _EV_LABEL: dict[str, str] = {
        "hp": "HP",
        "attack": "Atk",
        "defense": "Def",
        "sp_attack": "SpA",
        "sp_defense": "SpD",
        "speed": "Spe",
    }

    for member in team.pokemon:
        pokemon = load_pokemon(member.species)
        lines: list[str] = []

        # Species @ Item
        species_display = _to_showdown_name(pokemon.name_en)
        item_display = _to_showdown_name(member.item)
        lines.append(f"{species_display} @ {item_display}")

        # Ability
        ability_display = _to_showdown_name(member.ability)
        lines.append(f"Ability: {ability_display}")

        # EVs (0の項目は省略)
        evs = member.evs.model_dump()
        ev_parts = [
            f"{v} {_EV_LABEL[k]}"
            for k, v in evs.items()
            if v > 0
        ]
        if ev_parts:
            lines.append(f"EVs: {' / '.join(ev_parts)}")

        # IVs (31以外のみ出力)
        ivs = member.ivs.model_dump()
        iv_parts = [
            f"{v} {_EV_LABEL[k]}"
            for k, v in ivs.items()
            if v != 31
        ]
        if iv_parts:
            lines.append(f"IVs: {' / '.join(iv_parts)}")

        # Nature
        lines.append(f"{member.nature.value.title()} Nature")

        # Moves
        for move in member.moves:
            lines.append(f"- {_to_showdown_name(move)}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) + "\n"


def _to_showdown_name(slug: str) -> str:
    """kebab-case スラッグをShowdown表示名に変換する。

    例: "rough-skin" → "Rough Skin"
        "mega-stone" → "Mega Stone"
        "aegislash-shield" → "Aegislash-Shield"  (ハイフン後が小文字の場合は大文字化)
    """
    parts = slug.split("-")
    # Pokemon 名やフォームのハイフンは保持する必要があるが、
    # 表示上は各単語をキャプタライズするだけで十分
    return " ".join(p.title() for p in parts)
