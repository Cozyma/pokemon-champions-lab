from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TypeName(str, Enum):
    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    ELECTRIC = "electric"
    GRASS = "grass"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"
    STEEL = "steel"
    FAIRY = "fairy"


class Nature(str, Enum):
    HARDY = "hardy"
    LONELY = "lonely"
    BRAVE = "brave"
    ADAMANT = "adamant"
    NAUGHTY = "naughty"
    BOLD = "bold"
    DOCILE = "docile"
    RELAXED = "relaxed"
    IMPISH = "impish"
    LAX = "lax"
    TIMID = "timid"
    HASTY = "hasty"
    SERIOUS = "serious"
    JOLLY = "jolly"
    NAIVE = "naive"
    MODEST = "modest"
    MILD = "mild"
    QUIET = "quiet"
    BASHFUL = "bashful"
    RASH = "rash"
    CALM = "calm"
    GENTLE = "gentle"
    SASSY = "sassy"
    CAREFUL = "careful"
    QUIRKY = "quirky"


# 性格補正テーブル: {性格: (上昇ステータス, 下降ステータス)}  無補正はNone
NATURE_MODIFIERS: dict[Nature, tuple[str | None, str | None]] = {
    Nature.HARDY: (None, None),
    Nature.LONELY: ("attack", "defense"),
    Nature.BRAVE: ("attack", "speed"),
    Nature.ADAMANT: ("attack", "sp_attack"),
    Nature.NAUGHTY: ("attack", "sp_defense"),
    Nature.BOLD: ("defense", "attack"),
    Nature.DOCILE: (None, None),
    Nature.RELAXED: ("defense", "speed"),
    Nature.IMPISH: ("defense", "sp_attack"),
    Nature.LAX: ("defense", "sp_defense"),
    Nature.TIMID: ("speed", "attack"),
    Nature.HASTY: ("speed", "defense"),
    Nature.SERIOUS: (None, None),
    Nature.JOLLY: ("speed", "sp_attack"),
    Nature.NAIVE: ("speed", "sp_defense"),
    Nature.MODEST: ("sp_attack", "attack"),
    Nature.MILD: ("sp_attack", "defense"),
    Nature.QUIET: ("sp_attack", "speed"),
    Nature.BASHFUL: (None, None),
    Nature.RASH: ("sp_attack", "sp_defense"),
    Nature.CALM: ("sp_defense", "attack"),
    Nature.GENTLE: ("sp_defense", "defense"),
    Nature.SASSY: ("sp_defense", "speed"),
    Nature.CAREFUL: ("sp_defense", "sp_attack"),
    Nature.QUIRKY: (None, None),
}


class BaseStats(BaseModel):
    hp: int = Field(ge=1)
    attack: int = Field(ge=1)
    defense: int = Field(ge=1)
    sp_attack: int = Field(ge=1)
    sp_defense: int = Field(ge=1)
    speed: int = Field(ge=1)


class StatChange(BaseModel):
    stat: str  # "attack", "defense", "sp_attack", "sp_defense", "speed"
    stages: int  # +2 for swords dance, etc.


class Move(BaseModel):
    name: str
    name_en: str
    type: TypeName
    category: str  # "physical", "special", "status"
    power: int = Field(ge=0)
    accuracy: int = Field(ge=0, le=100)
    pp: int = Field(ge=1)
    priority: int = 0
    effects: list[str] = Field(default_factory=list)
    stat_changes: list[dict[str, int | str]] = Field(default_factory=list)


class MegaData(BaseModel):
    stone: str  # mega stone item name
    types: list[TypeName]
    ability: str
    base_stats: BaseStats


class Pokemon(BaseModel):
    name: str
    name_en: str
    types: list[TypeName]
    base_stats: BaseStats
    abilities: list[str]
    learnable_moves: list[str]
    mega: MegaData | None = None  # optional mega data
    mega_x: MegaData | None = None  # リザードンX等、複数メガ形態用
    mega_y: MegaData | None = None


class EVs(BaseModel):
    """チャンピオンズ仕様: 各0〜32、合計66。EV1=実数値1。"""
    hp: int = Field(default=0, ge=0, le=32)
    attack: int = Field(default=0, ge=0, le=32)
    defense: int = Field(default=0, ge=0, le=32)
    sp_attack: int = Field(default=0, ge=0, le=32)
    sp_defense: int = Field(default=0, ge=0, le=32)
    speed: int = Field(default=0, ge=0, le=32)


class IVs(BaseModel):
    hp: int = Field(default=31, ge=0, le=31)
    attack: int = Field(default=31, ge=0, le=31)
    defense: int = Field(default=31, ge=0, le=31)
    sp_attack: int = Field(default=31, ge=0, le=31)
    sp_defense: int = Field(default=31, ge=0, le=31)
    speed: int = Field(default=31, ge=0, le=31)


class TeamMember(BaseModel):
    species: str  # references pokemon name_en
    ability: str
    item: str
    nature: Nature
    evs: EVs = Field(default_factory=EVs)
    ivs: IVs = Field(default_factory=IVs)
    moves: list[str]  # references move name_en, max 4


class Team(BaseModel):
    name: str
    pokemon: list[TeamMember]


class BattleResult(BaseModel):
    pokemon_a: str
    pokemon_b: str
    win_rate_a: float
    win_rate_b: float
    avg_remaining_hp_a: float
    avg_remaining_hp_b: float


class MatchupMatrix(BaseModel):
    team_a_names: list[str]
    team_b_names: list[str]
    matrix: list[list[float]]  # win_rate_a[i][j]


class SelectionScore(BaseModel):
    team_a_selection: list[str]  # 3体
    team_b_selection: list[str]  # 3体
    score: float


class SetupEvaluation(BaseModel):
    pokemon: str
    move: str
    base_win_rate: float
    setup_win_rate: float
    delta: float


class MatchupResult(BaseModel):
    team_a: str
    team_b: str
    matrix: MatchupMatrix
    setup_evaluations: list[SetupEvaluation]
    selection_ranking: list[SelectionScore]
    overall_score: float
