"""Battle quality metrics extracted from Showdown battle logs.

Analyzes action quality beyond win/loss:
1. Wasted actions: moves that deal 0 damage (immune/no effect)
2. Setup efficiency: did boosts lead to KOs?
3. Switch ROI: did switches gain or lose action turns?
"""
from __future__ import annotations

import re

from pokechamp import showdown_data


def analyze_battle(log_lines: list[str], player_id: str = "p1") -> dict:
    """Analyze battle log and return quality metrics for the given player.

    Returns dict with:
        wasted_moves: int — moves that dealt 0 damage (immune)
        total_moves: int — total attack moves used
        setup_attempts: int — setup moves used
        setup_kos: int — KOs achieved while boosted (setup paid off)
        setup_wasted: int — setup moves where boosts were lost before KO
        switch_count: int — voluntary switches (not forced)
        switch_gained: int — switches where new pokemon had better matchup
        switch_lost: int — switches where new pokemon fainted within 2 turns
        turns: int — total battle turns
    """
    opp_id = "p2" if player_id == "p1" else "p1"

    metrics = {
        "wasted_moves": 0,
        "total_moves": 0,
        "setup_attempts": 0,
        "setup_kos": 0,
        "setup_wasted": 0,
        "switch_count": 0,
        "switch_gained": 0,
        "switch_lost": 0,
        "turns": 0,
    }

    # Track state
    current_species = ""
    has_boosts = False
    boost_count = 0  # how many setup moves used since last switch-in
    turns_since_switch = 0
    switched_this_turn = False
    switch_species = ""

    for i, line in enumerate(log_lines):
        line = line.strip()

        # Track turns
        if "|turn|" in line:
            m = re.match(r"\|turn\|(\d+)", line)
            if m:
                metrics["turns"] = int(m.group(1))
            switched_this_turn = False
            turns_since_switch += 1

        # Track our switch-ins
        if f"|switch|{player_id}a:" in line and "[from]" not in line:
            parts = line.split("|")
            if len(parts) > 3:
                new_species = parts[3].split(",")[0].strip()
                if current_species and not _is_forced_switch(log_lines, i, player_id):
                    # Voluntary switch
                    metrics["switch_count"] += 1
                    switched_this_turn = True
                    switch_species = new_species
                    turns_since_switch = 0

                    # If we had boosts and switched out, those boosts are wasted
                    if has_boosts:
                        metrics["setup_wasted"] += boost_count

                current_species = new_species
                has_boosts = False
                boost_count = 0

        # Track our moves
        if f"|move|{player_id}a:" in line:
            parts = line.split("|")
            if len(parts) > 3:
                move_name = parts[3].strip()
                move_id = move_name.lower().replace(" ", "").replace("-", "")
                sd = showdown_data.get_move(move_id)

                if sd:
                    bp = sd.get("basePower", 0)
                    category = sd.get("category", "")

                    if category == "Status" and sd.get("boosts"):
                        # Setup move
                        target = sd.get("target", "")
                        if target == "self":
                            metrics["setup_attempts"] += 1
                            has_boosts = True
                            boost_count += 1
                    elif bp > 0:
                        # Attack move
                        metrics["total_moves"] += 1

                        # Check if it was immune
                        # Look ahead for -immune, but only count as "wasted" if
                        # the opponent did NOT switch this turn (i.e., we should
                        # have known the type matchup was immune).
                        is_immune = False
                        opp_switched_this_turn = False
                        for j in range(i + 1, min(i + 5, len(log_lines))):
                            check = log_lines[j].strip()
                            if f"|-immune|{opp_id}a:" in check:
                                is_immune = True
                                break
                            if "|move|" in check or "|turn|" in check:
                                break
                        # Check if opponent switched in this same turn
                        # (look backward from our move for opponent switch)
                        if is_immune:
                            for j in range(i - 1, max(i - 10, 0), -1):
                                check = log_lines[j].strip()
                                if "|turn|" in check:
                                    break
                                if f"|switch|{opp_id}a:" in check:
                                    opp_switched_this_turn = True
                                    break
                            if not opp_switched_this_turn:
                                # We knew the opponent's type and still used
                                # an immune move — this is a true wasted action
                                metrics["wasted_moves"] += 1

        # Track opponent fainting (did our boosts lead to this?)
        if f"|faint|{opp_id}a:" in line:
            if has_boosts:
                metrics["setup_kos"] += 1

        # Track our pokemon fainting after switch
        if f"|faint|{player_id}a:" in line:
            if switched_this_turn or turns_since_switch <= 2:
                if switch_species and switch_species in (current_species or ""):
                    metrics["switch_lost"] += 1
            # Reset boost tracking
            has_boosts = False
            boost_count = 0

        # Detect if switch led to better matchup
        # Simple heuristic: if we attack on the turn after switching and it's
        # super effective, the switch was good
        if (switched_this_turn and f"|move|{player_id}a:" in line
                and "|-supereffective|" in _peek_ahead(log_lines, i)):
            metrics["switch_gained"] += 1
            switched_this_turn = False

    return metrics


