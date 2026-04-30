#!/usr/bin/env python3
"""Self-play training: RL vs past versions of itself.

Both sides use (selection_model + battle_model).
p1 trains, p2 uses a snapshot from the opponent pool.
Periodically snapshots p1 into the pool.

Usage:
    python scripts/train_selfplay.py \
        --selection-model models/selection_best \
        --battle-model models/ppo_masked_best \
        --rounds 10 --steps-per-round 2000
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from sb3_contrib import MaskablePPO  # noqa: E402
from pokechamp.selection_env import SelectionEnv  # noqa: E402

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RESULTS_PATH = MODELS_DIR / "selfplay_results.json"

EVAL_GAMES = 20  # games per evaluation round


def load_teams() -> dict[str, str]:
    return {t.parent.name: t.read_text()
            for t in TEAMS_DIR.glob("*/team.txt")
            if not t.parent.name.startswith("test-")}


def evaluate_vs_heuristic(
    selection_model, battle_model,
    p1_paste: str, teams: dict[str, str],
    n_per_opp: int = 10,
) -> dict:
    """Evaluate against heuristic opponents (regression check)."""
    results = {}
    for opp_name, opp_paste in sorted(teams.items()):
        wins = 0
        for _ in range(n_per_opp):
            ev = SelectionEnv(
                team_paste=p1_paste,
                opponent_paste=opp_paste,
                battle_model=battle_model,
            )
            obs, _ = ev.reset()
            action, _ = selection_model.predict(obs, deterministic=True)
            _, _, _, _, info = ev.step(int(action))
            ev.close()
            if info.get("winner") == "p1":
                wins += 1
        results[opp_name] = {"wins": wins, "games": n_per_opp}
    return results


def evaluate_vs_self(
    p1_sel, p1_bat, p2_sel, p2_bat,
    p1_paste: str, n_games: int = 20,
) -> float:
    """Play p1 vs p2 (both RL) and return p1 win rate."""
    wins = 0
    for _ in range(n_games):
        ev = SelectionEnv(
            team_paste=p1_paste,
            opponent_paste=p1_paste,  # mirror match
            battle_model=p1_bat,
            p2_selection_model=p2_sel,
            p2_battle_model=p2_bat,
        )
        obs, _ = ev.reset()
        action, _ = p1_sel.predict(obs, deterministic=True)
        _, _, _, _, info = ev.step(int(action))
        ev.close()
        if info.get("winner") == "p1":
            wins += 1
    return wins / n_games


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-model", type=str, required=True)
    parser.add_argument("--battle-model", type=str, required=True)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--steps-per-round", type=int, default=2000)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    teams = load_teams()
    p1_name = "screenshot-team"
    p1_paste = teams[p1_name]

    # Initialize opponent pool with the starting models
    pool_dir = MODELS_DIR / "selfplay_pool"
    pool_dir.mkdir(exist_ok=True)

    # Snapshot initial models as opponent v0
    shutil.copy(args.selection_model + ".zip", pool_dir / "sel_v0.zip")
    shutil.copy(args.battle_model + ".zip", pool_dir / "bat_v0.zip")

    print(f"Self-play training: {args.rounds} rounds, {args.steps_per_round} steps/round")
    print(f"Initial models: {args.selection_model}, {args.battle_model}")

    all_results = []
    start_time = time.time()
    best_heuristic_wr = 0.0

    sel_path = args.selection_model
    bat_path = args.battle_model

    for rnd in range(1, args.rounds + 1):
        print(f"\n{'='*60}")
        print(f"Round {rnd}/{args.rounds}", flush=True)

        # Pick random opponent from pool
        pool_versions = sorted(pool_dir.glob("sel_v*.zip"))
        n_versions = len(pool_versions)
        # Bias toward recent versions (50% latest, 50% random)
        import random
        if random.random() < 0.5 and n_versions > 1:
            opp_idx = random.randint(0, n_versions - 1)
        else:
            opp_idx = n_versions - 1  # latest
        opp_v = opp_idx

        p2_sel = MaskablePPO.load(str(pool_dir / f"sel_v{opp_v}"), device="cpu")
        p2_bat = MaskablePPO.load(str(pool_dir / f"bat_v{opp_v}"), device="cpu")
        print(f"  Opponent: v{opp_v} (of {n_versions} versions)", flush=True)

        # --- Train selection: mix of self-play and heuristic opponents ---
        # 50% self-play (mirror match vs past RL), 50% heuristic (diverse teams)
        # This prevents policy forgetting against heuristic patterns.
        print(f"  [A] Training selection ({args.steps_per_round} steps)...", flush=True)
        bat_frozen = MaskablePPO.load(bat_path, device="cpu")
        opp_pool_pastes = [v for k, v in teams.items() if k != p1_name]

        half = args.steps_per_round // 2

        # A1: Self-play (mirror)
        sel_env_sp = SelectionEnv(
            team_paste=p1_paste,
            opponent_paste=p1_paste,
            battle_model=bat_frozen,
            p2_selection_model=p2_sel,
            p2_battle_model=p2_bat,
        )
        sel_model = MaskablePPO.load(sel_path, env=sel_env_sp, device="cpu")
        sel_model.learning_rate = args.lr
        sel_model.learn(total_timesteps=half, reset_num_timesteps=False)
        sel_env_sp.close()

        # A2: vs heuristic (diverse opponents)
        sel_env_h = SelectionEnv(
            team_paste=p1_paste,
            opponent_pool=opp_pool_pastes,
            battle_model=bat_frozen,
        )
        sel_model.set_env(sel_env_h)
        sel_model.learn(total_timesteps=half, reset_num_timesteps=False)
        sel_model.save(str(MODELS_DIR / "sel_selfplay"))
        sel_path = str(MODELS_DIR / "sel_selfplay")
        sel_env_h.close()

        # --- Train battle against this opponent ---
        print(f"  [B] Training battle ({args.steps_per_round} steps)...", flush=True)
        from pokechamp.fast_env import FastBattleEnv
        sel_frozen = MaskablePPO.load(sel_path, device="cpu")
        # For battle training, we need FastBattleEnv with p2 as RL
        # But FastBattleEnv only supports heuristic p2 currently.
        # Workaround: use SelectionEnv with battle_model=None (heuristic p1 battle)
        # and train battle via the selection env wrapper.
        # Actually, we need a different approach for battle training in self-play.
        # For now, train battle against heuristic (same as Gen11) but with RL selection.
        opp_pool = [v for k, v in teams.items() if k != p1_name]
        bat_env = FastBattleEnv(
            team_paste=p1_paste,
            opponent_pool=opp_pool,
            selection_model=sel_frozen,
        )
        bat_model = MaskablePPO.load(bat_path, env=bat_env, device="cpu")
        bat_model.learning_rate = args.lr
        bat_model.learn(total_timesteps=args.steps_per_round, reset_num_timesteps=False)
        bat_model.save(str(MODELS_DIR / "bat_selfplay"))
        bat_path = str(MODELS_DIR / "bat_selfplay")
        bat_env.close()

        # --- Evaluate ---
        print("  Evaluating...", flush=True)
        sel_eval = MaskablePPO.load(sel_path, device="cpu")
        bat_eval = MaskablePPO.load(bat_path, device="cpu")

        # vs heuristic (regression check)
        h_results = evaluate_vs_heuristic(sel_eval, bat_eval, p1_paste, teams, n_per_opp=10)
        h_wins = sum(r["wins"] for r in h_results.values())
        h_games = sum(r["games"] for r in h_results.values())
        h_wr = h_wins / h_games

        # vs previous self
        self_wr = evaluate_vs_self(sel_eval, bat_eval, p2_sel, p2_bat, p1_paste, EVAL_GAMES)

        elapsed = (time.time() - start_time) / 60
        print(f"  Round {rnd}: vs heuristic {h_wr:.0%}, vs self(v{opp_v}) {self_wr:.0%} ({elapsed:.1f}min)", flush=True)
        for opp, r in sorted(h_results.items()):
            print(f"    vs {opp}: {r['wins']}/{r['games']}", flush=True)

        round_result = {
            "round": rnd,
            "elapsed_min": round(elapsed, 1),
            "vs_heuristic": round(h_wr, 3),
            "vs_self": round(self_wr, 3),
            "opponent_version": opp_v,
            "per_opponent": h_results,
        }
        all_results.append(round_result)
        RESULTS_PATH.write_text(json.dumps(all_results, indent=2))

        # Snapshot into pool every round
        v = rnd
        shutil.copy(sel_path + ".zip", pool_dir / f"sel_v{v}.zip")
        shutil.copy(bat_path + ".zip", pool_dir / f"bat_v{v}.zip")
        print(f"  Snapshot saved as v{v}", flush=True)

        if h_wr > best_heuristic_wr:
            best_heuristic_wr = h_wr
            sel_eval.save(str(MODELS_DIR / "sel_selfplay_best"))
            bat_eval.save(str(MODELS_DIR / "bat_selfplay_best"))
            print(f"  ★ New best vs heuristic: {best_heuristic_wr:.0%}", flush=True)

    print(f"\n{'='*60}")
    print(f"Self-play complete: {(time.time()-start_time)/60:.1f}min")
    print(f"Best vs heuristic: {best_heuristic_wr:.0%}")
    print(f"Pool size: {len(list(pool_dir.glob('sel_v*.zip')))} versions")


if __name__ == "__main__":
    main()
