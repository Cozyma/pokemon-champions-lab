"""poke-env + ローカルShowdown でChampions形式のテスト対戦を実行する。

Usage:
    cd /home/deploy/pokemon-champions-lab
    source .venv/bin/activate
    python scripts/test_poke_env.py
"""
from __future__ import annotations

import asyncio

from poke_env import AccountConfiguration, ServerConfiguration
from poke_env.player import RandomPlayer


# Showdown形式のチャンピオンズ構築（6体必須）
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

TEAM_2 = """
Gengar @ Gengarite
Ability: Cursed Body
EVs: 32 SpA / 32 Spe / 2 HP
Timid Nature
- Shadow Ball
- Sludge Wave
- Focus Blast
- Protect

Hydreigon @ Choice Scarf
Ability: Levitate
EVs: 32 SpA / 32 Spe / 2 HP
Timid Nature
- Dark Pulse
- Draco Meteor
- Flamethrower
- U-turn

Aegislash @ Leftovers
Ability: Stance Change
EVs: 32 SpA / 32 HP / 2 SpD
Modest Nature
- Shadow Ball
- Flash Cannon
- King's Shield
- Substitute

Hippowdon @ Lum Berry
Ability: Sand Stream
EVs: 32 HP / 32 Def / 2 SpD
Impish Nature
- Earthquake
- Stealth Rock
- Slack Off
- Stone Edge

Azumarill @ Sitrus Berry
Ability: Huge Power
EVs: 32 Atk / 32 HP / 2 Spe
Adamant Nature
- Play Rough
- Aqua Jet
- Belly Drum
- Bulldoze

Greninja @ Focus Sash
Ability: Protean
EVs: 32 SpA / 32 Spe / 2 HP
Timid Nature
- Ice Beam
- Dark Pulse
- Sludge Wave
- Water Shuriken
"""


async def main() -> None:
    # ローカルShowdownサーバー
    server_config = ServerConfiguration(
        "ws://localhost:8000/showdown/websocket",
        "http://localhost:8000/action.php?",
    )

    # 2つのランダムプレイヤーを作成
    player1 = RandomPlayer(
        account_configuration=AccountConfiguration("TestBot1", None),
        server_configuration=server_config,
        battle_format="gen9championsbssregma",
        team=TEAM_1,
    )
    player2 = RandomPlayer(
        account_configuration=AccountConfiguration("TestBot2", None),
        server_configuration=server_config,
        battle_format="gen9championsbssregma",
        team=TEAM_2,
    )

    print("Starting Champions test battle...")
    print(f"Format: {player1._format}")

    # 1戦だけ対戦
    await player1.battle_against(player2, n_battles=1)

    print(f"\nResults:")
    print(f"  Player1 wins: {player1.n_won_battles}")
    print(f"  Player2 wins: {player2.n_won_battles}")

    # バトルログを表示
    for battle_tag, battle in player1.battles.items():
        print(f"\n=== Battle: {battle_tag} ===")
        print(f"  Winner: {'Player1' if battle.won else 'Player2'}")
        print(f"  Turns: {battle.turn}")
        if battle.team:
            print(f"  Team: {[p.species for p in battle.team.values()]}")


if __name__ == "__main__":
    asyncio.run(main())
