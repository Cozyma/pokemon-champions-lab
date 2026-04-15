from __future__ import annotations
import typer
from pokechamp.battle import BattlePokemon, simulate_1v1
from pokechamp.loader import list_pokemon, list_teams, load_pokemon, load_team
from pokechamp.matchup import evaluate_matchup
from pokechamp.models import Nature
from pokechamp.output import format_battle_result, format_matchup_result

app = typer.Typer(help="Pokemon Champions team builder & battle simulator")

@app.command()
def battle(
    pokemon_a: str = typer.Argument(help="1体目のポケモン (species name)"),
    vs: str = typer.Argument(help="'vs' (固定)"),
    pokemon_b: str = typer.Argument(help="2体目のポケモン (species name)"),
    setup: str | None = typer.Option(None, help="積み技名"),
    setup_turns: int = typer.Option(1, help="積みターン数"),
    nature_a: str = typer.Option("hardy", help="ポケモンAの性格"),
    nature_b: str = typer.Option("hardy", help="ポケモンBの性格"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """1v1対面シミュレーション"""
    poke_a_data = load_pokemon(pokemon_a)
    poke_b_data = load_pokemon(pokemon_b)
    bp_a = BattlePokemon.from_data(
        species=pokemon_a, nature=Nature(nature_a),
        evs={}, ivs={}, item="",
        move_names=poke_a_data.learnable_moves[:4],
    )
    bp_b = BattlePokemon.from_data(
        species=pokemon_b, nature=Nature(nature_b),
        evs={}, ivs={}, item="",
        move_names=poke_b_data.learnable_moves[:4],
    )
    result = simulate_1v1(bp_a, bp_b, setup_move=setup, setup_turns=setup_turns if setup else 0)
    typer.echo(format_battle_result(result, as_json=json))

@app.command()
def matchup(
    team_a: str = typer.Argument(help="チームAのディレクトリ名"),
    vs: str = typer.Argument(help="'vs' (固定)"),
    team_b: str = typer.Argument(help="チームBのディレクトリ名"),
    with_setup: bool = typer.Option(False, "--with-setup", help="展開評価を含める"),
    matrix: bool = typer.Option(False, "--matrix", help="対面マトリクスのみ表示"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """構築マッチアップ評価"""
    result = evaluate_matchup(team_a, team_b, with_setup=with_setup)
    typer.echo(format_matchup_result(result, as_json=json))

@app.command("list")
def list_cmd(
    resource: str = typer.Argument(help="'pokemon' or 'teams'"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """登録済みポケモンまたはチーム一覧"""
    import json as json_mod
    if resource == "pokemon":
        items = list_pokemon()
    elif resource == "teams":
        items = list_teams()
    else:
        typer.echo(f"Unknown resource: {resource}. Use 'pokemon' or 'teams'.", err=True)
        raise typer.Exit(1)
    if json:
        typer.echo(json_mod.dumps(items, ensure_ascii=False, indent=2))
    else:
        for item in items:
            typer.echo(f"  {item}")

@app.command()
def show(
    pokemon: str = typer.Argument(help="ポケモン名 (name_en)"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """ポケモン詳細表示"""
    import json as json_mod
    poke = load_pokemon(pokemon)
    if json:
        typer.echo(json_mod.dumps(poke.model_dump(), ensure_ascii=False, indent=2))
    else:
        typer.echo(f"=== {poke.name} ({poke.name_en}) ===")
        typer.echo(f"タイプ: {', '.join(t.value for t in poke.types)}")
        typer.echo(f"種族値: H{poke.base_stats.hp} A{poke.base_stats.attack} B{poke.base_stats.defense} "
                    f"C{poke.base_stats.sp_attack} D{poke.base_stats.sp_defense} S{poke.base_stats.speed}")
        typer.echo(f"特性: {', '.join(poke.abilities)}")
        typer.echo(f"習得技: {', '.join(poke.learnable_moves)}")

@app.command("import")
def import_cmd(
    gen: int = typer.Option(9, help="世代番号"),
) -> None:
    """PokeAPIからデータインポート（未実装）"""
    typer.echo(f"PokeAPI import for gen {gen} is not yet implemented.")
    typer.echo("Use data/pokemon/*.yaml to add pokemon data manually.")
