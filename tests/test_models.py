import pytest
from pokechamp.models import BaseStats, Move, Pokemon, Nature, TypeName


class TestBaseStats:
    def test_create_valid(self):
        stats = BaseStats(hp=108, attack=130, defense=95, sp_attack=80, sp_defense=85, speed=102)
        assert stats.hp == 108
        assert stats.speed == 102

    def test_reject_negative(self):
        with pytest.raises(ValueError):
            BaseStats(hp=-1, attack=130, defense=95, sp_attack=80, sp_defense=85, speed=102)


class TestMove:
    def test_attack_move(self):
        move = Move(
            name="じしん", name_en="earthquake", type=TypeName.GROUND,
            category="physical", power=100, accuracy=100, pp=10, priority=0,
        )
        assert move.power == 100
        assert move.category == "physical"

    def test_status_move_no_power(self):
        move = Move(
            name="つるぎのまい", name_en="swords-dance", type=TypeName.NORMAL,
            category="status", power=0, accuracy=100, pp=20, priority=0,
            stat_changes=[{"stat": "attack", "stages": 2}],
        )
        assert move.stat_changes[0]["stat"] == "attack"


class TestPokemon:
    def test_create_pokemon(self):
        pokemon = Pokemon(
            name="ガブリアス", name_en="garchomp",
            types=[TypeName.GROUND, TypeName.DRAGON],
            base_stats=BaseStats(hp=108, attack=130, defense=95, sp_attack=80, sp_defense=85, speed=102),
            abilities=["sand-veil", "rough-skin"],
            learnable_moves=["earthquake", "outrage"],
        )
        assert pokemon.name_en == "garchomp"
        assert len(pokemon.types) == 2


from pokechamp.models import TeamMember, Team, EVs, IVs


class TestTeamMember:
    def test_create_with_defaults(self):
        member = TeamMember(
            species="garchomp", ability="rough-skin", item="choice-scarf",
            nature=Nature.JOLLY, moves=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert member.ivs.attack == 31  # デフォルト全31
        assert member.evs.hp == 0  # デフォルト全0

    def test_create_with_custom_evs(self):
        member = TeamMember(
            species="garchomp", ability="rough-skin", item="choice-scarf",
            nature=Nature.JOLLY,
            evs=EVs(hp=4, attack=252, speed=252),
            moves=["earthquake", "outrage", "iron-head", "stone-edge"],
        )
        assert member.evs.attack == 252
        assert member.evs.defense == 0


class TestTeam:
    def test_create_team(self):
        members = [
            TeamMember(
                species=f"pokemon-{i}", ability="ability", item="item",
                nature=Nature.ADAMANT, moves=["move-a", "move-b"],
            )
            for i in range(6)
        ]
        team = Team(name="テストチーム", pokemon=members)
        assert len(team.pokemon) == 6
