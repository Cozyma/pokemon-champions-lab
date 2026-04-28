#!/usr/bin/env python3
"""Convert top-team-collection data to Showdown paste format team.txt files."""
import json
from pathlib import Path

TEAMS_DIR = Path(__file__).resolve().parent.parent / "teams"
POKEDEX_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "showdown-cache" / "pokedex.json"
)

# Each team is a dict with "name" (kebab-case slug) and "pokemon" (list of dicts).
# Each pokemon dict has: species, item, ability, nature, evs, moves.

TEAMS = [
    # ── Team 1: noname-champ ────────────────────────────────────────────
    {
        "name": "noname-champ",
        "pokemon": [
            {
                "species": "Gyarados",
                "item": "Gyaradosite",
                "ability": "Intimidate",
                "nature": "Jolly",
                "evs": {"hp": 11, "atk": 23, "spe": 32},
                "moves": ["Waterfall", "Ice Fang", "Power Whip", "Dragon Dance"],
            },
            {
                "species": "Aegislash-Shield",
                "item": "Focus Sash",
                "ability": "Stance Change",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Poltergeist",
                    "Close Combat",
                    "Swords Dance",
                    "Shadow Sneak",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Yache Berry",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "def": 1, "spd": 1},
                "moves": ["Scale Shot", "Earthquake", "Swords Dance", "Fire Fang"],
            },
            {
                "species": "Sylveon",
                "item": "Pixie Plate",
                "ability": "Pixilate",
                "nature": "Modest",
                "evs": {"hp": 31, "spa": 24, "spe": 11},
                "moves": ["Hyper Voice", "Misty Terrain", "Quick Attack", "Yawn"],
            },
            {
                "species": "Dragonite",
                "item": "Dragoninite",
                "ability": "Multiscale",
                "nature": "Modest",
                "evs": {"hp": 13, "spa": 32, "spe": 21},
                "moves": [
                    "Flamethrower",
                    "Thunderbolt",
                    "Extreme Speed",
                    "Draco Meteor",
                ],
            },
            {
                "species": "Basculegion",
                "item": "Choice Scarf",
                "ability": "Adaptability",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "def": 2},
                "moves": [
                    "Last Respects",
                    "Wave Crash",
                    "Flip Turn",
                    "Aqua Jet",
                ],
            },
        ],
    },
    # ── Team 2: howarori-r2400 ──────────────────────────────────────────
    {
        "name": "howarori-r2400",
        "pokemon": [
            {
                "species": "Floette-Eternal",
                "item": "Floettite",
                "ability": "Flower Veil",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 25, "hp": 2, "def": 7},
                "moves": ["Moonblast", "Draining Kiss", "Psychic", "Calm Mind"],
            },
            {
                "species": "Garchomp",
                "item": "Lum Berry",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Earthquake", "Scale Shot", "Fire Fang", "Swords Dance"],
            },
            {
                "species": "Araquanid",
                "item": "Sitrus Berry",
                "ability": "Water Bubble",
                "nature": "Adamant",
                "evs": {"hp": 32, "atk": 32, "def": 2},
                "moves": ["Liquidation", "Lunge", "Sticky Web", "Mirror Coat"],
            },
            {
                "species": "Gengar",
                "item": "Focus Sash",
                "ability": "Cursed Body",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": ["Hex", "Sludge Wave", "Icy Wind", "Will-O-Wisp"],
            },
            {
                "species": "Charizard",
                "item": "Charizardite X",
                "ability": "Blaze",
                "nature": "Jolly",
                "evs": {"atk": 27, "spe": 27, "hp": 12},
                "moves": [
                    "Flare Blitz",
                    "Outrage",
                    "Thunder Punch",
                    "Swords Dance",
                ],
            },
            {
                "species": "Mimikyu",
                "item": "Spell Tag",
                "ability": "Disguise",
                "nature": "Adamant",
                "evs": {"atk": 32, "def": 32, "hp": 1, "spd": 1},
                "moves": [
                    "Play Rough",
                    "Shadow Sneak",
                    "Shadow Claw",
                    "Swords Dance",
                ],
            },
        ],
    },
    # ── Team 3: unaware-wall-r2400 ──────────────────────────────────────
    {
        "name": "unaware-wall-r2400",
        "pokemon": [
            {
                "species": "Clefable",
                "item": "Clefabirite",
                "ability": "Unaware",
                "nature": "Bold",
                "evs": {"hp": 32, "def": 15, "spa": 1, "spd": 1, "spe": 18},
                "moves": [
                    "Draining Kiss",
                    "Flamethrower",
                    "Calm Mind",
                    "Moonlight",
                ],
            },
            {
                "species": "Skeledirge",
                "item": "Sitrus Berry",
                "ability": "Unaware",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spe": 2},
                "moves": ["Torch Song", "Shadow Ball", "Will-O-Wisp", "Slack Off"],
            },
            {
                "species": "Gyarados",
                "item": "Leftovers",
                "ability": "Intimidate",
                "nature": "Adamant",
                "evs": {"hp": 31, "atk": 26, "spd": 1, "spe": 7},
                "moves": ["Waterfall", "Power Whip", "Thunder Wave", "Taunt"],
            },
            {
                "species": "Glimmora",
                "item": "Focus Sash",
                "ability": "Toxic Debris",
                "nature": "Impish",
                "evs": {"def": 28, "spe": 32},
                "moves": ["Mud Shot", "Stealth Rock", "Reflect", "Memento"],
            },
            {
                "species": "Polteageist",
                "item": "White Herb",
                "ability": "Cursed Body",
                "nature": "Timid",
                "evs": {"def": 32, "spd": 1, "spe": 19},
                "moves": ["Shadow Ball", "Substitute", "Shell Smash", "Baton Pass"],
            },
            {
                "species": "Venusaur",
                "item": "Venusaurite",
                "ability": "Chlorophyll",
                "nature": "Calm",
                "evs": {"hp": 21, "spa": 2, "spe": 8},
                "moves": ["Giga Drain", "Sludge Wave", "Earth Power", "Synthesis"],
            },
        ],
    },
    # ── Team 4: suzu-r2400 ──────────────────────────────────────────────
    {
        "name": "suzu-r2400",
        "pokemon": [
            {
                "species": "Arcanine",
                "item": "Shuca Berry",
                "ability": "Intimidate",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": [
                    "Flare Blitz",
                    "Extreme Speed",
                    "Will-O-Wisp",
                    "Morning Sun",
                ],
            },
            {
                "species": "Meganium",
                "item": "Meganiumite",
                "ability": "Overgrow",
                "nature": "Modest",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Solar Beam",
                    "Synthesis",
                    "Weather Ball",
                    "Dazzling Gleam",
                ],
            },
            {
                "species": "Hippowdon",
                "item": "Sitrus Berry",
                "ability": "Sand Stream",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["Earthquake", "Yawn", "Slack Off", "Stealth Rock"],
            },
            {
                "species": "Archaludon",
                "item": "Leftovers",
                "ability": "Stamina",
                "nature": "Calm",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": [
                    "Flash Cannon",
                    "Dragon Tail",
                    "Thunderbolt",
                    "Substitute",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Yache Berry",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Earthquake", "Scale Shot", "Rock Tomb", "Stealth Rock"],
            },
            {
                "species": "Greninja",
                "item": "Greninjite",
                "ability": "Torrent",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Dark Pulse",
                    "Ice Beam",
                    "Sludge Wave",
                    "Toxic Spikes",
                ],
            },
        ],
    },
    # ── Team 5: kurifuto-r2200 ──────────────────────────────────────────
    {
        "name": "kurifuto-r2200",
        "pokemon": [
            {
                "species": "Goodra-Hisui",
                "item": "Sitrus Berry",
                "ability": "Sap Sipper",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 32, "spd": 2},
                "moves": [
                    "Draco Meteor",
                    "Flamethrower",
                    "Thunderbolt",
                    "Acid Spray",
                ],
            },
            {
                "species": "Corviknight",
                "item": "Leftovers",
                "ability": "Mirror Armor",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["U-turn", "Body Press", "Iron Defense", "Roost"],
            },
            {
                "species": "Greninja",
                "item": "Focus Sash",
                "ability": "Protean",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Ice Beam",
                    "Dark Pulse",
                    "Sludge Wave",
                    "Water Shuriken",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Choice Scarf",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Outrage", "Earthquake", "Rock Slide", "Stealth Rock"],
            },
            {
                "species": "Kangaskhan",
                "item": "Kangaskhanite",
                "ability": "Scrappy",
                "nature": "Adamant",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Fake Out",
                    "Double-Edge",
                    "Earthquake",
                    "Sucker Punch",
                ],
            },
            {
                "species": "Charizard",
                "item": "Charizardite Y",
                "ability": "Blaze",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Overheat",
                    "Flamethrower",
                    "Nitro Charge",
                    "Solar Beam",
                ],
            },
        ],
    },
    # ── Team 6: 1leven-r2200 ────────────────────────────────────────────
    {
        "name": "1leven-r2200",
        "pokemon": [
            {
                "species": "Golurk",
                "item": "Golurgite",
                "ability": "Iron Fist",
                "nature": "Adamant",
                "evs": {"hp": 29, "atk": 18, "spd": 11, "spe": 8},
                "moves": [
                    "Poltergeist",
                    "Headlong Rush",
                    "Imprison",
                    "Iron Defense",
                ],
            },
            {
                "species": "Snorlax",
                "item": "Leftovers",
                "ability": "Thick Fat",
                "nature": "Calm",
                "evs": {"hp": 32, "atk": 2, "spd": 32},
                "moves": ["Fissure", "Facade", "Crunch", "Rest"],
            },
            {
                "species": "Clefable",
                "item": "Clefabirite",
                "ability": "Unaware",
                "nature": "Bold",
                "evs": {"hp": 31, "def": 32, "spd": 3},
                "moves": [
                    "Moonblast",
                    "Flamethrower",
                    "Cosmic Power",
                    "Moonlight",
                ],
            },
            {
                "species": "Toxapex",
                "item": "Mental Herb",
                "ability": "Regenerator",
                "nature": "Calm",
                "evs": {"hp": 32, "atk": 2, "spd": 32},
                "moves": ["Throat Chop", "Toxic", "Haze", "Recover"],
            },
            {
                "species": "Skeledirge",
                "item": "Kasib Berry",
                "ability": "Unaware",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spa": 2},
                "moves": ["Torch Song", "Hex", "Will-O-Wisp", "Slack Off"],
            },
            {
                "species": "Chesnaught",
                "item": "Brigalosite",
                "ability": "Bulletproof",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["Body Press", "Spikes", "Iron Defense", "Synthesis"],
            },
        ],
    },
    # ── Team 7: howarori-r2200 ──────────────────────────────────────────
    {
        "name": "howarori-r2200",
        "pokemon": [
            {
                "species": "Dragonite",
                "item": "Dragoninite",
                "ability": "Multiscale",
                "nature": "Modest",
                "evs": {"hp": 21, "spa": 32, "spe": 13},
                "moves": [
                    "Draco Meteor",
                    "Air Slash",
                    "Thunderbolt",
                    "Extreme Speed",
                ],
            },
            {
                "species": "Kangaskhan",
                "item": "Kangaskhanite",
                "ability": "Scrappy",
                "nature": "Adamant",
                "evs": {"hp": 23, "atk": 32, "spe": 11},
                "moves": [
                    "Body Slam",
                    "Sucker Punch",
                    "Earthquake",
                    "Ice Punch",
                ],
            },
            {
                "species": "Corviknight",
                "item": "Leftovers",
                "ability": "Pressure",
                "nature": "Calm",
                "evs": {"hp": 32, "def": 15, "spd": 19},
                "moves": ["U-turn", "Body Press", "Iron Head", "Roost"],
            },
            {
                "species": "Ceruledge",
                "item": "Focus Sash",
                "ability": "Weak Armor",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 1, "def": 1},
                "moves": [
                    "Bitter Blade",
                    "Poltergeist",
                    "Close Combat",
                    "Shadow Sneak",
                ],
            },
            {
                "species": "Mimikyu",
                "item": "Lum Berry",
                "ability": "Disguise",
                "nature": "Adamant",
                "evs": {"atk": 32, "def": 32, "hp": 1, "spe": 1},
                "moves": [
                    "Play Rough",
                    "Shadow Sneak",
                    "Drain Punch",
                    "Swords Dance",
                ],
            },
            {
                "species": "Primarina",
                "item": "Sitrus Berry",
                "ability": "Torrent",
                "nature": "Bold",
                "evs": {"hp": 32, "def": 14, "spa": 14, "spe": 6},
                "moves": [
                    "Sparkling Aria",
                    "Moonblast",
                    "Aqua Jet",
                    "Encore",
                ],
            },
        ],
    },
    # ── Team 8: chiku-r2300 ─────────────────────────────────────────────
    {
        "name": "chiku-r2300",
        "pokemon": [
            {
                "species": "Starmie",
                "item": "Starmieite",
                "ability": "Natural Cure",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 30, "hp": 2, "def": 1, "spd": 1},
                "moves": [
                    "Waterfall",
                    "Flip Turn",
                    "Aqua Jet",
                    "Zen Headbutt",
                ],
            },
            {
                "species": "Floette-Eternal",
                "item": "Choice Scarf",
                "ability": "Flower Veil",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Light of Ruin",
                    "Moonblast",
                    "Psychic",
                    "Petal Dance",
                ],
            },
            {
                "species": "Meganium",
                "item": "Meganiumite",
                "ability": "Overgrow",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 17, "spe": 14, "def": 3},
                "moves": [
                    "Solar Beam",
                    "Weather Ball",
                    "Synthesis",
                    "Substitute",
                ],
            },
            {
                "species": "Diggersby",
                "item": "Focus Sash",
                "ability": "Huge Power",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 1, "def": 1},
                "moves": [
                    "Earthquake",
                    "Ice Punch",
                    "Thunder Punch",
                    "Quick Attack",
                ],
            },
            {
                "species": "Pelipper",
                "item": "Sitrus Berry",
                "ability": "Drizzle",
                "nature": "Bold",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["Surf", "U-turn", "Hurricane", "Tailwind"],
            },
            {
                "species": "Archaludon",
                "item": "Shuca Berry",
                "ability": "Stamina",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 15, "def": 7, "spd": 1, "spe": 11},
                "moves": [
                    "Draco Meteor",
                    "Flash Cannon",
                    "Electro Shot",
                    "Focus Blast",
                ],
            },
        ],
    },
    # ── Team 9: cr7-r2300 ───────────────────────────────────────────────
    {
        "name": "cr7-r2300",
        "pokemon": [
            {
                "species": "Charizard",
                "item": "Charizardite Y",
                "ability": "Blaze",
                "nature": "Bold",
                "evs": {"hp": 30, "def": 32, "spa": 1, "spd": 1, "spe": 2},
                "moves": [
                    "Flamethrower",
                    "Will-O-Wisp",
                    "Roost",
                    "Solar Beam",
                ],
            },
            {
                "species": "Hippowdon",
                "item": "Sitrus Berry",
                "ability": "Sand Stream",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 17, "spd": 17},
                "moves": ["Yawn", "Earthquake", "Slack Off", "Stealth Rock"],
            },
            {
                "species": "Gengar",
                "item": "Gengarite",
                "ability": "Cursed Body",
                "nature": "Timid",
                "evs": {"hp": 12, "spa": 32, "spe": 22},
                "moves": [
                    "Shadow Ball",
                    "Focus Blast",
                    "Icy Wind",
                    "Sludge Wave",
                ],
            },
            {
                "species": "Umbreon",
                "item": "Leftovers",
                "ability": "Inner Focus",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 30, "spd": 4},
                "moves": ["Yawn", "Protect", "Foul Play", "Wish"],
            },
            {
                "species": "Scizor",
                "item": "Lum Berry",
                "ability": "Technician",
                "nature": "Adamant",
                "evs": {"hp": 30, "atk": 32, "def": 4},
                "moves": [
                    "Bullet Punch",
                    "Close Combat",
                    "Swords Dance",
                    "U-turn",
                ],
            },
            {
                "species": "Empoleon",
                "item": "Chople Berry",
                "ability": "Torrent",
                "nature": "Calm",
                "evs": {"hp": 32, "def": 5, "spd": 29},
                "moves": ["Yawn", "Surf", "Flip Turn", "Stealth Rock"],
            },
        ],
    },
    # ── Team 10: mana-r2300 ─────────────────────────────────────────────
    {
        "name": "mana-r2300",
        "pokemon": [
            {
                "species": "Dragonite",
                "item": "Dragoninite",
                "ability": "Multiscale",
                "nature": "Modest",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Air Slash",
                    "Draco Meteor",
                    "Thunderbolt",
                    "Extreme Speed",
                ],
            },
            {
                "species": "Kangaskhan",
                "item": "Kangaskhanite",
                "ability": "Scrappy",
                "nature": "Adamant",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Fake Out",
                    "Double-Edge",
                    "Ice Punch",
                    "Earthquake",
                ],
            },
            {
                "species": "Hippowdon",
                "item": "Leftovers",
                "ability": "Sand Stream",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["Earthquake", "Stealth Rock", "Yawn", "Slack Off"],
            },
            {
                "species": "Primarina",
                "item": "Sitrus Berry",
                "ability": "Torrent",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 32, "spd": 2},
                "moves": [
                    "Sparkling Aria",
                    "Moonblast",
                    "Calm Mind",
                    "Aqua Jet",
                ],
            },
            {
                "species": "Meowscarada",
                "item": "Choice Scarf",
                "ability": "Protean",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Flower Trick", "Knock Off", "U-turn", "Low Kick"],
            },
            {
                "species": "Aegislash-Shield",
                "item": "Spell Tag",
                "ability": "Stance Change",
                "nature": "Adamant",
                "evs": {"hp": 32, "atk": 32, "spd": 2},
                "moves": [
                    "Poltergeist",
                    "Shadow Sneak",
                    "Close Combat",
                    "Swords Dance",
                ],
            },
        ],
    },
    # ── Team 11: sato-r2300 ─────────────────────────────────────────────
    {
        "name": "sato-r2300",
        "pokemon": [
            {
                "species": "Lopunny",
                "item": "Lopunnite",
                "ability": "Cute Charm",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32},
                "moves": [
                    "Close Combat",
                    "Fake Out",
                    "Mach Punch",
                    "Triple Axel",
                ],
            },
            {
                "species": "Primarina",
                "item": "Chesto Berry",
                "ability": "Torrent",
                "nature": "Calm",
                "evs": {"hp": 32, "spa": 19, "spd": 14},
                "moves": ["Sparkling Aria", "Moonblast", "Aqua Jet", "Rest"],
            },
            {
                "species": "Aegislash-Shield",
                "item": "Leftovers",
                "ability": "Stance Change",
                "nature": "Adamant",
                "evs": {"hp": 26, "atk": 32, "spe": 8},
                "moves": [
                    "Poltergeist",
                    "Iron Head",
                    "Shadow Sneak",
                    "King's Shield",
                ],
            },
            {
                "species": "Dragonite",
                "item": "Dragoninite",
                "ability": "Multiscale",
                "nature": "Modest",
                "evs": {"hp": 31, "def": 12, "spa": 5, "spd": 4, "spe": 14},
                "moves": [
                    "Air Slash",
                    "Flamethrower",
                    "Ice Beam",
                    "Roost",
                ],
            },
            {
                "species": "Glimmora",
                "item": "Focus Sash",
                "ability": "Toxic Debris",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32},
                "moves": [
                    "Sludge Wave",
                    "Mud Shot",
                    "Mortal Spin",
                    "Stealth Rock",
                ],
            },
            {
                "species": "Corviknight",
                "item": "Lum Berry",
                "ability": "Mirror Armor",
                "nature": "Jolly",
                "evs": {"hp": 16, "atk": 18, "spe": 32},
                "moves": ["Brave Bird", "Bulk Up", "Roost", "Taunt"],
            },
        ],
    },
    # ── Team 12: gray-r2001 ─────────────────────────────────────────────
    {
        "name": "gray-r2001",
        "pokemon": [
            {
                "species": "Archaludon",
                "item": "Sitrus Berry",
                "ability": "Stamina",
                "nature": "Calm",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": [
                    "Draco Meteor",
                    "Flash Cannon",
                    "Thunder Wave",
                    "Stealth Rock",
                ],
            },
            {
                "species": "Scizor",
                "item": "Scizorite",
                "ability": "Technician",
                "nature": "Adamant",
                "evs": {"hp": 32, "atk": 32, "spe": 2},
                "moves": [
                    "Bullet Punch",
                    "Close Combat",
                    "Knock Off",
                    "Swords Dance",
                ],
            },
            {
                "species": "Charizard",
                "item": "Charizardite Y",
                "ability": "Solar Power",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Flamethrower",
                    "Air Slash",
                    "Solar Beam",
                    "Nitro Charge",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Choice Scarf",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Earthquake", "Outrage", "Stone Edge", "Poison Jab"],
            },
            {
                "species": "Primarina",
                "item": "Mystic Water",
                "ability": "Torrent",
                "nature": "Modest",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Sparkling Aria",
                    "Moonblast",
                    "Encore",
                    "Aqua Jet",
                ],
            },
            {
                "species": "Ceruledge",
                "item": "Focus Sash",
                "ability": "Weak Armor",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Bitter Blade",
                    "Poltergeist",
                    "Close Combat",
                    "Shadow Sneak",
                ],
            },
        ],
    },
    # ── Team 14: rb-neko-r2001 ──────────────────────────────────────────
    {
        "name": "rb-neko-r2001",
        "pokemon": [
            {
                "species": "Kangaskhan",
                "item": "Kangaskhanite",
                "ability": "Scrappy",
                "nature": "Adamant",
                "evs": {"hp": 23, "atk": 32, "spe": 11},
                "moves": [
                    "Fake Out",
                    "Ice Punch",
                    "Earthquake",
                    "Sucker Punch",
                ],
            },
            {
                "species": "Aegislash-Shield",
                "item": "Spell Tag",
                "ability": "Stance Change",
                "nature": "Adamant",
                "evs": {"hp": 32, "atk": 32, "spe": 8},
                "moves": [
                    "Poltergeist",
                    "Shadow Ball",
                    "Close Combat",
                    "Shadow Sneak",
                ],
            },
            {
                "species": "Volcarona",
                "item": "Leftovers",
                "ability": "Swarm",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Flamethrower",
                    "Giga Drain",
                    "Psychic",
                    "Quiver Dance",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Choice Scarf",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Outrage", "Earthquake", "Rock Slide", "Poison Jab"],
            },
            {
                "species": "Greninja",
                "item": "Focus Sash",
                "ability": "Protean",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": ["Surf", "Dark Pulse", "Ice Beam", "Water Shuriken"],
            },
            {
                "species": "Mimikyu",
                "item": "Scope Lens",
                "ability": "Disguise",
                "nature": "Adamant",
                "evs": {"atk": 32, "hp": 32, "def": 2},
                "moves": [
                    "Shadow Claw",
                    "Play Rough",
                    "Swords Dance",
                    "Shadow Sneak",
                ],
            },
        ],
    },
    # ── Team 15: key-r2400 ──────────────────────────────────────────────
    {
        "name": "key-r2400",
        "pokemon": [
            {
                "species": "Hippowdon",
                "item": "Sitrus Berry",
                "ability": "Sand Stream",
                "nature": "Calm",
                "evs": {"hp": 32, "def": 2, "spd": 32},
                "moves": ["Earthquake", "Yawn", "Stealth Rock", "Whirlwind"],
            },
            {
                "species": "Excadrill",
                "item": "Soft Sand",
                "ability": "Sand Rush",
                "nature": "Jolly",
                "evs": {"atk": 32, "spd": 15, "spe": 19},
                "moves": [
                    "Earthquake",
                    "Iron Head",
                    "Rock Slide",
                    "Swords Dance",
                ],
            },
            {
                "species": "Gyarados",
                "item": "Gyaradosite",
                "ability": "Intimidate",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 1, "def": 1},
                "moves": [
                    "Waterfall",
                    "Ice Fang",
                    "Power Whip",
                    "Dragon Dance",
                ],
            },
            {
                "species": "Dragonite",
                "item": "Dragoninite",
                "ability": "Multiscale",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 1, "spd": 1},
                "moves": [
                    "Draco Meteor",
                    "Flamethrower",
                    "Thunderbolt",
                    "Ice Beam",
                ],
            },
            {
                "species": "Archaludon",
                "item": "Leftovers",
                "ability": "Stamina",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 25, "spe": 9},
                "moves": [
                    "Draco Meteor",
                    "Foul Play",
                    "Thunderbolt",
                    "Substitute",
                ],
            },
            {
                "species": "Mimikyu",
                "item": "Spell Tag",
                "ability": "Disguise",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 1, "def": 1},
                "moves": [
                    "Play Rough",
                    "Shadow Claw",
                    "Shadow Sneak",
                    "Swords Dance",
                ],
            },
        ],
    },
    # ── Team 16: shioinu-r2400 ──────────────────────────────────────────
    {
        "name": "shioinu-r2400",
        "pokemon": [
            {
                "species": "Infernape",
                "item": "Wacan Berry",
                "ability": "Iron Fist",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": [
                    "Rock Tomb",
                    "Taunt",
                    "Will-O-Wisp",
                    "Stealth Rock",
                ],
            },
            {
                "species": "Heliolisk",
                "item": "Choice Scarf",
                "ability": "Dry Skin",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": ["Thunderbolt", "Volt Switch", "Glare", "Shed Tail"],
            },
            {
                "species": "Froslass",
                "item": "Frostlasite",
                "ability": "Cursed Body",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": ["Blizzard", "Shadow Ball", "Aurora Veil", "Nasty Plot"],
            },
            {
                "species": "Gyarados",
                "item": "Gyaradosite",
                "ability": "Intimidate",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Waterfall",
                    "Ice Fang",
                    "Earthquake",
                    "Dragon Dance",
                ],
            },
            {
                "species": "Aegislash-Shield",
                "item": "Focus Sash",
                "ability": "Stance Change",
                "nature": "Adamant",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Poltergeist",
                    "Close Combat",
                    "Shadow Sneak",
                    "Swords Dance",
                ],
            },
            {
                "species": "Hawlucha",
                "item": "Sitrus Berry",
                "ability": "Unburden",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Close Combat",
                    "Brave Bird",
                    "Substitute",
                    "Swords Dance",
                ],
            },
        ],
    },
    # ── Team 17: daisangen-r2500 ────────────────────────────────────────
    {
        "name": "daisangen-r2500",
        "pokemon": [
            {
                "species": "Kangaskhan",
                "item": "Kangaskhanite",
                "ability": "Scrappy",
                "nature": "Adamant",
                "evs": {"hp": 21, "atk": 31, "spe": 14},
                "moves": [
                    "Body Slam",
                    "Earthquake",
                    "Ice Punch",
                    "Fire Punch",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Choice Scarf",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Outrage", "Earthquake", "Rock Slide", "Poison Jab"],
            },
            {
                "species": "Froslass",
                "item": "Frostlasite",
                "ability": "Cursed Body",
                "nature": "Timid",
                "evs": {"hp": 12, "spa": 29, "spe": 25},
                "moves": ["Blizzard", "Shadow Ball", "Thunderbolt", "Taunt"],
            },
            {
                "species": "Volcarona",
                "item": "Lum Berry",
                "ability": "Swarm",
                "nature": "Modest",
                "evs": {"spa": 32, "spe": 21, "hp": 13},
                "moves": [
                    "Heat Wave",
                    "Bug Buzz",
                    "Substitute",
                    "Quiver Dance",
                ],
            },
            {
                "species": "Primarina",
                "item": "Focus Sash",
                "ability": "Torrent",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "atk": 2},
                "moves": [
                    "Sparkling Aria",
                    "Moonblast",
                    "Aqua Jet",
                    "Encore",
                ],
            },
            {
                "species": "Archaludon",
                "item": "Leftovers",
                "ability": "Stamina",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 15, "def": 7, "spd": 1, "spe": 11},
                "moves": [
                    "Focus Blast",
                    "Thunderbolt",
                    "Foul Play",
                    "Substitute",
                ],
            },
        ],
    },
    # ── Team 18: gusha-r2200 ────────────────────────────────────────────
    {
        "name": "gusha-r2200",
        "pokemon": [
            {
                "species": "Tyranitar",
                "item": "Leftovers",
                "ability": "Sand Stream",
                "nature": "Calm",
                "evs": {"hp": 32, "spd": 32, "def": 2},
                "moves": ["Rock Blast", "Foul Play", "Stealth Rock", "Protect"],
            },
            {
                "species": "Excadrill",
                "item": "Sitrus Berry",
                "ability": "Mold Breaker",
                "nature": "Calm",
                "evs": {"hp": 32, "atk": 2, "spd": 32},
                "moves": [
                    "Earthquake",
                    "Iron Head",
                    "Horn Drill",
                    "Stealth Rock",
                ],
            },
            {
                "species": "Meganium",
                "item": "Meganiumite",
                "ability": "Overgrow",
                "nature": "Calm",
                "evs": {"hp": 32, "spd": 30, "def": 1, "spa": 1, "spe": 3},
                "moves": [
                    "Solar Beam",
                    "Weather Ball",
                    "Dazzling Gleam",
                    "Synthesis",
                ],
            },
            {
                "species": "Skarmory",
                "item": "BrightPowder",
                "ability": "Sturdy",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["Drill Peck", "Body Press", "Iron Defense", "Roost"],
            },
            {
                "species": "Venusaur",
                "item": "Venusaurite",
                "ability": "Overgrow",
                "nature": "Calm",
                "evs": {"hp": 32, "spd": 20, "def": 11, "spe": 3},
                "moves": [
                    "Sludge Bomb",
                    "Earth Power",
                    "Leech Seed",
                    "Synthesis",
                ],
            },
            {
                "species": "Toxapex",
                "item": "Black Sludge",
                "ability": "Regenerator",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 32, "spd": 2},
                "moves": ["Infestation", "Toxic", "Haze", "Recover"],
            },
        ],
    },
    # ── Team 19: teramatsu-r2100 ────────────────────────────────────────
    {
        "name": "teramatsu-r2100",
        "pokemon": [
            {
                "species": "Gyarados",
                "item": "Gyaradosite",
                "ability": "Intimidate",
                "nature": "Adamant",
                "evs": {"hp": 1, "atk": 32, "def": 32, "spd": 1},
                "moves": [
                    "Aqua Tail",
                    "Power Whip",
                    "Earthquake",
                    "Avalanche",
                ],
            },
            {
                "species": "Dragonite",
                "item": "Dragoninite",
                "ability": "Multiscale",
                "nature": "Modest",
                "evs": {"hp": 31, "spa": 32, "spd": 1},
                "moves": [
                    "Draco Meteor",
                    "Hurricane",
                    "Fire Blast",
                    "Thunder",
                ],
            },
            {
                "species": "Slowking",
                "item": "Black Belt",
                "ability": "Regenerator",
                "nature": "Modest",
                "evs": {"hp": 31, "spa": 32, "def": 3},
                "moves": [
                    "Sludge Wave",
                    "Psychic",
                    "Focus Blast",
                    "Fire Blast",
                ],
            },
            {
                "species": "Tyranitar",
                "item": "Tyranitarite",
                "ability": "Sand Stream",
                "nature": "Adamant",
                "evs": {"hp": 32, "atk": 32, "spd": 2},
                "moves": [
                    "Stone Edge",
                    "Knock Off",
                    "Superpower",
                    "Ice Punch",
                ],
            },
            {
                "species": "Rotom-Wash",
                "item": "Mystic Water",
                "ability": "Levitate",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 32},
                "moves": [
                    "Thunder",
                    "Hydro Pump",
                    "Dark Pulse",
                    "Volt Switch",
                ],
            },
            {
                "species": "Tinkaton",
                "item": "Never-Melt Ice",
                "ability": "Mold Breaker",
                "nature": "Adamant",
                "evs": {"hp": 29, "atk": 32, "spd": 5},
                "moves": [
                    "Gigaton Hammer",
                    "Play Rough",
                    "Ice Hammer",
                    "Knock Off",
                ],
            },
        ],
    },
    # ── Team 20: yumenonaka-r2100 ───────────────────────────────────────
    {
        "name": "yumenonaka-r2100",
        "pokemon": [
            {
                "species": "Volcarona",
                "item": "Sitrus Berry",
                "ability": "Flame Body",
                "nature": "Bold",
                "evs": {"hp": 23, "def": 32, "spe": 11},
                "moves": [
                    "Fiery Dance",
                    "Giga Drain",
                    "Morning Sun",
                    "Quiver Dance",
                ],
            },
            {
                "species": "Snorlax",
                "item": "Leftovers",
                "ability": "Thick Fat",
                "nature": "Impish",
                "evs": {"hp": 32, "atk": 2, "def": 32},
                "moves": ["Protect", "Earthquake", "Facade", "Yawn"],
            },
            {
                "species": "Venusaur",
                "item": "Venusaurite",
                "ability": "Chlorophyll",
                "nature": "Modest",
                "evs": {"hp": 32, "spa": 32, "def": 2},
                "moves": [
                    "Earth Power",
                    "Sludge Bomb",
                    "Synthesis",
                    "Leech Seed",
                ],
            },
            {
                "species": "Basculegion",
                "item": "Choice Scarf",
                "ability": "Adaptability",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "def": 2},
                "moves": [
                    "Wave Crash",
                    "Last Respects",
                    "Aqua Jet",
                    "Flip Turn",
                ],
            },
            {
                "species": "Clefable",
                "item": "Clefabirite",
                "ability": "Unaware",
                "nature": "Bold",
                "evs": {"hp": 32, "def": 11, "spa": 23},
                "moves": [
                    "Moonblast",
                    "Psyshock",
                    "Calm Mind",
                    "Moonlight",
                ],
            },
            {
                "species": "Garchomp",
                "item": "Focus Sash",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Outrage", "Earthquake", "Rock Tomb", "Stealth Rock"],
            },
        ],
    },
    # ── Team 21: chikuko ────────────────────────────────────────────────
    {
        "name": "chikuko",
        "pokemon": [
            {
                "species": "Garchomp",
                "item": "Choice Scarf",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Outrage", "Earthquake", "Fire Fang", "Poison Jab"],
            },
            {
                "species": "Froslass",
                "item": "Frostlasite",
                "ability": "Cursed Body",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": ["Blizzard", "Shadow Ball", "Aurora Veil", "Taunt"],
            },
            {
                "species": "Volcarona",
                "item": "Lum Berry",
                "ability": "Flame Body",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Flamethrower",
                    "Bug Buzz",
                    "Quiver Dance",
                    "Morning Sun",
                ],
            },
            {
                "species": "Azumarill",
                "item": "Sitrus Berry",
                "ability": "Huge Power",
                "nature": "Adamant",
                "evs": {"hp": 32, "atk": 32, "spe": 2},
                "moves": [
                    "Play Rough",
                    "Aqua Jet",
                    "Liquidation",
                    "Belly Drum",
                ],
            },
            {
                "species": "Glimmora",
                "item": "Focus Sash",
                "ability": "Toxic Debris",
                "nature": "Timid",
                "evs": {"spa": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Sludge Wave",
                    "Mud Shot",
                    "Mortal Spin",
                    "Stealth Rock",
                ],
            },
            {
                "species": "Kangaskhan",
                "item": "Kangaskhanite",
                "ability": "Scrappy",
                "nature": "Adamant",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": [
                    "Rock Slide",
                    "Ice Punch",
                    "Earthquake",
                    "Sucker Punch",
                ],
            },
        ],
    },
    # ── Team 22: garashi-r2100 ──────────────────────────────────────────
    {
        "name": "garashi-r2100",
        "pokemon": [
            {
                "species": "Garchomp",
                "item": "Choice Scarf",
                "ability": "Rough Skin",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 2},
                "moves": ["Outrage", "Earthquake", "Rock Slide", "Stealth Rock"],
            },
            {
                "species": "Gengar",
                "item": "Gengarite",
                "ability": "Cursed Body",
                "nature": "Bold",
                "evs": {"hp": 32, "def": 11, "spe": 23},
                "moves": ["Hex", "Sludge Bomb", "Protect", "Will-O-Wisp"],
            },
            {
                "species": "Umbreon",
                "item": "Leftovers",
                "ability": "Synchronize",
                "nature": "Calm",
                "evs": {"hp": 32, "def": 14, "spd": 20},
                "moves": ["Yawn", "Foul Play", "Wish", "Protect"],
            },
            {
                "species": "Corviknight",
                "item": "Sitrus Berry",
                "ability": "Pressure",
                "nature": "Impish",
                "evs": {"hp": 32, "def": 25, "spd": 9},
                "moves": ["Body Press", "Iron Defense", "Roost", "U-turn"],
            },
            {
                "species": "Lopunny",
                "item": "Lopunnite",
                "ability": "Cute Charm",
                "nature": "Jolly",
                "evs": {"atk": 32, "spe": 32, "hp": 1, "def": 1},
                "moves": [
                    "Fake Out",
                    "Close Combat",
                    "Triple Axel",
                    "U-turn",
                ],
            },
            {
                "species": "Primarina",
                "item": "Chesto Berry",
                "ability": "Torrent",
                "nature": "Bold",
                "evs": {"hp": 32, "def": 26, "spe": 8},
                "moves": ["Moonblast", "Surf", "Encore", "Rest"],
            },
        ],
    },
]


