from __future__ import annotations
import asyncio
import typer
from pokechamp.battle import simulate_1v1
from pokechamp.loader import list_pokemon, list_teams, load_pokemon, load_team
from pokechamp.matchup import evaluate_matchup, build_battle_pokemon_from_team
from pokechamp.output import format_battle_result, format_matchup_result
from pokechamp.type_filter import analyze_team

app = typer.Typer(help="Pokemon Champions team builder & battle simulator")


def _resolve_pokemon(team_name: str, spec: str):
    """チームからポケモンを解決する。specはspecies名 or 0始まりインデックス."""
    team = load_team(team_name)
    bp_list = build_battle_pokemon_from_team(team)
    # インデックス指定
    if spec.isdigit():
        idx = int(spec)
        if idx >= len(bp_list):
            typer.echo(f"Error: index {idx} out of range (team has {len(bp_list)} pokemon)", err=True)
            raise typer.Exit(1)
        return bp_list[idx]
    # species名指定
    for bp in bp_list:
        if bp.name == spec:
            return bp
    typer.echo(f"Error: '{spec}' not found in team '{team_name}'", err=True)
    raise typer.Exit(1)


@app.command()
def battle(
    team_a: str = typer.Argument(help="チームA名"),
    pokemon_a: str = typer.Argument(help="ポケモンA (species名 or インデックス)"),
    vs: str = typer.Argument(help="'vs' (固定)"),
    team_b: str = typer.Argument(help="チームB名"),
    pokemon_b: str = typer.Argument(help="ポケモンB (species名 or インデックス)"),
    setup: str | None = typer.Option(None, help="積み技名"),
    setup_turns: int = typer.Option(1, help="積みターン数"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """1v1対面シミュレーション (チーム定義の型を使用)"""
    bp_a = _resolve_pokemon(team_a, pokemon_a)
    bp_b = _resolve_pokemon(team_b, pokemon_b)
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


@app.command()
def build(
    starter: str = typer.Argument(help="起点となるポケモンのspecies名 (name_en)"),
    members: list[str] = typer.Argument(default=None, help="既存チームメンバー (name_en, スペース区切り)"),
    top: int = typer.Option(10, help="表示件数"),
    evaluate: bool = typer.Option(False, "--evaluate", help="TOP候補をShowdownで精密評価"),
    eval_battles: int = typer.Option(3, "--eval-battles", help="評価対戦数"),
    json: bool = typer.Option(False, "--json", help="JSON出力"),
) -> None:
    """パーティ構築補助 — 弱点脅威の分析とカバー候補の提案。

    starter を起点に、type相性ベースで上位脅威と推奨追加ポケモンを表示する。

    例:
      pokechamp build garchomp
      pokechamp build garchomp corviknight primarina --top 5
      pokechamp build garchomp --evaluate --eval-battles 5
    """
    import json as json_mod

    team: list[str] = [starter]
    if members:
        team.extend(members)

    # Validate all species exist
    for species in team:
        try:
            load_pokemon(species)
        except FileNotFoundError:
            typer.echo(f"Error: pokemon '{species}' not found in data/pokemon/", err=True)
            raise typer.Exit(1)

    result = analyze_team(team, top_n=top)

    if json:
        typer.echo(json_mod.dumps(result, ensure_ascii=False, indent=2))
        return

    typer.echo("\n=== パーティ構築分析 ===")
    typer.echo(f"現在のチーム: {', '.join(team)}")

    typer.echo(f"\n--- 上位脅威 (Top {top}) ---")
    for rank, (species, score) in enumerate(result["top_threats"], 1):
        try:
            poke = load_pokemon(species)
            types_str = "/".join(t.value for t in poke.types)
            typer.echo(f"  {rank:2d}. {species:<20s} [{types_str}]  score={score:.2f}")
        except FileNotFoundError:
            typer.echo(f"  {rank:2d}. {species:<20s}  score={score:.2f}")

    typer.echo(f"\n--- 推奨追加候補 (Top {top}) ---")
    for rank, (species, score) in enumerate(result["suggested_additions"], 1):
        try:
            poke = load_pokemon(species)
            types_str = "/".join(t.value for t in poke.types)
            typer.echo(f"  {rank:2d}. {species:<20s} [{types_str}]  score={score:.2f}")
        except FileNotFoundError:
            typer.echo(f"  {rank:2d}. {species:<20s}  score={score:.2f}")

    if evaluate:
        from pokechamp.showdown_eval import evaluate_candidates

        typer.echo("\n--- Showdown精密評価中 ---")
        candidates = [s for s, _ in result["suggested_additions"][:5]]
        threats = [s for s, _ in result["top_threats"][:6]]

        eval_results = asyncio.run(
            evaluate_candidates(team, candidates, threats, n_battles=eval_battles)
        )

        typer.echo("\n--- 精密評価結果 ---")
        for i, r in enumerate(eval_results, 1):
            status = f"{r['win_rate'] * 100:.0f}%" if r["win_rate"] >= 0 else "ERROR"
            typer.echo(f"  {i}. {r['candidate']:<20s} 勝率: {status} ({r['battles']}戦)")
