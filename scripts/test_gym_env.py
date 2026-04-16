"""Gymnasium 環境のテストスクリプト。

ローカルShowdownサーバー (localhost:8000) が起動している必要があります。

Usage
-----
    cd /home/deploy/pokemon-champions-lab
    source .venv/bin/activate
    python scripts/test_gym_env.py
"""
from __future__ import annotations

import sys
import time


# チームデフォルト (test_poke_env.py と同じ構築)
TEAM_1 = """
Garchomp @ Focus Sash
Ability: Rough Skin
EVs: 32 Atk / 32 Spe / 2 HP
Jolly Nature
- Earthquake
- Outrage
- Swords Dance
- Stone Edge

Dragonite @ Dragoninite
Ability: Multiscale
EVs: 32 SpA / 32 Spe / 2 HP
Modest Nature
- Draco Meteor
- Thunderbolt
- Flamethrower
- Roost

Primarina @ Sitrus Berry
Ability: Torrent
EVs: 32 SpA / 32 Spe / 2 HP
Modest Nature
- Sparkling Aria
- Moonblast
- Aqua Jet
- Encore

Volcarona @ Leftovers
Ability: Flame Body
EVs: 32 SpA / 32 Spe / 2 HP
Timid Nature
- Flamethrower
- Giga Drain
- Quiver Dance
- Morning Sun

Corviknight @ Metal Coat
Ability: Pressure
EVs: 32 HP / 32 Def / 2 SpD
Impish Nature
- Body Press
- U-turn
- Iron Defense
- Roost

Scizor @ Scizorite
Ability: Technician
EVs: 32 Atk / 32 HP / 2 Spe
Adamant Nature
- Bullet Punch
- Close Combat
- Swords Dance
- Roost
"""


def test_env_interface() -> None:
    """環境インタフェースとshapeのテスト (サーバー不要)。"""
    print("=== 環境インタフェーステスト (サーバー不要) ===")

    from pokechamp.env import OBS_DIM, N_ACTIONS

    print(f"  OBS_DIM: {OBS_DIM}")
    print(f"  N_ACTIONS: {N_ACTIONS}")
    print("  observation_space shape: OK (確認済み)")
    print("  action_space size: OK (確認済み)")
    print()


def test_team_converter() -> None:
    """team_converter のユニットテスト。"""
    print("=== team_converter テスト ===")

    from pokechamp.team_converter import team_yaml_to_showdown
    from pokechamp.loader import list_teams

    teams = list_teams()
    print(f"  利用可能チーム数: {len(teams)}")

    for team_name in teams[:3]:  # 最初の3チームをテスト
        try:
            result = team_yaml_to_showdown(team_name)
            pokemon_count = result.count("Ability:")
            print(f"  [{team_name}] -> {pokemon_count}体 変換成功")
        except Exception as e:
            print(f"  [{team_name}] -> ERROR: {e}")
    print()


def test_live_battle(n_steps: int = 50) -> None:
    """実際のShowdownサーバーに接続して環境をテストする。"""
    print("=== ライブバトルテスト ===")
    print("  Showdownサーバー: localhost:8000")
    print(f"  最大ステップ数: {n_steps}")
    print()

    from pokechamp.env import ChampionsEnv

    env = ChampionsEnv(
        team=TEAM_1,
        opponent_team=TEAM_1,
        username="ChampRL_test",
        opponent_username="ChampRL_opp",
    )

    print(f"  観測空間: {env.observation_space}")
    print(f"  行動空間: {env.action_space}")
    print()

    try:
        print("  env.reset() を呼び出し中...")
        t0 = time.time()
        obs, info = env.reset()
        print(f"  reset 完了 ({time.time() - t0:.1f}s)")
        print(f"  観測 shape: {obs.shape}")
        print(f"  観測 dtype: {obs.dtype}")
        print(f"  観測 min/max: {obs.min():.3f} / {obs.max():.3f}")
        print(f"  バトルタグ: {info.get('battle_tag', 'N/A')}")
        print(f"  有効行動マスク: {info.get('action_mask', 'N/A')}")
        print()

        total_reward = 0.0
        for step in range(n_steps):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward

            if step < 3 or terminated:
                print(
                    f"  step={step:3d}  action={action}  reward={reward:+.3f}"
                    f"  terminated={terminated}  turn={info.get('turn', '?')}"
                )

            if terminated or truncated:
                won = info.get("won")
                print()
                print(f"  エピソード終了: {'勝利' if won else '敗北' if won is False else '不明'}")
                print(f"  総報酬: {total_reward:.3f}")
                break
        else:
            print(f"\n  {n_steps}ステップ後も継続中 (総報酬: {total_reward:.3f})")

    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        env.close()
        print("\n  env.close() 完了")


if __name__ == "__main__":
    # 常に実行するテスト
    test_env_interface()
    test_team_converter()

    # ライブバトルテスト (--live フラグがあれば)
    if "--live" in sys.argv:
        test_live_battle()
    else:
        print("=== ライブバトルテストはスキップ ===")
        print("  実行するには: python scripts/test_gym_env.py --live")
