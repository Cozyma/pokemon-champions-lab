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

# Action type labels
ACTION_TYPES = ["move", "switch", "mega_move"]
ACTION_TYPE_TO_IDX = {a: i for i, a in enumerate(ACTION_TYPES)}


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

    return np.array(features, dtype=np.float32)


def encode_action_type(sample: dict) -> int:
    """Encode action type as integer label."""
    return ACTION_TYPE_TO_IDX.get(sample.get("action_type", "move"), 0)


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


def train_action_type_model(
    min_rating: int = 1300,
    winners_only: bool = True,
) -> dict:
    """Train Stage 1: action type classifier.

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
