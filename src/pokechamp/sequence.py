"""3v3 シーケンス評価

選出3体ずつの対面を交代込みでシミュレーションし、勝敗を判定する。
"""
from __future__ import annotations

import math
import random

from pokechamp.battle import (
    BattlePokemon,
    _WEATHER_ABILITIES,
    _calc_all_moves,
    simulate_1v1,
)
from pokechamp.models import SequenceResult


def _quick_win_estimate(
    a: BattlePokemon,
    b: BattlePokemon,
    hp_a: int,
    hp_b: int,
    weather: str,
) -> float:
    """Fast win rate estimate based on damage ranges (no Monte Carlo).

    Compare: turns for a to KO b vs turns for b to KO a.
    Factor in speed (who attacks first).
    """
    all_moves_a = _calc_all_moves(a, b, weather=weather)
    all_moves_b = _calc_all_moves(b, a, weather=weather)

    if not all_moves_a:
        return 0.0
    if not all_moves_b:
        return 1.0

    best_a = max(all_moves_a, key=lambda x: sum(x[1]) / len(x[1]))
    best_b = max(all_moves_b, key=lambda x: sum(x[1]) / len(x[1]))

    avg_dmg_a = sum(best_a[1]) / len(best_a[1])
    avg_dmg_b = sum(best_b[1]) / len(best_b[1])

    if avg_dmg_a <= 0:
        return 0.0
    if avg_dmg_b <= 0:
        return 1.0

    turns_to_ko_b = math.ceil(hp_b / avg_dmg_a)
    turns_to_ko_a = math.ceil(hp_a / avg_dmg_b)

    speed_a = a.get_effective_stat("speed")
    speed_b = b.get_effective_stat("speed")

    # Faster pokemon gets an extra "half turn" advantage
    if speed_a > speed_b:
        if turns_to_ko_b <= turns_to_ko_a:
            return 0.85  # faster and KOs in same or fewer turns
        else:
            return 0.3
    elif speed_b > speed_a:
        if turns_to_ko_a <= turns_to_ko_b:
            return 0.15
        else:
            return 0.7
    else:
        return 0.5 if turns_to_ko_a == turns_to_ko_b else (0.6 if turns_to_ko_b < turns_to_ko_a else 0.4)


def _should_switch(
    current: BattlePokemon,
    opponent: BattlePokemon,
    bench: list[tuple[BattlePokemon, int]],  # (pokemon, current_hp) pairs
    weather: str,
    hp_current: int,
    hp_opponent: int,
) -> tuple[bool, int | None]:
    """Decide if current pokemon should switch out.

    Returns: (should_switch, bench_index_to_switch_to)

    Logic:
    1. Compute current matchup win rate (quick estimate using damage ranges)
    2. If win_rate > 0.3, don't switch (can fight)
    3. For each bench pokemon:
       a. Predict opponent's best move damage against bench pokemon
       b. Estimate bench pokemon's HP after taking the hit
       c. Compute bench pokemon's win rate vs opponent at reduced HP
    4. If best bench option has win_rate > current win_rate + 0.2, switch
    """
    if not bench:
        return False, None

    current_win_rate = _quick_win_estimate(current, opponent, hp_current, hp_opponent, weather)

    if current_win_rate > 0.3:
        return False, None

    # Evaluate each bench pokemon
    best_switch_win_rate = current_win_rate
    best_switch_idx = None

    for bench_idx, (bench_mon, bench_hp) in enumerate(bench):
        # Predict switch-in damage from opponent's best move
        all_moves_opp_vs_bench = _calc_all_moves(opponent, bench_mon, weather=weather)
        if all_moves_opp_vs_bench:
            best_move_opp = max(all_moves_opp_vs_bench, key=lambda x: sum(x[1]) / len(x[1]))
            avg_switch_dmg = sum(best_move_opp[1]) / len(best_move_opp[1])
        else:
            avg_switch_dmg = 0.0

        # Estimate bench HP after taking switch-in hit
        post_switch_hp = max(1, bench_hp - int(avg_switch_dmg))

        # Win rate of bench mon vs opponent at reduced HP
        bench_win_rate = _quick_win_estimate(bench_mon, opponent, post_switch_hp, hp_opponent, weather)

        if bench_win_rate > best_switch_win_rate:
            best_switch_win_rate = bench_win_rate
            best_switch_idx = bench_idx

    # Only switch if bench option is significantly better
    if best_switch_idx is not None and best_switch_win_rate > current_win_rate + 0.2:
        return True, best_switch_idx

    return False, None


