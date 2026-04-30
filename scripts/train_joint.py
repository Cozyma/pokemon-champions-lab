#!/usr/bin/env python3
"""Joint training: alternate between selection and battle agents.

Phase 3 of the RL roadmap. Alternates:
  1. Train selection model (battle model frozen)
  2. Train battle model (selection model frozen)

Usage:
    python scripts/train_joint.py \
        --selection-model models/selection_best \
        --battle-model models/ppo_masked_best \
        --rounds 5 --steps-per-round 2000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from sb3_contrib import MaskablePPO  # noqa: E402
from pokechamp.fast_env import FastBattleEnv  # noqa: E402
from pokechamp.selection_env import SelectionEnv  # noqa: E402

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RESULTS_PATH = MODELS_DIR / "joint_results.json"

EVAL_GAMES_PER_OPP = 10


def load_teams() -> dict[str, str]:
    return {t.parent.name: t.read_text()
            for t in TEAMS_DIR.glob("*/team.txt")
            if not t.parent.name.startswith("test-")}


def evaluate_joint(
    selection_model, battle_model,
    p1_paste: str, teams: dict[str, str],
    n_per_opp: int = 10,
) -> dict:
    """Evaluate selection + battle agents together."""
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
            mask = ev.action_masks()
            action, _ = selection_model.predict(obs, deterministic=True, action_masks=mask)
            _, _, _, _, info = ev.step(int(action))
            ev.close()
            if info.get("winner") == "p1":
                wins += 1
        results[opp_name] = {"wins": wins, "games": n_per_opp}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-model", type=str, default="models/selection_best")
    parser.add_argument("--battle-model", type=str, default="models/ppo_masked_best")
    parser.add_argument("--rounds", type=int, default=5, help="Alternation rounds")
    parser.add_argument("--steps-per-round", type=int, default=2000)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    teams = load_teams()

    p1_name = "screenshot-team"
    p1_paste = teams[p1_name]
    opp_pool = [v for k, v in teams.items() if k != p1_name]

    print(f"Loading selection model: {args.selection_model}")
    print(f"Loading battle model: {args.battle_model}")

    all_results = []
    start_time = time.time()
    best_win_rate = 0.0

    for rnd in range(1, args.rounds + 1):
        print(f"\n{'='*60}")
        print(f"Round {rnd}/{args.rounds}")

        # --- Step A: Train selection (battle frozen) ---
        print(f"\n  [A] Training selection ({args.steps_per_round} steps)...", flush=True)
        battle_model = MaskablePPO.load(args.battle_model, device="cpu")
        sel_env = SelectionEnv(
            team_paste=p1_paste,
            opponent_pool=opp_pool,
            battle_model=battle_model,
        )
        sel_model = MaskablePPO.load(args.selection_model, env=sel_env, device="cpu")
        sel_model.learning_rate = args.lr
        sel_model.learn(total_timesteps=args.steps_per_round, reset_num_timesteps=False)
        sel_model.save(str(MODELS_DIR / "selection_joint"))
        args.selection_model = str(MODELS_DIR / "selection_joint")
        sel_env.close()

        # --- Step B: Train battle (selection frozen) ---
        print(f"  [B] Training battle ({args.steps_per_round} steps)...", flush=True)
        sel_model_frozen = MaskablePPO.load(args.selection_model, device="cpu")
        bat_env = FastBattleEnv(
            team_paste=p1_paste,
            opponent_pool=opp_pool,
            selection_model=sel_model_frozen,
        )
        bat_model = MaskablePPO.load(args.battle_model, env=bat_env, device="cpu")
        bat_model.learning_rate = args.lr
        bat_model.learn(total_timesteps=args.steps_per_round, reset_num_timesteps=False)
        bat_model.save(str(MODELS_DIR / "battle_joint"))
        args.battle_model = str(MODELS_DIR / "battle_joint")
        bat_env.close()

        # --- Evaluate joint performance ---
        print("  Evaluating...", flush=True)
        sel_eval = MaskablePPO.load(args.selection_model, device="cpu")
        bat_eval = MaskablePPO.load(args.battle_model, device="cpu")
        eval_results = evaluate_joint(sel_eval, bat_eval, p1_paste, teams, EVAL_GAMES_PER_OPP)

        total_wins = sum(r["wins"] for r in eval_results.values())
        total_games = sum(r["games"] for r in eval_results.values())
        overall_wr = total_wins / total_games if total_games else 0

        elapsed = time.time() - start_time
        print(f"  Round {rnd}: {total_wins}/{total_games} = {overall_wr:.0%} ({elapsed/60:.1f}min)", flush=True)
        for opp, r in sorted(eval_results.items()):
            print(f"    vs {opp}: {r['wins']}/{r['games']}", flush=True)

        round_result = {
            "round": rnd,
            "elapsed_min": round(elapsed / 60, 1),
            "overall_win_rate": round(overall_wr, 3),
            "per_opponent": eval_results,
        }
        all_results.append(round_result)
        RESULTS_PATH.write_text(json.dumps(all_results, indent=2))

        if overall_wr > best_win_rate:
            best_win_rate = overall_wr
            sel_eval.save(str(MODELS_DIR / "selection_joint_best"))
            bat_eval.save(str(MODELS_DIR / "battle_joint_best"))
            print(f"  ★ New best: {best_win_rate:.0%}", flush=True)

    print(f"\n{'='*60}")
    print(f"Joint training complete: {(time.time()-start_time)/60:.1f}min")
    print(f"Best joint win rate: {best_win_rate:.0%}")


if __name__ == "__main__":
    main()
