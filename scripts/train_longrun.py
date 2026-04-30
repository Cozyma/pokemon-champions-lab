#!/usr/bin/env python3
"""Long-running MaskablePPO training with diverse opponents, checkpointing, and early stopping.

Uses sb3-contrib MaskablePPO for proper action masking.
Saves checkpoints, evaluates each, stops if win rate declines.

Usage:
    nohup python scripts/train_longrun.py > models/training.log 2>&1 &

Options:
    --resume PATH   Resume from a saved model checkpoint
    --steps N       Total training steps (default: 80000)
    --lr-start F    Initial learning rate (default: 1e-3)
    --lr-end F      Final learning rate (default: 1e-4)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(line_buffering=True)

from sb3_contrib import MaskablePPO
from pokechamp.fast_env import FastBattleEnv

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RESULTS_PATH = MODELS_DIR / "longrun_results.json"

CHECKPOINT_EVERY = 2000
EVAL_GAMES_PER_OPP = 10
EARLY_STOP_PATIENCE = 5  # stop after N checkpoints without improvement


def load_teams() -> dict[str, str]:
    return {t.parent.name: t.read_text()
            for t in TEAMS_DIR.glob("*/team.txt")
            if not t.parent.name.startswith("test-")}


def evaluate(model, p1_paste: str, teams: dict[str, str], n_per_opp: int = 5, selection_model=None) -> dict:
    """Evaluate against each opponent team, collecting battle metrics."""
    from pokechamp.battle_metrics import analyze_battle
    results = {}
    all_metrics = []
    for opp_name, opp_paste in sorted(teams.items()):
        wins = 0
        for _ in range(n_per_opp):
            ev = FastBattleEnv(team_paste=p1_paste, opponent_paste=opp_paste, selection_model=selection_model)
            obs, _ = ev.reset()
            done = False
            while not done:
                mask = ev.action_masks()
                action, _ = model.predict(obs, deterministic=True, action_masks=mask)
                obs, reward, terminated, truncated, info = ev.step(int(action))
                done = terminated or truncated
            # Collect battle metrics from the env's log
            if hasattr(ev, '_log_lines') and ev._log_lines:
                m = analyze_battle(ev._log_lines, "p1")
                all_metrics.append(m)
            ev.close()
            if info.get("winner") == "p1":
                wins += 1
        results[opp_name] = {"wins": wins, "games": n_per_opp}
    results["_metrics"] = all_metrics
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=str, default=None, help="Resume from checkpoint path")
    parser.add_argument("--steps", type=int, default=80000, help="Total training steps")
    parser.add_argument("--lr-start", type=float, default=1e-3, help="Initial learning rate")
    parser.add_argument("--lr-end", type=float, default=1e-4, help="Final learning rate")
    parser.add_argument("--selection-model", type=str, default=None, help="Selection RL model for p1 team preview")
    parser.add_argument("--n-steps", type=int, default=32, help="Steps per PPO update")
    parser.add_argument("--batch-size", type=int, default=16, help="Minibatch size")
    parser.add_argument("--ent-coef", type=float, default=0.1, help="Entropy coefficient")
    parser.add_argument("--checkpoint-every", type=int, default=None, help="Checkpoint interval (default: CHECKPOINT_EVERY)")
    parser.add_argument("--eval-games", type=int, default=None, help="Games per opponent for eval")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    teams = load_teams()
    team_names = sorted(teams.keys())
    print(f"Teams: {team_names}")

    p1_name = "screenshot-team"
    p1_paste = teams[p1_name]
    opp_pool = [v for k, v in teams.items() if k != p1_name]
    print(f"p1: {p1_name}, opponent pool: {len(opp_pool)} teams")

    selection_model = None
    if args.selection_model:
        from sb3_contrib import MaskablePPO as _M
        selection_model = _M.load(args.selection_model, device="cpu")
        print(f"Using selection model: {args.selection_model}")

    env = FastBattleEnv(team_paste=p1_paste, opponent_pool=opp_pool, selection_model=selection_model)

    # Linear lr decay: lr_start → lr_end over training
    lr_start = args.lr_start
    lr_end = args.lr_end

    def lr_schedule(progress_remaining: float) -> float:
        """Linear decay from lr_start to lr_end. progress_remaining: 1.0 → 0.0."""
        return lr_end + (lr_start - lr_end) * progress_remaining

    print(f"LR schedule: {lr_start} → {lr_end} (linear decay)")

    if args.resume:
        print(f"Resuming from {args.resume}")
        model = MaskablePPO.load(args.resume, env=env, device="cpu")
        model.learning_rate = lr_schedule
    else:
        print("Starting fresh MaskablePPO")
        model = MaskablePPO(
            "MlpPolicy", env,
            learning_rate=lr_schedule,
            n_steps=args.n_steps,
            batch_size=args.batch_size,
            n_epochs=4,
            gamma=0.99,
            ent_coef=args.ent_coef,
            clip_range=0.2,
            device="cpu",
            verbose=0,
        )

    all_results = []
    start_time = time.time()
    best_win_rate = 0.0
    no_improve_count = 0

    checkpoint_interval = args.checkpoint_every or CHECKPOINT_EVERY
    eval_n = args.eval_games or EVAL_GAMES_PER_OPP
    total_steps = args.steps
    n_checkpoints = total_steps // checkpoint_interval

    for checkpoint in range(1, n_checkpoints + 1):
        step_target = checkpoint * checkpoint_interval
        print(f"\n{'='*60}", flush=True)
        print(f"Training to {step_target} steps...", flush=True)

        model.learn(total_timesteps=checkpoint_interval, reset_num_timesteps=False)
        elapsed = time.time() - start_time

        # Save checkpoint
        ckpt_path = MODELS_DIR / f"ppo_masked_{step_target}"
        model.save(str(ckpt_path))

        # Evaluate
        print(f"Evaluating at {step_target} steps ({elapsed/60:.1f}min elapsed)...", flush=True)
        eval_results = evaluate(model, p1_paste, teams, n_per_opp=eval_n, selection_model=selection_model)

        # Extract metrics before computing totals
        battle_metrics = eval_results.pop("_metrics", [])

        total_wins = sum(r["wins"] for r in eval_results.values())
        total_games = sum(r["games"] for r in eval_results.values())
        overall_wr = total_wins / total_games if total_games else 0

        print(f"  Overall: {total_wins}/{total_games} = {overall_wr:.0%}", flush=True)
        for opp, r in sorted(eval_results.items()):
            print(f"    vs {opp}: {r['wins']}/{r['games']}", flush=True)

        # Print battle quality metrics
        if battle_metrics:
            from pokechamp.battle_metrics import summarize_metrics, format_metrics
            summary = summarize_metrics(battle_metrics)
            print("  --- Quality Metrics ---", flush=True)
            for line in format_metrics(summary).split("\n"):
                print(f"  {line}", flush=True)

        checkpoint_result = {
            "steps": step_target,
            "elapsed_min": round(elapsed / 60, 1),
            "overall_win_rate": round(overall_wr, 3),
            "total_wins": total_wins,
            "total_games": total_games,
            "per_opponent": eval_results,
        }
        if battle_metrics:
            from pokechamp.battle_metrics import summarize_metrics as _sm
            checkpoint_result["quality"] = _sm(battle_metrics)
        all_results.append(checkpoint_result)
        RESULTS_PATH.write_text(json.dumps(all_results, indent=2))

        # Early stopping check
        if overall_wr > best_win_rate:
            best_win_rate = overall_wr
            no_improve_count = 0
            # Save best model separately
            model.save(str(MODELS_DIR / "ppo_masked_best"))
            print(f"  ★ New best: {best_win_rate:.0%}", flush=True)
        else:
            no_improve_count += 1
            print(f"  No improvement ({no_improve_count}/{EARLY_STOP_PATIENCE})", flush=True)
            if no_improve_count >= EARLY_STOP_PATIENCE:
                print(f"\n��� Early stopping: no improvement for {EARLY_STOP_PATIENCE} checkpoints", flush=True)
                break

    env.close()
    elapsed = time.time() - start_time

    print(f"\n{'='*60}", flush=True)
    print(f"Training complete: {elapsed/60:.1f}min", flush=True)
    print(f"\nProgression:", flush=True)
    for r in all_results:
        marker = "★" if r["overall_win_rate"] == best_win_rate else " "
        print(f"  {marker} {r['steps']} steps: {r['overall_win_rate']:.0%} ({r['elapsed_min']}min)", flush=True)
    print(f"\nBest model: ppo_masked_best ({best_win_rate:.0%})", flush=True)


if __name__ == "__main__":
    main()