def _simulate_one_sequence(
    team_a: list[BattlePokemon],
    team_b: list[BattlePokemon],
    weather: str,
) -> tuple[bool, int, int, list[str]]:
    """Simulate one 3v3 sequence.

    Returns: (a_wins, remaining_a, remaining_b, log)
    """
    size_a = len(team_a)
    size_b = len(team_b)
    hp_a = [p.stats["hp"] for p in team_a]
    hp_b = [p.stats["hp"] for p in team_b]
    alive_a = [True] * size_a
    alive_b = [True] * size_b
    idx_a = 0
    idx_b = 0
    log: list[str] = []
    max_turns = 100  # safety limit

    for _turn in range(max_turns):
        # Ensure we have alive pokemon on both sides
        alive_idx_a = [i for i in range(size_a) if alive_a[i]]
        alive_idx_b = [i for i in range(size_b) if alive_b[i]]
        if not alive_idx_a or not alive_idx_b:
            break

        # Advance active index to an alive pokemon
        if not alive_a[idx_a]:
            idx_a = alive_idx_a[0]
        if not alive_b[idx_b]:
            idx_b = alive_idx_b[0]

        cur_a = team_a[idx_a]
        cur_b = team_b[idx_b]

        # Switch decision for a
        bench_a_pairs = [(team_a[i], hp_a[i]) for i in range(size_a) if alive_a[i] and i != idx_a]
        should_switch_a, switch_idx_a = _should_switch(
            cur_a, cur_b, bench_a_pairs, weather, hp_a[idx_a], hp_b[idx_b],
        )

        if should_switch_a and switch_idx_a is not None:
            # Find the actual team index for this bench slot
            bench_indices_a = [i for i in range(size_a) if alive_a[i] and i != idx_a]
            new_idx = bench_indices_a[switch_idx_a]
            incoming = team_a[new_idx]

            # Incoming pokemon takes a hit from opponent's best move
            all_moves_b_vs_incoming = _calc_all_moves(cur_b, incoming, weather=weather)
            if all_moves_b_vs_incoming:
                best_move_b = max(all_moves_b_vs_incoming, key=lambda x: sum(x[1]) / len(x[1]))
                switch_damage = random.choice(best_move_b[1])
                hp_a[new_idx] -= switch_damage
                if hp_a[new_idx] <= 0:
                    hp_a[new_idx] = 0
                    alive_a[new_idx] = False
                    log.append(f"{incoming.name} switched in but fainted to {cur_b.name}")
                    next_alive = [i for i in range(size_a) if alive_a[i]]
                    if not next_alive:
                        break
                    idx_a = next_alive[0]
                    continue

            idx_a = new_idx
            log.append(f"A switched to {team_a[idx_a].name}")
            continue  # switch turn - no attack from a this turn

        # Note: stat stage changes (boosts/debuffs) are automatically reset when a
        # pokemon switches out, because each simulate_1v1 call starts with fresh stages.
        # This correctly models the game behavior where switching resets all stat changes.

        # Run 1v1 to completion with current HPs (n_trials=1 for single deterministic trial)
        result = simulate_1v1(
            cur_a, cur_b,
            hp_a=hp_a[idx_a], hp_b=hp_b[idx_b],
            n_trials=1,
        )

        if result.win_rate_a > 0.5:
            # a wins this matchup
            hp_a[idx_a] = max(1, int(result.avg_remaining_hp_a))
            hp_b[idx_b] = 0
            alive_b[idx_b] = False
            log.append(f"{cur_a.name}(HP{hp_a[idx_a]}) beat {cur_b.name}")
            next_b = [i for i in range(size_b) if alive_b[i]]
            if not next_b:
                break
            idx_b = next_b[0]
        else:
            # b wins this matchup
            hp_b[idx_b] = max(1, int(result.avg_remaining_hp_b))
            hp_a[idx_a] = 0
            alive_a[idx_a] = False
            log.append(f"{cur_b.name}(HP{hp_b[idx_b]}) beat {cur_a.name}")
            next_a = [i for i in range(size_a) if alive_a[i]]
            if not next_a:
                break
            idx_a = next_a[0]

    remaining_a = sum(alive_a)
    remaining_b = sum(alive_b)
    a_wins = remaining_a > remaining_b
    return a_wins, remaining_a, remaining_b, log


def evaluate_sequence(
    team_a: list[BattlePokemon],
    team_b: list[BattlePokemon],
    n_trials: int = 500,
) -> SequenceResult:
    """3v3 sequence battle simulation.

    For each trial:
    1. Start with team_a[0] vs team_b[0]
    2. Each turn, the losing side may switch (see switching logic)
    3. When a pokemon faints, next pokemon comes in
    4. Continue until one side has no pokemon left

    Returns aggregate win rate and sample log.
    """
    # Determine weather based on lead pokemon abilities
    weather = "none"
    for ability_name, weather_type in _WEATHER_ABILITIES.items():
        if team_a[0].ability == ability_name:
            weather = weather_type
        if team_b[0].ability == ability_name:
            weather = weather_type  # last one wins

    wins_a = 0
    total_rem_a = 0
    total_rem_b = 0
    sample_log: list[str] | None = None

    for _trial in range(n_trials):
        a_wins, rem_a, rem_b, log = _simulate_one_sequence(team_a, team_b, weather)
        if a_wins:
            wins_a += 1
        total_rem_a += rem_a
        total_rem_b += rem_b
        if sample_log is None:
            sample_log = log

    return SequenceResult(
        team_a_selection=[p.name for p in team_a],
        team_b_selection=[p.name for p in team_b],
        win_rate_a=wins_a / n_trials,
        avg_remaining_a=total_rem_a / n_trials,
        avg_remaining_b=total_rem_b / n_trials,
        sample_log=sample_log or [],
    )
