#!/usr/bin/env python3
"""Train a PPO agent to play Pokemon Champions battles.

The agent (p1) learns to beat the heuristic AI (p2) using
FastBattleEnv (~1s/battle).

Usage:
    python scripts/train_ppo.py --timesteps 10000 --eval-freq 2000
    python scripts/train_ppo.py --timesteps 50000  # longer training
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from pokechamp.fast_env import FastBattleEnv

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


class ActionMaskCallback(BaseCallback):
    """Mask invalid actions during PPO training."""

    def _on_step(self) -> bool:
        return True


class EvalCallback(BaseCallback):
    """Periodically evaluate agent win rate vs heuristic AI."""

    def __init__(self, eval_env_fn, eval_freq: int = 2000, n_eval: int = 10, verbose: int = 1):
        super().__init__(verbose)
        self.eval_env_fn = eval_env_fn
        self.eval_freq = eval_freq
        self.n_eval = n_eval
        self.best_win_rate = 0.0

    def _on_step(self) -> bool:
        if self.n_calls % self.eval_freq == 0:
            win_rate = evaluate_agent(self.model, self.eval_env_fn, n_games=self.n_eval)
            if self.verbose:
                print(f"  Step {self.n_calls}: win_rate={win_rate:.0%} ({self.n_eval} games)")
            if win_rate > self.best_win_rate:
                self.best_win_rate = win_rate
        return True


def make_env(team_name: str = "screenshot-team", opp_name: str = "mega-gengar-team"):
    """Create a FastBattleEnv with specified teams."""
    teams = {t.parent.name: t.read_text() for t in TEAMS_DIR.glob("*/team.txt") if not t.parent.name.startswith("test-")}
    team_paste = teams.get(team_name, list(teams.values())[0])
    opp_paste = teams.get(opp_name, list(teams.values())[1])
    return FastBattleEnv(team_paste=team_paste, opponent_paste=opp_paste)


def make_random_matchup_env():
    """Create env with random team matchup each reset."""
    teams = {t.parent.name: t.read_text() for t in TEAMS_DIR.glob("*/team.txt") if not t.parent.name.startswith("test-")}
    team_list = list(teams.values())

    class RandomMatchupEnv(FastBattleEnv):
        def reset(self, **kwargs):
            # Randomize teams each episode
            idx = np.random.choice(len(team_list), size=2, replace=False)
            self.team_paste = team_list[idx[0]]
            self.opponent_paste = team_list[idx[1]]
            return super().reset(**kwargs)

    return RandomMatchupEnv(team_paste=team_list[0], opponent_paste=team_list[1])


def evaluate_agent(model, env_fn, n_games: int = 10) -> float:
    """Evaluate agent win rate."""
    wins = 0
    for _ in range(n_games):
        env = env_fn()
        obs, info = env.reset()
        done = False
        while not done:
            mask = env.get_action_mask()
            # Use model prediction with action masking
            action, _ = model.predict(obs, deterministic=True)
            action = int(action)
            # Enforce mask
            if mask[action] == 0:
                valid = np.where(mask > 0)[0]
                action = int(np.random.choice(valid)) if len(valid) > 0 else 0
            obs, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
        env.close()
        if info.get("winner") == "p1":
            wins += 1
    return wins / n_games


def main():
    parser = argparse.ArgumentParser(description="Train PPO Pokemon agent")
    parser.add_argument("--timesteps", type=int, default=10000, help="Total training timesteps")
    parser.add_argument("--eval-freq", type=int, default=2000, help="Evaluate every N steps")
    parser.add_argument("--n-eval", type=int, default=10, help="Games per evaluation")
    parser.add_argument("--random-matchups", action="store_true", help="Randomize team matchups")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("Creating environment...")
    if args.random_matchups:
        env = DummyVecEnv([make_random_matchup_env])
    else:
        env = DummyVecEnv([lambda: make_env()])

    print("Creating PPO model...")
    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        n_steps=128,
        batch_size=64,
        n_epochs=4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        verbose=1,
        tensorboard_log=str(MODELS_DIR / "tb_logs"),
    )

    print(f"Training for {args.timesteps} timesteps...")
    eval_cb = EvalCallback(
        eval_env_fn=make_env if not args.random_matchups else make_random_matchup_env,
        eval_freq=args.eval_freq,
        n_eval=args.n_eval,
    )

    start = time.time()
    model.learn(total_timesteps=args.timesteps, callback=eval_cb)
    elapsed = time.time() - start

    print(f"\nTraining complete: {args.timesteps} steps in {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Final evaluation
    print("\nFinal evaluation (20 games)...")
    final_wr = evaluate_agent(model, make_env, n_games=20)
    print(f"Win rate vs heuristic AI: {final_wr:.0%}")

    # Save model
    model_path = MODELS_DIR / "ppo_champions"
    model.save(str(model_path))
    print(f"Model saved to {model_path}")


if __name__ == "__main__":
    main()