def pokemon_to_paste(mon: dict) -> str:
    """Convert a pokemon dict to Showdown paste format."""
    lines = []
    species = mon["species"]
    item = mon.get("item", "")
    if item:
        lines.append(f"{species} @ {item}")
    else:
        lines.append(species)

    lines.append(f"Ability: {mon['ability']}")

    evs = mon.get("evs", {})
    stat_order = [
        ("hp", "HP"),
        ("atk", "Atk"),
        ("def", "Def"),
        ("spa", "SpA"),
        ("spd", "SpD"),
        ("spe", "Spe"),
    ]
    ev_parts = []
    for stat, label in stat_order:
        val = evs.get(stat, 0)
        if val > 0:
            ev_parts.append(f"{val} {label}")
    if ev_parts:
        lines.append("EVs: " + " / ".join(ev_parts))

    lines.append(f"{mon['nature']} Nature")

    for move in mon["moves"]:
        lines.append(f"- {move}")

    return "\n".join(lines)


def team_to_paste(team: list[dict]) -> str:
    """Convert a list of pokemon dicts to Showdown paste format."""
    return "\n\n".join(pokemon_to_paste(mon) for mon in team)


def validate_species(species: str, pokedex: dict) -> bool:
    """Validate that a species exists in the pokedex."""
    # Normalize: lowercase, strip hyphens/spaces/apostrophes
    key = species.lower().replace(" ", "").replace("-", "").replace("'", "")

    # Aegislash-Shield → aegislash
    if "aegislash" in key:
        key = "aegislash"

    if key in pokedex:
        return True

    # Try base form (before first hyphen)
    base = species.split("-")[0].lower().replace(" ", "").replace("'", "")
    return base in pokedex


