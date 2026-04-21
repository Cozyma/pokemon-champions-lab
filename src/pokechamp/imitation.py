"""Imitation learning from high-rated Showdown replays.

Two-stage behavioral cloning:
  Stage 1: Predict action type (move / switch / mega_move)
  Stage 2: Score candidates (which move or which switch target)

The model learns from (state, action) pairs extracted by parse_replays.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pokechamp import showdown_data

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ---------------------------------------------------------------------------
# Feature encoding
# ---------------------------------------------------------------------------

# All types in the game, lowercase
ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]
TYPE_TO_IDX = {t: i for i, t in enumerate(ALL_TYPES)}
N_TYPES = len(ALL_TYPES)

# Action type labels (binary: attack includes move+mega_move)
# Mega decision is handled separately by _should_mega_evolve (rule-based)
ACTION_TYPES = ["attack", "switch"]
ACTION_TYPE_TO_IDX = {"attack": 0, "switch": 1}


def _encode_species_types(species: str) -> list[float]:
    """Encode species types as N_TYPES-dim one-hot (multi-hot for dual type)."""
    vec = [0.0] * N_TYPES
    pokedex = showdown_data.load_pokedex()
    key = species.lower().replace(" ", "").replace("-", "")
    entry = pokedex.get(key)
    if entry:
        for t in entry.get("types", []):
            idx = TYPE_TO_IDX.get(t.lower())
            if idx is not None:
                vec[idx] = 1.0
    return vec


def _encode_species_stats(species: str) -> list[float]:
    """Encode species base stats (normalized to 0-1 range)."""
    pokedex = showdown_data.load_pokedex()
    key = species.lower().replace(" ", "").replace("-", "")
    entry = pokedex.get(key)
    if entry and "baseStats" in entry:
        bs = entry["baseStats"]
        return [
            bs.get("hp", 80) / 200.0,
            bs.get("atk", 80) / 200.0,
            bs.get("def", 80) / 200.0,
            bs.get("spa", 80) / 200.0,
            bs.get("spd", 80) / 200.0,
            bs.get("spe", 80) / 200.0,
        ]
    return [0.4] * 6  # default ~80/200


def encode_state(sample: dict) -> np.ndarray:
    """Encode a training sample's state into a feature vector.

    Features (total ~80 dims):
    - Active pokemon types (18) + stats (6) + hp (1) = 25
    - Opponent active types (18) + stats (6) + hp (1) = 25
    - Team HP state: 3 pokemon hp% (3)
    - Opponent team HP state: 3 pokemon hp% (3)
    - Weather one-hot (8)
    - Action type context: is_mega_available (1), turn_number (1)
    Total: ~66
    """
    features: list[float] = []

    # Active pokemon
    features.extend(_encode_species_types(sample.get("active_species", "")))
    features.extend(_encode_species_stats(sample.get("active_species", "")))
    features.append(sample.get("active_hp_pct", 100.0) / 100.0)

    # Opponent active
    features.extend(_encode_species_types(sample.get("opp_active_species", "")))
    features.extend(_encode_species_stats(sample.get("opp_active_species", "")))
    features.append(sample.get("opp_active_hp_pct", 100.0) / 100.0)

    # Team HP (from selected_full, up to 3)
    team_hp = sample.get("team_hp", {})
    selected = sample.get("selected_full", [])
    for i in range(3):
        if i < len(selected):
            features.append(team_hp.get(selected[i], 100.0) / 100.0)
        else:
            features.append(1.0)

    # Opponent team HP
    opp_hp = sample.get("opp_known_hp", {})
    opp_selected = sample.get("opp_selected_full", [])
    for i in range(3):
        if i < len(opp_selected):
            features.append(opp_hp.get(opp_selected[i], 100.0) / 100.0)
        else:
            features.append(1.0)

    # Weather
    weather = sample.get("weather", "")
    weather_types = ["sunnyday", "raindance", "sandstorm", "hail", "snowscape",
                     "desolateland", "primordialsea", "deltastream"]
    for w in weather_types:
        features.append(1.0 if weather == w else 0.0)

    # Turn number (normalized)
    features.append(min(sample.get("turn", 1), 30) / 30.0)

    # Type matchup features: how well we hit them / they hit us
    active_types = _encode_species_types(sample.get("active_species", ""))
    opp_types = _encode_species_types(sample.get("opp_active_species", ""))
    my_types_list = [ALL_TYPES[i] for i, v in enumerate(active_types) if v > 0]
    opp_types_list = [ALL_TYPES[i] for i, v in enumerate(opp_types) if v > 0]

    from pokechamp.ai_scoring import _calc_type_effectiveness
    # Best offensive matchup (max type eff we deal)
    if my_types_list and opp_types_list:
        best_atk = max(
            (_calc_type_effectiveness(t, opp_types_list) for t in my_types_list),
            default=1.0,
        )
        best_def = max(
            (_calc_type_effectiveness(t, my_types_list) for t in opp_types_list),
            default=1.0,
        )
    else:
        best_atk = 1.0
        best_def = 1.0
    features.append(best_atk / 4.0)  # normalize: max 4x
    features.append(best_def / 4.0)

    # HP advantage
    features.append((sample.get("active_hp_pct", 100) - sample.get("opp_active_hp_pct", 100)) / 100.0)

    # Team advantage: count alive own vs opponent
    team_hp = sample.get("team_hp", {})
    opp_hp = sample.get("opp_known_hp", {})
    own_alive = sum(1 for v in team_hp.values() if v > 0)
    opp_alive = sum(1 for v in opp_hp.values() if v > 0)
    features.append((own_alive - opp_alive) / 3.0)

    return np.array(features, dtype=np.float32)


def encode_action_type(sample: dict) -> int:
    """Encode action type as binary label: 0=attack, 1=switch.

    Mega moves are merged into attack — mega decision is rule-based.
    """
    if sample.get("action_type") == "switch":
        return 1
    return 0  # move and mega_move → attack


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def load_training_data(
    min_rating: int = 1300,
    winners_only: bool = False,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Load and encode training data.

    Returns:
        X: (N, feature_dim) state features
        y: (N,) action type labels
        samples: raw sample dicts (for stage 2 training)
    """
    path = DATA_DIR / "replays" / "training_data.json"
    raw = json.loads(path.read_text())

    # Filter
    samples = [s for s in raw if s.get("replay_rating", 0) >= min_rating]
    if winners_only:
        samples = [s for s in samples if s.get("won")]

    # Filter samples with full selection data
    samples = [s for s in samples if len(s.get("selected_full", [])) >= 2]

    X = np.array([encode_state(s) for s in samples], dtype=np.float32)
    y = np.array([encode_action_type(s) for s in samples], dtype=np.int64)

    return X, y, samples


