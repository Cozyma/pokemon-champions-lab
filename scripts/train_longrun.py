#!/usr/bin/env python3
"""Long-running PPO training with diverse opponents and checkpointing.

Saves checkpoints every 1000 steps, evaluates each, logs everything.
Designed to run unattended.

Usage:
    nohup python scripts/train_longrun.py > models/training.log 2>&1 &
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

from stable_baselines3 import PPO
from pokechamp.fast_env import FastBattleEnv

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RESULTS_PATH = MODELS_DIR / "longrun_results.json"

TOTAL_STEPS = 80000
CHECKPOINT_EVERY = 5000
EVAL_GAMES_PER_OPP = 5


def load_teams() -> dict[str, str]:
    return {t.parent.name: t.read_text()
            for t in TEAMS_DIR.glob("*/team.txt")
            if not t.parent.name.startswith("test-")}


def evaluate(model, p1_paste: str, teams: dict[str, str], n_per_opp: int = 3) -> dict:
    """Evaluate against each opponent team. Returns {opp_name: wins/n}."""
    results = {}
    for opp_name, opp_paste in sorted(teams.items()):
        wins = 0
        for _ in range(n_per_opp):
            ev = FastBattleEnv(team_paste=p1_paste, opponent_paste=opp_paste)
            obs, _ = ev.reset()
            done = False
            while not done:
                mask = ev.get_action_mask()
                action, _ = model.predict(obs, deterministic=True)
                action = int(action)
                if mask[action] == 0:
                    valid = np.where(mask > 0)[0]
                    action = int(np.random.choice(valid)) if len(valid) > 0 else 0
                obs, reward, terminated, truncated, info = ev.step(action)
                done = terminated or truncated
            ev.close()
            if info.get("winner") == "p1":
                wins += 1
        results[opp_name] = {"wins": wins, "games": n_per_opp}
    return results


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    teams = load_teams()
    team_names = sorted(teams.keys())
    print(f"Teams: {team_names}")

    p1_name = "screenshot-team"
    p1_paste = teams[p1_name]
    opp_pool = [v for k, v in teams.items() if k != p1_name]
    print(f"p1: {p1_name}, opponent pool: {len(opp_pool)} teams")

    env = FastBattleEnv(team_paste=p1_paste, opponent_pool=opp_pool)

    model = PPO(
        "MlpPolicy", env,
        learning_rate=1e-3,
        n_steps=32,
        batch_size=16,
        n_epochs=4,
        gamma=0.99,
        ent_coef=0.1,       # high entropy to prevent collapse
        clip_range=0.2,
        device="cpu",
        verbose=0,           # quiet during training
    )

    all_results = []
    start_time = time.time()
    trained_steps = 0

    for checkpoint in range(1, TOTAL_STEPS // CHECKPOINT_EVERY + 1):
        step_target = checkpoint * CHECKPOINT_EVERY
        print(f"\n{'='*60}", flush=True)
        print(f"Training to {step_target} steps...", flush=True)

        model.learn(total_timesteps=CHECKPOINT_EVERY, reset_num_timesteps=False)
        trained_steps = step_target
        elapsed = time.time() - start_time

        # Save checkpoint
        ckpt_path = MODELS_DIR / f"ppo_diverse_{step_target}"
        model.save(str(ckpt_path))

        # Evaluate
        print(f"Evaluating at {step_target} steps ({elapsed/60:.1f}min elapsed)...", flush=True)
        eval_results = evaluate(model, p1_paste, teams, n_per_opp=EVAL_GAMES_PER_OPP)

        total_wins = sum(r["wins"] for r in eval_results.values())
        total_games = sum(r["games"] for r in eval_results.values())
        overall_wr = total_wins / total_games if total_games else 0

        print(f"  Overall: {total_wins}/{total_games} = {overall_wr:.0%}", flush=True)
        for opp, r in sorted(eval_results.items()):
            print(f"    vs {opp}: {r['wins']}/{r['games']}", flush=True)

        checkpoint_result = {
            "steps": step_target,
            "elapsed_min": round(elapsed / 60, 1),
            "overall_win_rate": round(overall_wr, 3),
            "total_wins": total_wins,
            "total_games": total_games,
            "per_opponent": eval_results,
        }
        all_results.append(checkpoint_result)

        # Save results incrementally
        RESULTS_PATH.write_text(json.dumps(all_results, indent=2))

    env.close()

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n{'='*60}", flush=True)
    print(f"Training complete: {trained_steps} steps in {elapsed/60:.1f}min", flush=True)
    print(f"\nProgression:", flush=True)
    for r in all_results:
        print(f"  {r['steps']} steps: {r['overall_win_rate']:.0%} ({r['elapsed_min']}min)", flush=True)

    best = max(all_results, key=lambda r: r["overall_win_rate"])
    print(f"\nBest: {best['steps']} steps at {best['overall_win_rate']:.0%}", flush=True)


if __name__ == "__main__":
    main()