def main() -> None:
    """Generate team.txt files for all complete teams."""
    # Load pokedex for validation
    pokedex: dict = json.loads(POKEDEX_PATH.read_text())

    created = 0
    skipped = 0

    for team_data in TEAMS:
        slug = team_data["name"]
        team_dir = TEAMS_DIR / slug
        pokemon_list = team_data["pokemon"]

        # Validate all 6 pokemon have complete data
        incomplete = False
        for mon in pokemon_list:
            if not mon.get("species"):
                print(f"  SKIP (missing species): {slug}")
                incomplete = True
                break
            if not mon.get("ability"):
                print(f"  SKIP (missing ability for {mon['species']}): {slug}")
                incomplete = True
                break
            if not mon.get("item"):
                print(f"  SKIP (missing item for {mon['species']}): {slug}")
                incomplete = True
                break
            if len(mon.get("moves", [])) < 4:
                print(
                    f"  SKIP (incomplete moves for {mon['species']}): {slug}"
                )
                incomplete = True
                break

        if incomplete:
            skipped += 1
            continue

        # Validate species against pokedex
        for mon in pokemon_list:
            if not validate_species(mon["species"], pokedex):
                print(
                    f"  WARNING: {mon['species']} not found in pokedex"
                    f" (team {slug})"
                )

        # Skip if directory already exists
        if team_dir.exists():
            print(f"  SKIP (exists): {slug}")
            skipped += 1
            continue

        paste = team_to_paste(pokemon_list)

        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "team.txt").write_text(paste + "\n")
        created += 1
        print(f"  OK: {slug}")

    print(f"\nCreated {created} new teams, skipped {skipped}")
    print(f"Total teams: {len(list(TEAMS_DIR.glob('*/team.txt')))}")


if __name__ == "__main__":
    main()