# ---------------------------------------------------------------------------
# Simple model (sklearn-compatible for quick iteration)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Stage 2: Move / Switch target scoring
# ---------------------------------------------------------------------------


MOVE_CANDIDATE_DIM = 20


def _encode_move_candidate(
    move_id: str,
    active_types: list[str],
    opp_types: list[str],
    active_hp_pct: float = 100.0,
    opp_hp_pct: float = 100.0,
    is_faster: bool = True,
    opp_remaining: int = 3,
    turn: int = 1,
) -> list[float]:
    """Encode a move candidate as features for scoring."""
    sd = showdown_data.get_move(move_id)
    if not sd:
        return [0.0] * MOVE_CANDIDATE_DIM

    from pokechamp.ai_scoring import _calc_type_effectiveness

    bp = min(sd.get("basePower", 0), 250) / 250.0
    move_type = sd.get("type", "").lower()

    # STAB
    stab = 1.0 if move_type in active_types else 0.0

    # Type effectiveness vs opponent
    eff = _calc_type_effectiveness(move_type, opp_types) if opp_types else 1.0
    eff_norm = min(eff, 4.0) / 4.0

    # Category: physical=1, special=0.5, status=0
    cat_map = {"Physical": 1.0, "Special": 0.5, "Status": 0.0}
    cat = cat_map.get(sd.get("category", ""), 0.0)

    # Priority
    priority = max(min(sd.get("priority", 0), 5), -5) / 5.0

    # Is recovery
    is_heal = 1.0 if sd.get("isHeal") and sd.get("category") == "Status" else 0.0

    # Is setup (boosts)
    has_boosts = 1.0 if sd.get("boosts") and sd.get("category") == "Status" else 0.0

    # Is hazard
    is_hazard = 1.0 if sd.get("sideCondition") else 0.0

    # --- Situational value features ---

    # KO estimate: rough (bp * eff * stab_mult) / opp_hp
    stab_mult = 1.5 if stab else 1.0
    raw_power = sd.get("basePower", 0) * stab_mult * eff
    ko_estimate = min(raw_power / max(opp_hp_pct, 1.0), 3.0) / 3.0

    # Recovery value: higher when own HP is low
    recovery_value = is_heal * (1.0 - active_hp_pct / 100.0)

    # Setup value: higher when own HP is high and early game
    setup_value = has_boosts * (active_hp_pct / 100.0) * (1.0 - min(turn, 15) / 15.0)

    # Hazard value: proportional to opponent remaining pokemon
    hazard_value = is_hazard * (opp_remaining / 3.0)

    # Priority value: higher when slower or opponent low HP
    priority_value = 0.0
    if sd.get("priority", 0) > 0:
        priority_value = (1.0 - opp_hp_pct / 100.0)
        if not is_faster:
            priority_value += 0.3

    # Drain value: more valuable at low HP
    drain = 0.0
    if sd.get("drain"):
        drain = sd["drain"][0] / sd["drain"][1]
    drain_value = drain * (1.0 - active_hp_pct / 100.0)

    # Recoil risk: more dangerous at low HP
    recoil = 0.0
    if sd.get("recoil"):
        recoil = sd["recoil"][0] / sd["recoil"][1]
    recoil_risk = recoil * (1.0 - active_hp_pct / 100.0)

    # Self-debuff penalty
    self_debuff = 0.0
    if sd.get("selfBoosts"):
        self_debuff = -sum(v for v in sd["selfBoosts"].values() if v < 0) / 6.0

    return [
        bp, stab, eff_norm, cat, priority, is_heal, has_boosts, is_hazard,
        ko_estimate, recovery_value, setup_value, hazard_value,
        priority_value, drain_value, recoil_risk, self_debuff,
        active_hp_pct / 100.0, opp_hp_pct / 100.0,
        1.0 if is_faster else 0.0,
        min(turn, 30) / 30.0,
    ]


