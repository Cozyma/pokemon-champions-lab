#!/usr/bin/env python3
"""Train team selection agent with MaskablePPO.

Each episode is 1 step: observe team preview → pick 3 → battle plays out → reward.
This is effectively a contextual bandit.

Usage:
    nohup python scripts/train_selection.py > models/selection_training.log 2>&1 &

Options:
    --steps N       Total training steps (default: 20000)
    --lr-start F    Initial learning rate (default: 3e-4)
    --lr-end F      Final learning rate (default: 3e-5)
    --resume PATH   Resume from checkpoint
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)

from sb3_contrib import MaskablePPO  # noqa: E402
from pokechamp.selection_env import SelectionEnv  # noqa: E402

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
RESULTS_PATH = MODELS_DIR / "selection_results.json"

CHECKPOINT_EVERY = 1000  # 1000 episodes (=steps, since 1-step episodes)
EVAL_GAMES_PER_OPP = 10
EARLY_STOP_PATIENCE = 10  # more patience for bandit (high variance)


def load_teams() -> dict[str, str]:
    return {t.parent.name: t.read_text()
            for t in TEAMS_DIR.glob("*/team.txt")
            if not t.parent.name.startswith("test-")}


def evaluate_selection(model, p1_paste: str, teams: dict[str, str], n_per_opp: int = 10) -> dict:
    """Evaluate selection agent against each opponent team."""
    results = {}
    for opp_name, opp_paste in sorted(teams.items()):
        wins = 0
        for _ in range(n_per_opp):
            ev = SelectionEnv(team_paste=p1_paste, opponent_paste=opp_paste)
            obs, _ = ev.reset()
            mask = ev.action_masks()
            action, _ = model.predict(obs, deterministic=True, action_masks=mask)
            obs, reward, terminated, truncated, info = ev.step(int(action))
            ev.close()
            if info.get("winner") == "p1":
                wins += 1
        results[opp_name] = {"wins": wins, "games": n_per_opp}
    return results


def evaluate_heuristic(p1_paste: str, teams: dict[str, str], n_per_opp: int = 10) -> dict:
    """Evaluate heuristic selection (action=None, env uses default)."""
    from pokechamp.fast_battle import run_battle
    results = {}
    for opp_name, opp_paste in sorted(teams.items()):
        wins = 0
        for _ in range(n_per_opp):
            r = run_battle(p1_paste, opp_paste)
            if r.get("winner") == "p1":
                wins += 1
        results[opp_name] = {"wins": wins, "games": n_per_opp}
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=str, default=None)
    parser.add_argument("--steps", type=int, default=20000)
    parser.add_argument("--lr-start", type=float, default=3e-4)
    parser.add_argument("--lr-end", type=float, default=3e-5)
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    teams = load_teams()
    team_names = sorted(teams.keys())
    print(f"Teams: {team_names}")

    p1_name = "screenshot-team"
    p1_paste = teams[p1_name]
    opp_pool = [v for k, v in teams.items() if k != p1_name]
    print(f"p1: {p1_name}, opponent pool: {len(opp_pool)} teams")

    env = SelectionEnv(team_paste=p1_paste, opponent_pool=opp_pool)

    lr_start = args.lr_start
    lr_end = args.lr_end

    def lr_schedule(progress_remaining: float) -> float:
        return lr_end + (lr_start - lr_end) * progress_remaining

    print(f"LR schedule: {lr_start} -> {lr_end}")

    if args.resume:
        print(f"Resuming from {args.resume}")
        model = MaskablePPO.load(args.resume, env=env, device="cpu")
        model.learning_rate = lr_schedule
    else:
        print("Starting fresh MaskablePPO for selection")
        model = MaskablePPO(
            "MlpPolicy", env,
            learning_rate=lr_schedule,
            n_steps=512,      # Many episodes per update (1-step bandit)
            batch_size=128,
            n_epochs=10,       # More epochs since episodes are cheap
            gamma=1.0,         # No discounting (immediate reward)
            ent_coef=0.05,     # Explore across 20 actions
            clip_range=0.2,
            device="cpu",
            verbose=0,
        )

    # Baseline: heuristic selection
    print("\nEvaluating heuristic baseline...", flush=True)
    heuristic_results = evaluate_heuristic(p1_paste, teams, n_per_opp=EVAL_GAMES_PER_OPP)
    h_wins = sum(r["wins"] for r in heuristic_results.values())
    h_games = sum(r["games"] for r in heuristic_results.values())
    print(f"Heuristic baseline: {h_wins}/{h_games} = {h_wins/h_games:.0%}", flush=True)
    for opp, r in sorted(heuristic_results.items()):
        print(f"  vs {opp}: {r['wins']}/{r['games']}", flush=True)

    all_results = []
    start_time = time.time()
    best_win_rate = 0.0
    no_improve_count = 0

    total_steps = args.steps
    n_checkpoints = total_steps // CHECKPOINT_EVERY

    for checkpoint in range(1, n_checkpoints + 1):
        step_target = checkpoint * CHECKPOINT_EVERY
        print(f"\n{'='*60}", flush=True)
        print(f"Training to {step_target} steps...", flush=True)

        model.learn(total_timesteps=CHECKPOINT_EVERY, reset_num_timesteps=False)
        elapsed = time.time() - start_time

        # Save checkpoint
        model.save(str(MODELS_DIR / f"selection_{step_target}"))

        # Evaluate
        print(f"Evaluating at {step_target} steps ({elapsed/60:.1f}min elapsed)...", flush=True)
        eval_results = evaluate_selection(model, p1_paste, teams, n_per_opp=EVAL_GAMES_PER_OPP)

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
        RESULTS_PATH.write_text(json.dumps(all_results, indent=2))

        if overall_wr > best_win_rate:
            best_win_rate = overall_wr
            no_improve_count = 0
            model.save(str(MODELS_DIR / "selection_best"))
            print(f"  ★ New best: {best_win_rate:.0%}", flush=True)
        else:
            no_improve_count += 1
            print(f"  No improvement ({no_improve_count}/{EARLY_STOP_PATIENCE})", flush=True)
            if no_improve_count >= EARLY_STOP_PATIENCE:
                print("\n⏹ Early stopping", flush=True)
                break

    env.close()
    elapsed = time.time() - start_time

    print(f"\n{'='*60}", flush=True)
    print(f"Training complete: {elapsed/60:.1f}min", flush=True)
    print("\nProgression:", flush=True)
    for r in all_results:
        marker = "★" if r["overall_win_rate"] == best_win_rate else " "
        print(f"  {marker} {r['steps']} steps: {r['overall_win_rate']:.0%} ({r['elapsed_min']}min)", flush=True)
    print(f"\nHeuristic baseline: {h_wins/h_games:.0%}", flush=True)
    print(f"Best selection RL: {best_win_rate:.0%}", flush=True)


if __name__ == "__main__":
    main()
