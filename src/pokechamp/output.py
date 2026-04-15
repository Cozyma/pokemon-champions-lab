from __future__ import annotations
import json
from pokechamp.models import BattleResult, MatchupResult


def format_battle_result(result: BattleResult, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
    lines = [
        f"=== {result.pokemon_a} vs {result.pokemon_b} ===",
        "",
        f"  {result.pokemon_a}: 勝率 {result.win_rate_a * 100:.1f}%  平均残HP {result.avg_remaining_hp_a:.1f}",
        f"  {result.pokemon_b}: 勝率 {result.win_rate_b * 100:.1f}%  平均残HP {result.avg_remaining_hp_b:.1f}",
    ]
    return "\n".join(lines)


def format_matchup_result(result: MatchupResult, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
    lines = [f"=== {result.team_a} vs {result.team_b} ===", "", "【対面マトリクス】(A勝率%)"]
    name_width = max(len(n) for n in result.matrix.team_a_names + result.matrix.team_b_names) + 2
    header = " " * name_width + "".join(f"{n:>{name_width}}" for n in result.matrix.team_b_names)
    lines.append(header)
    for i, name_a in enumerate(result.matrix.team_a_names):
        row_str = f"{name_a:<{name_width}}"
        for j in range(len(result.matrix.team_b_names)):
            rate = result.matrix.matrix[i][j]
            row_str += f"{rate * 100:>{name_width - 1}.1f}%"
        lines.append(row_str)
    if result.setup_evaluations:
        lines.append("")
        lines.append("【展開評価】")
        for se in result.setup_evaluations:
            sign = "+" if se.delta > 0 else ""
            lines.append(f"  {se.pokemon} ({se.move}): {se.base_win_rate * 100:.1f}% → {se.setup_win_rate * 100:.1f}% ({sign}{se.delta * 100:.1f}%)")
    if result.selection_ranking:
        lines.append("")
        lines.append("【推奨選出】")
        for rank, sel in enumerate(result.selection_ranking, 1):
            a_str = " / ".join(sel.team_a_selection)
            lines.append(f"  {rank}. {a_str}  スコア: {sel.score * 100:.1f}")
    lines.append("")
    lines.append(f"総合スコア: {result.overall_score * 100:.1f}")
    return "\n".join(lines)