def _encode_switch_candidate(
    species: str, opp_types: list[str], opp_species: str,
) -> list[float]:
    """Encode a switch candidate as features for scoring."""
    from pokechamp.ai_scoring import _calc_type_effectiveness

    pokedex = showdown_data.load_pokedex()
    key = species.lower().replace(" ", "").replace("-", "")
    entry = pokedex.get(key)

    if not entry:
        return [0.0] * 6

    types = [t.lower() for t in entry.get("types", [])]
    bs = entry.get("baseStats", {})

    # Defensive: how well we resist opponent's STAB
    def_eff = 1.0
    if opp_types and types:
        def_eff = max(
            (_calc_type_effectiveness(t, types) for t in opp_types),
            default=1.0,
        )
    resist_score = 1.0 - min(def_eff, 4.0) / 4.0  # higher = better resist

    # Offensive: how well we hit opponent
    atk_eff = 1.0
    if types and opp_types:
        atk_eff = max(
            (_calc_type_effectiveness(t, opp_types) for t in types),
            default=1.0,
        )
    atk_score = min(atk_eff, 4.0) / 4.0

    # Bulk (defense + spdef normalized)
    bulk = (bs.get("def", 80) + bs.get("spd", 80)) / 400.0

    # Speed
    speed = bs.get("spe", 80) / 200.0

    # Offensive power
    power = max(bs.get("atk", 80), bs.get("spa", 80)) / 200.0

    # HP base
    hp = bs.get("hp", 80) / 200.0

    return [resist_score, atk_score, bulk, speed, power, hp]


