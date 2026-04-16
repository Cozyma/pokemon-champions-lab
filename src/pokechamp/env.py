"""Gymnasium環境: Pokemon Champions RL Training

poke-env 0.15.0 には Gen9EnvSinglePlayer が存在しないため、
Player を継承しつつ gym.Env インタフェースを実装するカスタム環境。

設計概要
--------
- ChampionsEnv は gym.Env と Player を多重継承
- バトルループは POKE_LOOP (バックグラウンドスレッドの asyncio ループ) で動作
- choose_move() の呼び出しで threading.Event を使い step() と同期
- 観測ベクトル: 72次元の Box (正規化済み float32)
- 行動空間: Discrete(9) — 技4枚 + 交代5体

Usage
-----
    from pokechamp.env import ChampionsEnv

    env = ChampionsEnv(team=SHOWDOWN_TEAM_STR)
    obs, info = env.reset()
    done = False
    while not done:
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
    env.close()
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from poke_env import AccountConfiguration, ServerConfiguration
from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.battle import Battle
from poke_env.battle.move import Move as BattleMove
from poke_env.battle.pokemon import Pokemon as BattlePokemon
from poke_env.battle.pokemon_type import PokemonType
from poke_env.battle.status import Status
from poke_env.battle.weather import Weather
from poke_env.battle.field import Field
from poke_env.concurrency import POKE_LOOP
from poke_env.player import RandomPlayer
from poke_env.player.battle_order import BattleOrder
from poke_env.player.player import Player

# --------------------------------------------------------------------------- #
# 定数
# --------------------------------------------------------------------------- #

# 行動インデックス
# 0-3: 技0-3
# 4-8: 交代先ポケモン0-4 (ベンチの0〜4番目)
N_MOVES = 4
N_BENCH = 5
N_ACTIONS = N_MOVES + N_BENCH  # 9

# 観測ベクトルの次元
# 自分のアクティブポケモン: HP%, タイプ(2), ステータス, 積み段階(6) = 10
# 自分の技(4枚 × 5特徴): 技パワー, タイプ, 命中, PP%, カテゴリ = 20
# 相手のアクティブポケモン: HP%, タイプ(2), ステータス, 積み段階(6) = 10
# 自分のチーム残存(6体分 HP%) = 6
# 相手のチーム残存(6体分 HP%) = 6
# 天候 (1-hot: 8種) = 8
# フィールド (1-hot: 4地形) = 4
# has_mega / used_mega = 2
# フォースイッチフラグ = 1
# アクション有効マスク = 9 (情報提供用、obs に含める)
# -------- 合計 = 76
OBS_DIM = 76

_WEATHER_LIST = [
    Weather.RAINDANCE,
    Weather.SUNNYDAY,
    Weather.SANDSTORM,
    Weather.HAIL,
    Weather.SNOWSCAPE,
    Weather.DESOLATELAND,
    Weather.PRIMORDIALSEA,
    Weather.DELTASTREAM,
]

_TERRAIN_LIST = [
    Field.ELECTRIC_TERRAIN,
    Field.GRASSY_TERRAIN,
    Field.MISTY_TERRAIN,
    Field.PSYCHIC_TERRAIN,
]

_STATUS_IDX = {
    None: 0,
    Status.BRN: 1,
    Status.FRZ: 2,
    Status.PAR: 3,
    Status.PSN: 4,
    Status.TOX: 4,  # PSNと同じ枠 (正規化)
    Status.SLP: 5,
    Status.FNT: 6,
}

_BOOST_STATS = ["atk", "def", "spa", "spd", "spe", "accuracy", "evasion"]

# --------------------------------------------------------------------------- #
# 観測エンコーダ
# --------------------------------------------------------------------------- #


def _encode_status(status: Status | None) -> float:
    """ステータス異常を 0.0〜1.0 に正規化。"""
    return _STATUS_IDX.get(status, 0) / 6.0


def _encode_boosts(boosts: dict[str, int]) -> list[float]:
    """6段階の積み (-6〜+6) を -1.0〜+1.0 に正規化。"""
    return [boosts.get(s, 0) / 6.0 for s in _BOOST_STATS]


def _encode_type(t: PokemonType | None) -> float:
    if t is None:
        return 0.0
    return t.value / 20.0


def _encode_active_pokemon(pokemon: BattlePokemon | None) -> list[float]:
    """アクティブポケモンを10次元ベクトルに変換。"""
    if pokemon is None:
        return [0.0] * 10
    hp = pokemon.current_hp_fraction
    t1 = _encode_type(pokemon.type_1)
    t2 = _encode_type(pokemon.type_2)
    status = _encode_status(pokemon.status)
    boosts = _encode_boosts(pokemon.boosts)  # 6 values (atk/def/spa/spd/spe/acc)
    # -> 1 + 1 + 1 + 1 + 6 = 10
    return [hp, t1, t2, status] + boosts[:6]


def _encode_move(move: BattleMove | None) -> list[float]:
    """1技を5次元ベクトルに変換。"""
    if move is None:
        return [0.0] * 5
    power = min(move.base_power, 250) / 250.0
    move_type = _encode_type(move.type)
    acc = (move.accuracy if isinstance(move.accuracy, (int, float)) else 100) / 100.0
    pp_ratio = move.current_pp / max(move.max_pp, 1) if move.max_pp else 0.0
    # カテゴリ: physical=1, special=0.5, status=0
    cat_map = {"physical": 1.0, "special": 0.5, "status": 0.0}
    cat = cat_map.get(str(move.category).lower().split(".")[-1], 0.0)
    return [power, move_type, acc, pp_ratio, cat]


def encode_battle(battle: Battle) -> np.ndarray:
    """バトル状態を OBS_DIM 次元の float32 ベクトルに変換。"""
    obs: list[float] = []

    # --- 自分のアクティブポケモン (10)
    obs.extend(_encode_active_pokemon(battle.active_pokemon))

    # --- 自分の技 4枚 × 5 = 20
    moves = list(battle.available_moves)[:N_MOVES]
    moves += [None] * (N_MOVES - len(moves))  # type: ignore[list-item]
    for m in moves:
        obs.extend(_encode_move(m))

    # --- 相手のアクティブポケモン (10)
    obs.extend(_encode_active_pokemon(battle.opponent_active_pokemon))

    # --- 自分チーム HP% (6体)
    team_mons = list(battle.team.values())
    team_mons += [None] * (6 - len(team_mons))  # type: ignore[list-item]
    for mon in team_mons[:6]:
        obs.append(mon.current_hp_fraction if mon and not mon.fainted else 0.0)

    # --- 相手チーム HP% (6体)
    opp_team = list(battle.opponent_team.values())
    opp_team += [None] * (6 - len(opp_team))  # type: ignore[list-item]
    for mon in opp_team[:6]:
        obs.append(mon.current_hp_fraction if mon and not mon.fainted else 0.0)

    # --- 天候 1-hot (8)
    for w in _WEATHER_LIST:
        obs.append(1.0 if w in battle.weather else 0.0)

    # --- 地形 1-hot (4)
    for f in _TERRAIN_LIST:
        obs.append(1.0 if f in battle.fields else 0.0)

    # --- メガ進化フラグ (2)
    obs.append(1.0 if battle.can_mega_evolve else 0.0)
    obs.append(1.0 if battle.used_mega_evolve else 0.0)

    # --- フォースイッチフラグ (1)
    obs.append(1.0 if battle.force_switch else 0.0)

    # --- 有効行動マスク (9)
    mask = _compute_action_mask(battle)
    obs.extend(mask.tolist())

    arr = np.array(obs, dtype=np.float32)
    assert len(arr) == OBS_DIM, f"OBS_DIM mismatch: {len(arr)} != {OBS_DIM}"
    return arr


def _compute_action_mask(battle: Battle) -> np.ndarray:
    """各行動が有効かどうかを示す boolean マスクを返す。"""
    mask = np.zeros(N_ACTIONS, dtype=np.float32)

    if battle.force_switch:
        # フォースイッチ: 交代のみ有効
        switches = list(battle.available_switches)
        for i, _ in enumerate(switches[:N_BENCH]):
            mask[N_MOVES + i] = 1.0
        return mask

    # 技
    for i in range(min(len(battle.available_moves), N_MOVES)):
        mask[i] = 1.0

    # 交代 (トラップされていなければ)
    if not battle.trapped:
        switches = list(battle.available_switches)
        for i, _ in enumerate(switches[:N_BENCH]):
            mask[N_MOVES + i] = 1.0

    return mask


# --------------------------------------------------------------------------- #
# 報酬計算
# --------------------------------------------------------------------------- #


def calc_reward(
    prev_battle: Battle | None,
    current_battle: Battle,
) -> float:
    """ターン差分報酬を計算する。"""
    if current_battle.finished:
        return 1.0 if current_battle.won else -1.0

    if prev_battle is None:
        return 0.0

    reward = 0.0

    # 相手ポケモンのHP変化
    prev_opp_hp = sum(
        m.current_hp_fraction
        for m in prev_battle.opponent_team.values()
        if not m.fainted
    )
    curr_opp_hp = sum(
        m.current_hp_fraction
        for m in current_battle.opponent_team.values()
        if not m.fainted
    )
    reward += (prev_opp_hp - curr_opp_hp) * 0.1

    # 自分ポケモンのHP変化 (ダメージを受けたら負報酬)
    prev_my_hp = sum(
        m.current_hp_fraction
        for m in prev_battle.team.values()
        if not m.fainted
    )
    curr_my_hp = sum(
        m.current_hp_fraction
        for m in current_battle.team.values()
        if not m.fainted
    )
    reward -= (prev_my_hp - curr_my_hp) * 0.1

    # 相手ポケモンの気絶チェック
    prev_opp_count = sum(1 for m in prev_battle.opponent_team.values() if not m.fainted)
    curr_opp_count = sum(1 for m in current_battle.opponent_team.values() if not m.fainted)
    reward += (prev_opp_count - curr_opp_count) * 0.3

    # 自分ポケモンの気絶チェック
    prev_my_count = sum(1 for m in prev_battle.team.values() if not m.fainted)
    curr_my_count = sum(1 for m in current_battle.team.values() if not m.fainted)
    reward -= (prev_my_count - curr_my_count) * 0.3

    return float(reward)


# --------------------------------------------------------------------------- #
# Gymnasium 環境
# --------------------------------------------------------------------------- #


class ChampionsEnv(gym.Env, Player):
    """Pokemon Champions BSS 形式のシングルバトル Gymnasium 環境。

    Parameters
    ----------
    team:
        Showdown paste 形式の6体チーム文字列。省略時はテスト用デフォルトチームを使用。
    opponent_team:
        相手プレイヤーのチーム文字列。省略時は team と同じものを使用。
    battle_format:
        バトルフォーマット文字列 (デフォルト: gen9championsbssregma)。
    server_url:
        Showdown サーバーの WebSocket URL。
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        team: str | None = None,
        opponent_team: str | None = None,
        battle_format: str = "gen9championsbssregma",
        server_url: str = "ws://localhost:8000/showdown/websocket",
        server_action_url: str = "http://localhost:8000/action.php?",
        username: str = "ChampRL",
        opponent_username: str = "ChampRLOpp",
    ) -> None:
        server_config = ServerConfiguration(server_url, server_action_url)

        Player.__init__(
            self,
            account_configuration=AccountConfiguration(username, None),
            server_configuration=server_config,
            battle_format=battle_format,
            team=team,
        )

        self._opponent_team = opponent_team or team
        self._opponent_username = opponent_username
        self._server_config = server_config
        self._battle_format_str = battle_format

        # 観測・行動空間
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

        # バトル同期用の内部状態
        self._battle_ready = threading.Event()   # バトル開始待ち
        self._action_event = threading.Event()   # エージェントがアクションを送った
        self._obs_event = threading.Event()      # 次の観測が準備できた

        self._current_battle: Battle | None = None
        self._prev_battle_snapshot: dict | None = None
        self._pending_action: int | None = None
        self._battle_result: bool | None = None  # True=勝ち, False=負け, None=継続

        self._opponent: RandomPlayer | None = None
        self._episode_battle_future: asyncio.Future | None = None
        self._current_obs: np.ndarray = np.zeros(OBS_DIM, dtype=np.float32)

    # ------------------------------------------------------------------ #
    # Player の抽象メソッドを実装 (バトルループから呼ばれる)
    # ------------------------------------------------------------------ #

    def choose_move(self, battle: Battle) -> BattleOrder:
        """エージェントのアクション選択を待ち、BattleOrder に変換して返す。"""
        self._current_battle = battle
        self._current_obs = encode_battle(battle)
        self._obs_event.set()  # step() に「観測準備完了」を通知

        if battle.finished:
            return self.choose_default_move()

        # エージェントのアクションを待つ
        self._action_event.wait()
        self._action_event.clear()

        action = self._pending_action
        if action is None:
            return self.choose_random_move(battle)

        order = self._action_to_order(action, battle)
        return order

    def _action_to_order(self, action: int, battle: Battle) -> BattleOrder:
        """行動インデックスを BattleOrder に変換する。"""
        # 有効行動マスクで補正 (無効な行動はランダムへフォールバック)
        mask = _compute_action_mask(battle)

        if mask[action] > 0:
            if action < N_MOVES:
                # 技選択
                moves = list(battle.available_moves)
                if action < len(moves):
                    return self.create_order(moves[action])
            else:
                # 交代
                bench_idx = action - N_MOVES
                switches = list(battle.available_switches)
                if bench_idx < len(switches):
                    return self.create_order(switches[bench_idx])

        # フォールバック: ランダム
        return self.choose_random_move(battle)

    # ------------------------------------------------------------------ #
    # Gymnasium インタフェース
    # ------------------------------------------------------------------ #

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        # 前エピソードのクリーンアップ
        self._action_event.clear()
        self._obs_event.clear()
        self._pending_action = None
        self._current_battle = None

        # 相手プレイヤーを作成 (または再利用)
        if self._opponent is None:
            self._opponent = RandomPlayer(
                account_configuration=AccountConfiguration(
                    self._opponent_username, None
                ),
                server_configuration=self._server_config,
                battle_format=self._battle_format_str,
                team=self._opponent_team,
            )

        # バトルを非同期で開始
        asyncio.run_coroutine_threadsafe(
            self._run_battle(), POKE_LOOP
        )

        # 最初の観測を待つ
        self._obs_event.wait(timeout=30.0)
        self._obs_event.clear()

        info: dict = {
            "battle_tag": self._current_battle.battle_tag
            if self._current_battle
            else "",
            "action_mask": _compute_action_mask(self._current_battle)
            if self._current_battle
            else np.zeros(N_ACTIONS, dtype=np.float32),
        }
        return self._current_obs.copy(), info

    def step(
        self, action: int
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        """エージェントのアクションを送り、次のターンの観測・報酬を受け取る。"""
        battle = self._current_battle
        if battle is None:
            raise RuntimeError("step() called before reset()")

        # 前のバトル状態を保存 (報酬計算用)
        prev_battle = battle  # 参照保存 (属性はミュータブルなので注意)

        # アクションをバトルループに送信
        self._pending_action = action
        self._action_event.set()

        # 次の観測を待つ
        self._obs_event.wait(timeout=30.0)
        self._obs_event.clear()

        current_battle = self._current_battle

        # 終了判定
        terminated = current_battle is not None and current_battle.finished
        truncated = False

        # 報酬
        reward = calc_reward(prev_battle if not terminated else None, current_battle or battle)
        if terminated and current_battle is not None:
            reward = 1.0 if current_battle.won else -1.0

        info: dict = {
            "battle_tag": current_battle.battle_tag if current_battle else "",
            "won": current_battle.won if (current_battle and terminated) else None,
            "turn": current_battle.turn if current_battle else 0,
            "action_mask": _compute_action_mask(current_battle)
            if current_battle and not terminated
            else np.zeros(N_ACTIONS, dtype=np.float32),
        }

        return self._current_obs.copy(), reward, terminated, truncated, info

    def close(self) -> None:
        """リソースをクリーンアップする。"""
        # イベントを解放してデッドロックを防ぐ
        self._action_event.set()
        self._obs_event.set()

    # ------------------------------------------------------------------ #
    # 内部: バトル実行
    # ------------------------------------------------------------------ #

    async def _run_battle(self) -> None:
        """バックグラウンドで1バトルを実行する。"""
        assert self._opponent is not None
        try:
            await self._battle_against(self._opponent, n_battles=1)
        except Exception as e:
            self.logger.error("Battle error: %s", e)
        finally:
            # バトル終了を obs_event でシグナル (step() がタイムアウトしないよう)
            if self._current_battle and self._current_battle.finished:
                self._current_obs = encode_battle(self._current_battle)
            self._obs_event.set()

    # ------------------------------------------------------------------ #
    # バトル終了コールバックのオーバーライド
    # ------------------------------------------------------------------ #

    def _battle_finished_callback(self, battle: AbstractBattle) -> None:
        """バトル終了時に呼ばれる。最後の観測をセットして obs_event を発火。"""
        self._current_battle = battle  # type: ignore[assignment]
        self._current_obs = encode_battle(battle)  # type: ignore[arg-type]
        self._obs_event.set()
