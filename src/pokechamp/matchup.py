"""構築マッチアップ評価モジュール

BattlePokemonリストの構築と6x6 1v1シミュレーションによるマッチアップ評価を提供する。
"""
from __future__ import annotations

from itertools import combinations

from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.loader import load_team
from pokechamp.models import (
    MatchupMatrix,
    MatchupResult,
    SelectionScore,
    SequenceResult,
    SetupEvaluation,
    Team,
    TeamMember,
)
from pokechamp.sequence import evaluate_sequence


def _is_mega_member(member: TeamMember) -> bool:
    """チームメンバーがメガストーンを持っているか判定する."""
    from pokechamp.loader import load_pokemon
    pokemon = load_pokemon(member.species)
    for mega_field in (pokemon.mega, pokemon.mega_x, pokemon.mega_y):
        if mega_field is not None and mega_field.stone == member.item:
            return True
    return False


def build_battle_pokemon_from_team(team: Team) -> list[BattlePokemon]:
    """チーム定義からBattlePokemonリストを構築."""
    return [_member_to_battle_pokemon(member) for member in team.pokemon]


def _member_to_battle_pokemon(member: TeamMember) -> BattlePokemon:
    """TeamMemberからBattlePokemonを生成する."""
    return BattlePokemon.from_data(
        species=member.species,
        nature=member.nature,
        evs=member.evs.model_dump(),
        ivs=member.ivs.model_dump(),
        item=member.item,
        move_names=member.moves,
        level=50,
    )


def _find_setup_moves(bp: BattlePokemon) -> list[str]:
    """積み技を持っているか判定 — stat_changesを持つ技を返す."""
    return [move.name_en for move in bp.moves if move.stat_changes]


def evaluate_matchup(
    team_a_name: str,
    team_b_name: str,
    with_setup: bool = True,
    n_trials: int = 1000,
) -> MatchupResult:
    """2構築間のマッチアップを評価する.

    1. 両チームをロードしてBattlePokemonリストを構築
    2. NxM 1v1シミュレーション → matrix
       IMPORTANT: シミュレーションごとにフレッシュなBattlePokemonインスタンスを生成
    3. with_setup時: 積み技持ちポケモンについてsetup_turns=1でもシミュレーション実行
       deltaが1%超の場合にSetupEvaluationとして記録
    4. 選出ランキング: C(n,3) x C(m,3)の組み合わせをスコアリング
       3体未満の場合は全員を使用
    5. 総合スコア = matrixの平均
    6. MatchupResultを返す
    """
    team_a = load_team(team_a_name)
    team_b = load_team(team_b_name)

    members_a = team_a.pokemon
    members_b = team_b.pokemon

    names_a = [m.species for m in members_a]
    names_b = [m.species for m in members_b]

    # NxM matrixを構築: matrix[i][j] = aのiがbのjに対する勝率
    n = len(members_a)
    m = len(members_b)
    matrix: list[list[float]] = [[0.0] * m for _ in range(n)]

    for i, member_a in enumerate(members_a):
        for j, member_b in enumerate(members_b):
            bp_a = _member_to_battle_pokemon(member_a)
            bp_b = _member_to_battle_pokemon(member_b)
            result = simulate_1v1(bp_a, bp_b, n_trials=n_trials)
            matrix[i][j] = result.win_rate_a

    matchup_matrix = MatchupMatrix(
        team_a_names=names_a,
        team_b_names=names_b,
        matrix=matrix,
    )

    # 積み技評価
    setup_evaluations: list[SetupEvaluation] = []
    if with_setup:
        for i, member_a in enumerate(members_a):
            bp_sample = _member_to_battle_pokemon(member_a)
            setup_moves = _find_setup_moves(bp_sample)
            if not setup_moves:
                continue

            for setup_move in setup_moves:
                # 全対戦相手に対する基本勝率と積み勝率の平均を比較
                base_win_rates = []
                setup_win_rates = []

                for j, member_b in enumerate(members_b):
                    base_win_rates.append(matrix[i][j])

                    # フレッシュなインスタンスを生成してsetup_turns=1でシミュレーション
                    bp_a_setup = _member_to_battle_pokemon(member_a)
                    bp_b_setup = _member_to_battle_pokemon(member_b)
                    result_setup = simulate_1v1(
                        bp_a_setup,
                        bp_b_setup,
                        setup_move=setup_move,
                        setup_turns=1,
                        n_trials=n_trials,
                    )
                    setup_win_rates.append(result_setup.win_rate_a)

                avg_base = sum(base_win_rates) / len(base_win_rates)
                avg_setup = sum(setup_win_rates) / len(setup_win_rates)
                delta = avg_setup - avg_base

                if delta > 0.01:
                    setup_evaluations.append(
                        SetupEvaluation(
                            pokemon=member_a.species,
                            move=setup_move,
                            base_win_rate=avg_base,
                            setup_win_rate=avg_setup,
                            delta=delta,
                        )
                    )

    # メガフラグを計算
    is_mega_a = [_is_mega_member(m) for m in members_a]
    is_mega_b = [_is_mega_member(m) for m in members_b]

    # 選出ランキング
    selection_ranking = _rank_selections(names_a, names_b, matrix, is_mega_a=is_mega_a, is_mega_b=is_mega_b)

    # 総合スコア = matrixの全要素の平均
    all_values = [matrix[i][j] for i in range(n) for j in range(m)]
    overall_score = sum(all_values) / len(all_values) if all_values else 0.5

    # 選出上位3件についてシーケンスバトル評価
    sequence_results: list[SequenceResult] = []
    for sel in selection_ranking[:3]:
        bp_sel_a = [
            _member_to_battle_pokemon(members_a[names_a.index(name)])
            for name in sel.team_a_selection
        ]
        bp_sel_b = [
            _member_to_battle_pokemon(members_b[names_b.index(name)])
            for name in sel.team_b_selection
        ]
        seq = evaluate_sequence(bp_sel_a, bp_sel_b, n_trials=200)
        sequence_results.append(seq)

    return MatchupResult(
        team_a=team_a.name,
        team_b=team_b.name,
        matrix=matchup_matrix,
        setup_evaluations=setup_evaluations,
        selection_ranking=selection_ranking,
        overall_score=overall_score,
        sequence_results=sequence_results,
    )