def _is_forced_switch(log_lines: list[str], switch_idx: int, player_id: str) -> bool:
    """Check if a switch was forced (after faint or by move effect)."""
    # Look backward for faint or drag
    for j in range(switch_idx - 1, max(switch_idx - 5, 0), -1):
        line = log_lines[j].strip()
        if f"|faint|{player_id}a:" in line:
            return True
        if "|turn|" in line:
            break
    return False


def _peek_ahead(log_lines: list[str], idx: int) -> str:
    """Return next few lines concatenated for checking."""
    return " ".join(log_lines[idx + 1:idx + 5])


def summarize_metrics(metrics_list: list[dict]) -> dict:
    """Summarize metrics across multiple battles."""
    total = {
        "battles": len(metrics_list),
        "wasted_moves": sum(m["wasted_moves"] for m in metrics_list),
        "total_moves": sum(m["total_moves"] for m in metrics_list),
        "wasted_rate": 0.0,
        "setup_attempts": sum(m["setup_attempts"] for m in metrics_list),
        "setup_kos": sum(m["setup_kos"] for m in metrics_list),
        "setup_wasted": sum(m["setup_wasted"] for m in metrics_list),
        "setup_success_rate": 0.0,
        "switch_count": sum(m["switch_count"] for m in metrics_list),
        "switch_gained": sum(m["switch_gained"] for m in metrics_list),
        "switch_lost": sum(m["switch_lost"] for m in metrics_list),
        "switch_roi": 0.0,
        "avg_turns": sum(m["turns"] for m in metrics_list) / max(len(metrics_list), 1),
    }

    if total["total_moves"] > 0:
        total["wasted_rate"] = total["wasted_moves"] / total["total_moves"]

    if total["setup_attempts"] > 0:
        total["setup_success_rate"] = total["setup_kos"] / total["setup_attempts"]

    if total["switch_count"] > 0:
        total["switch_roi"] = (total["switch_gained"] - total["switch_lost"]) / total["switch_count"]

    return total


def format_metrics(summary: dict) -> str:
    """Format summary metrics as a readable string."""
    lines = [
        f"Battles: {summary['battles']}",
        f"Avg turns: {summary['avg_turns']:.1f}",
        f"Wasted moves: {summary['wasted_moves']}/{summary['total_moves']}"
        f" ({summary['wasted_rate']:.1%})",
        f"Setup: {summary['setup_kos']} KOs / {summary['setup_attempts']} attempts"
        f" ({summary['setup_success_rate']:.0%} success)"
        f", {summary['setup_wasted']} wasted",
        f"Switches: {summary['switch_count']} total"
        f", +{summary['switch_gained']} gained"
        f", -{summary['switch_lost']} lost"
        f" (ROI: {summary['switch_roi']:+.2f})",
    ]
    return "\n".join(lines)