def build_stage2_data(
    samples: list[dict],
) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], dict]:
    """Build Stage 2 training data: move and switch candidate scoring.

    For each sample, encodes the CHOSEN action as positive (1) and
    generates features. Returns separate datasets for moves and switches.
    """
    pokedex = showdown_data.load_pokedex()

    move_X: list[list[float]] = []
    move_y: list[int] = []
    switch_X: list[list[float]] = []
    switch_y: list[int] = []

    stats = {"move_samples": 0, "switch_samples": 0, "skipped": 0}

    # Pre-build: (replay_id, player, species) -> all moves used
    from collections import defaultdict
    instance_moves: dict[tuple, list[str]] = defaultdict(list)
    for s in samples:
        if s["action_type"] in ("move", "mega_move"):
            key = (s.get("replay_id", ""), s["player"], s["active_species"])
            move = s["action_detail"]
            if move not in instance_moves[key]:
                instance_moves[key].append(move)

    for s in samples:
        active = s.get("active_species", "")
        opp = s.get("opp_active_species", "")

        # Get types
        active_key = active.lower().replace(" ", "").replace("-", "")
        opp_key = opp.lower().replace(" ", "").replace("-", "")
        active_entry = pokedex.get(active_key, {})
        opp_entry = pokedex.get(opp_key, {})
        active_types = [t.lower() for t in active_entry.get("types", [])]
        opp_types = [t.lower() for t in opp_entry.get("types", [])]

        if s["action_type"] in ("move", "mega_move"):
            # Common context for move encoding
            active_hp = s.get("active_hp_pct", 100.0)
            opp_hp = s.get("opp_active_hp_pct", 100.0)
            turn = s.get("turn", 1)
            opp_known = s.get("opp_known_hp", {})
            opp_remaining = max(sum(1 for v in opp_known.values() if v > 0), 1)

            # Speed comparison (rough: use base stats)
            active_bs = active_entry.get("baseStats", {})
            opp_bs = opp_entry.get("baseStats", {})
            is_faster = active_bs.get("spe", 80) >= opp_bs.get("spe", 80)

            move_ctx = dict(
                active_hp_pct=active_hp, opp_hp_pct=opp_hp,
                is_faster=is_faster, opp_remaining=opp_remaining, turn=turn,
            )

            # Positive: the chosen move
            move_name = s["action_detail"]
            move_id = move_name.lower().replace(" ", "").replace("-", "").replace("'", "")
            features = _encode_move_candidate(move_id, active_types, opp_types, **move_ctx)
            state_features = encode_state(s).tolist()
            move_X.append(state_features + features)
            move_y.append(1)
            stats["move_samples"] += 1

            # Hard negatives: other moves this pokemon used in same replay
            key = (s.get("replay_id", ""), s["player"], active)
            alternatives = [m for m in instance_moves.get(key, []) if m != move_name]
            for alt in alternatives:
                alt_id = alt.lower().replace(" ", "").replace("-", "").replace("'", "")
                neg_features = _encode_move_candidate(alt_id, active_types, opp_types, **move_ctx)
                move_X.append(state_features + neg_features)
                move_y.append(0)

        elif s["action_type"] == "switch":
            chosen = s["action_detail"]
            selected = s.get("selected_full", [])
            if len(selected) < 2:
                stats["skipped"] += 1
                continue

            state_features = encode_state(s).tolist()

            # Positive: chosen switch target
            features = _encode_switch_candidate(chosen, opp_types, opp)
            switch_X.append(state_features + features)
            switch_y.append(1)
            stats["switch_samples"] += 1

            # Negative: other team members that weren't chosen
            for sp in selected:
                if sp != chosen and sp != active:
                    features = _encode_switch_candidate(sp, opp_types, opp)
                    switch_X.append(state_features + features)
                    switch_y.append(0)

    result = {}
    if move_X:
        result["move"] = (np.array(move_X, dtype=np.float32), np.array(move_y, dtype=np.int64))
    if switch_X:
        result["switch"] = (np.array(switch_X, dtype=np.float32), np.array(switch_y, dtype=np.int64))

    return result, stats


def train_stage2_models(min_rating: int = 1200) -> dict:
    """Train Stage 2: move scorer and switch scorer.

    Returns dict with models and metrics.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report

    _, _, samples = load_training_data(min_rating=min_rating)
    datasets, stats = build_stage2_data(samples)
    print(f"Stage 2 data: {stats}")

    results = {}
    for name, (X, y) in datasets.items():
        print(f"\n--- {name} scorer ---")
        print(f"  Samples: {len(X)}, Features: {X.shape[1]}, Pos: {(y==1).sum()}, Neg: {(y==0).sum()}")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y,
        )
        model = GradientBoostingClassifier(
            n_estimators=150, max_depth=4, learning_rate=0.1, random_state=42,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        accuracy = (y_pred == y_test).mean()

        print(f"  Accuracy: {accuracy:.3f}")
        print(classification_report(y_test, y_pred, target_names=["not_chosen", "chosen"]))
        results[name] = {"model": model, "accuracy": accuracy}

    return results


def train_action_type_model(
    min_rating: int = 1200,
    winners_only: bool = False,
) -> dict:
    """Train Stage 1: binary attack/switch classifier.

    Returns dict with model, accuracy, and feature info.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report

    X, y, samples = load_training_data(min_rating=min_rating, winners_only=winners_only)
    print(f"Training data: {len(X)} samples, {X.shape[1]} features")
    print(f"Action distribution: {dict(zip(*np.unique(y, return_counts=True)))}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )

    model = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = (y_pred == y_test).mean()

    print(f"\nTest accuracy: {accuracy:.3f}")
    print(classification_report(
        y_test, y_pred,
        target_names=ACTION_TYPES,
    ))

    return {
        "model": model,
        "accuracy": accuracy,
        "feature_dim": X.shape[1],
        "n_samples": len(X),
    }
