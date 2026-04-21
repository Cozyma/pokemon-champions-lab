#!/usr/bin/env python3
"""Parse Showdown replays into (state, action) training pairs.

Each turn produces one training sample per player:
- state: observable battle state at decision time
- action: what the player chose (move N or switch to species)

Usage:
    python scripts/parse_replays.py
    python scripts/parse_replays.py --min-rating 1400

Output: data/replays/training_data.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPLAY_DIR = Path(__file__).resolve().parent.parent / "data" / "replays"


def parse_replay(log_text: str) -> list[dict]:
    """Parse a single replay log into training samples.

    Returns list of dicts with:
        player: "p1" or "p2"
        turn: int
        action_type: "move" | "switch" | "mega_move"
        action_detail: move name or switch species
        team_preview: {p1: [species...], p2: [species...]}
        selected: [species...] (3 selected pokemon for this player)
        active_species: str (species on field at decision time)
        active_hp_pct: float
        opp_active_species: str
        opp_active_hp_pct: float
        team_hp: {species: hp_pct} (own team HP)
        opp_known_hp: {species: hp_pct} (opponent known HP)
        weather: str
        winner: "p1" | "p2" | None
    """
    lines = log_text.split("\n")
    samples: list[dict] = []

    # --- Phase 1: Parse metadata ---
    team_preview: dict[str, list[str]] = {"p1": [], "p2": []}
    winner: str | None = None
    player_ratings: dict[str, int] = {}

    for line in lines:
        # |poke|p1|Garchomp, L50, M|
        m = re.match(r"\|poke\|(p[12])\|([^,|]+)", line)
        if m:
            team_preview[m.group(1)].append(m.group(2).strip())

        # |player|p1|name|avatar|rating
        m = re.match(r"\|player\|(p[12])\|[^|]+\|[^|]+\|(\d+)", line)
        if m:
            player_ratings[m.group(1)] = int(m.group(2))

        if line.startswith("|win|"):
            winner_name = line.split("|")[2].strip()
            # Determine p1/p2 from player lines
            for pline in lines:
                pm = re.match(r"\|player\|(p[12])\|(.+?)\|", pline)
                if pm and pm.group(2).strip() == winner_name:
                    winner = pm.group(1)
                    break

    # --- Phase 2: Track battle state turn by turn ---
    turn = 0
    # Current active pokemon per player
    active: dict[str, str] = {"p1": "", "p2": ""}
    # HP tracking: {player: {species: "cur/max" or "0 fnt"}}
    hp: dict[str, dict[str, float]] = {"p1": {}, "p2": {}}
    # Selected pokemon (first 3 unique switches before/at turn 1)
    selected: dict[str, list[str]] = {"p1": [], "p2": []}
    # Weather
    weather = ""
    # Mega evolution tracking
    mega_this_turn: dict[str, bool] = {"p1": False, "p2": False}
    # Actions collected for current turn (before appending)
    pre_turn1 = True

    for line in lines:
        # Turn marker
        m = re.match(r"\|turn\|(\d+)", line)
        if m:
            turn = int(m.group(1))
            mega_this_turn = {"p1": False, "p2": False}
            if turn > 0:
                pre_turn1 = False
            continue

        # Switch (includes initial leads and mid-battle switches)
        m = re.match(r"\|switch\|(p[12])a: ([^|]+)\|([^|]+)\|([^|]*)", line)
        if m:
            player = m.group(1)
            species = m.group(2).strip()
            details = m.group(3).strip()  # "Garchomp, L50, M"
            hp_str = m.group(4).strip()  # "183/183" or "100/100"
            base_species = details.split(",")[0].strip()

            active[player] = species

            # Parse HP
            hp_m = re.match(r"(\d+)/(\d+)", hp_str)
            if hp_m:
                hp[player][species] = int(hp_m.group(1)) / int(hp_m.group(2)) * 100
            else:
                hp[player][species] = 100.0

            # Track selected pokemon (first appearances)
            if species not in selected[player] and len(selected[player]) < 3:
                selected[player].append(species)

            # Record switch action (not for initial leads)
            if turn > 0 and "[from]" not in line:
                opp = "p2" if player == "p1" else "p1"
                sample = _make_sample(
                    player=player,
                    turn=turn,
                    action_type="switch",
                    action_detail=species,
                    team_preview=team_preview,
                    selected=selected[player],
                    active=active,
                    hp=hp,
                    weather=weather,
                    winner=winner,
                    opp=opp,
                )
                samples.append(sample)
            continue

        # Mega evolution
        m = re.match(r"\|-mega\|(p[12])a:", line)
        if m:
            mega_this_turn[m.group(1)] = True
            continue

        # Move
        m = re.match(r"\|move\|(p[12])a: ([^|]+)\|([^|]+)", line)
        if m:
            player = m.group(1)
            move_name = m.group(3).strip()
            opp = "p2" if player == "p1" else "p1"

            # Skip [from] lockedmove etc
            if "[from]" in line:
                continue

            action_type = "mega_move" if mega_this_turn.get(player) else "move"

            sample = _make_sample(
                player=player,
                turn=turn,
                action_type=action_type,
                action_detail=move_name,
                team_preview=team_preview,
                selected=selected[player],
                active=active,
                hp=hp,
                weather=weather,
                winner=winner,
                opp=opp,
            )
            samples.append(sample)
            continue

        # Damage
        m = re.match(r"\|-damage\|(p[12])a: ([^|]+)\|([^|]+)", line)
        if m:
            player = m.group(1)
            species = m.group(2).strip()
            hp_str = m.group(3).strip().split()[0]  # "50/183" or "0 fnt"
            hp_m = re.match(r"(\d+)/(\d+)", hp_str)
            if hp_m:
                hp[player][species] = int(hp_m.group(1)) / int(hp_m.group(2)) * 100
            elif "fnt" in hp_str:
                hp[player][species] = 0.0
            continue

        # Heal
        m = re.match(r"\|-heal\|(p[12])a: ([^|]+)\|([^|]+)", line)
        if m:
            player = m.group(1)
            species = m.group(2).strip()
            hp_str = m.group(3).strip().split()[0]
            hp_m = re.match(r"(\d+)/(\d+)", hp_str)
            if hp_m:
                hp[player][species] = int(hp_m.group(1)) / int(hp_m.group(2)) * 100
            continue

        # Faint
        m = re.match(r"\|faint\|(p[12])a: (.+)", line)
        if m:
            player = m.group(1)
            species = m.group(2).strip()
            hp[player][species] = 0.0
            continue

        # Weather
        m = re.match(r"\|-weather\|(\w+)", line)
        if m:
            w = m.group(1).lower()
            weather = "" if w == "none" else w
            continue

    # Post-process: backfill full selected teams from final state
    # Each replay has a definitive set of 3 selected per player
    final_selected: dict[str, list[str]] = {"p1": list(selected.get("p1", [])),
                                             "p2": list(selected.get("p2", []))}
    for s in samples:
        player = s["player"]
        opp = "p2" if player == "p1" else "p1"
        s["selected_full"] = final_selected.get(player, [])
        s["opp_selected_full"] = final_selected.get(opp, [])

    return samples


def _make_sample(
    player: str,
    turn: int,
    action_type: str,
    action_detail: str,
    team_preview: dict[str, list[str]],
    selected: list[str],
    active: dict[str, str],
    hp: dict[str, dict[str, float]],
    weather: str,
    winner: str | None,
    opp: str,
) -> dict:
    """Create a training sample dict."""
    return {
        "player": player,
        "turn": turn,
        "action_type": action_type,
        "action_detail": action_detail,
        "team_preview_self": team_preview[player],
        "team_preview_opp": team_preview[opp],
        "selected_known": list(selected),  # what's known at this point in time
        "active_species": active.get(player, ""),
        "active_hp_pct": hp.get(player, {}).get(active.get(player, ""), 100.0),
        "opp_active_species": active.get(opp, ""),
        "opp_active_hp_pct": hp.get(opp, {}).get(active.get(opp, ""), 100.0),
        "team_hp": dict(hp.get(player, {})),
        "opp_known_hp": dict(hp.get(opp, {})),
        "weather": weather,
        "winner": winner,
        "won": winner == player,
        # selected_full and opp_selected_full are added in post-processing
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse replays into training data")
    parser.add_argument("--min-rating", type=int, default=1300, help="Minimum rating")
    args = parser.parse_args()

    index = json.loads((REPLAY_DIR / "index.json").read_text())
    filtered = [r for r in index if r.get("rating", 0) >= args.min_rating]
    print(f"Parsing {len(filtered)} replays (rating {args.min_rating}+)...")

    all_samples: list[dict] = []
    errors = 0

    for i, meta in enumerate(filtered):
        replay_path = REPLAY_DIR / f"{meta['id']}.json"
        if not replay_path.exists():
            errors += 1
            continue

        try:
            replay = json.loads(replay_path.read_text())
            samples = parse_replay(replay["log"])
            # Add metadata
            for s in samples:
                s["replay_id"] = meta["id"]
                s["replay_rating"] = meta.get("rating")
            all_samples.extend(samples)
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  Error parsing {meta['id']}: {e}")

    # Stats
    move_count = sum(1 for s in all_samples if s["action_type"] == "move")
    mega_count = sum(1 for s in all_samples if s["action_type"] == "mega_move")
    switch_count = sum(1 for s in all_samples if s["action_type"] == "switch")
    won_count = sum(1 for s in all_samples if s["won"])

    print(f"\nParsed {len(all_samples)} samples from {len(filtered) - errors} replays")
    print(f"  Moves: {move_count}, Mega moves: {mega_count}, Switches: {switch_count}")
    print(f"  From winners: {won_count}, From losers: {len(all_samples) - won_count}")
    print(f"  Errors: {errors}")

    # Save
    out_path = REPLAY_DIR / "training_data.json"
    out_path.write_text(json.dumps(all_samples, indent=2))
    print(f"\nSaved to {out_path} ({len(all_samples)} samples)")


if __name__ == "__main__":
    main()