def _rank_selections(
    names_a: list[str],
    names_b: list[str],
    matrix: list[list[float]],
    top_n: int = 5,
    is_mega_a: list[bool] | None = None,
    is_mega_b: list[bool] | None = None,
) -> list[SelectionScore]:
    """C(n,3) x C(m,3) の全選出組み合わせを生成してスコアリングする.

    チームが3体未満の場合は全員を使用。
    メガ制約: 各選出にメガシンカポケモンは1体まで。
    """
    size_a = len(names_a)
    size_b = len(names_b)

    mega_a = is_mega_a if is_mega_a is not None else [False] * size_a
    mega_b = is_mega_b if is_mega_b is not None else [False] * size_b

    # 選出候補のインデックス組み合わせを生成
    if size_a >= 3:
        sels_a = list(combinations(range(size_a), 3))
    else:
        sels_a = [tuple(range(size_a))]

    if size_b >= 3:
        sels_b = list(combinations(range(size_b), 3))
    else:
        sels_b = [tuple(range(size_b))]

    scored: list[SelectionScore] = []
    for sel_a in sels_a:
        # メガ制約: 選出内のメガシンカポケモンは1体まで
        if sum(1 for i in sel_a if mega_a[i]) > 1:
            continue
        for sel_b in sels_b:
            # メガ制約: 選出内のメガシンカポケモンは1体まで
            if sum(1 for j in sel_b if mega_b[j]) > 1:
                continue

            # この選出の平均勝率を計算
            rates = [matrix[i][j] for i in sel_a for j in sel_b]
            score = sum(rates) / len(rates) if rates else 0.5

            scored.append(
                SelectionScore(
                    team_a_selection=[names_a[i] for i in sel_a],
                    team_b_selection=[names_b[j] for j in sel_b],
                    score=score,
                )
            )

    # スコア降順でソートしてtop_nを返す
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:top_n]
