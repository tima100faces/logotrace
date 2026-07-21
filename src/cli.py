from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from src.config import DEFAULT_COLORS, MAX_COLORS, MIN_COLORS
from src.pipeline import VectorizeError, vectorize_file

app = typer.Typer(add_completion=False, no_args_is_help=True, help="LogoTrace — flat logo to SVG")


@app.command()
def main(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="Input raster"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output SVG path"),
    colors: int = typer.Option(
        DEFAULT_COLORS,
        "--colors",
        "-c",
        min=MIN_COLORS,
        max=MAX_COLORS,
        help="Max palette size (up to N colors)",
    ),
) -> None:
    """Convert a flat logo image to SVG."""
    out = output
    if out is None:
        out = input.with_suffix(".svg")
    try:
        vectorize_file(input, colors=colors, output_path=out)
    except VectorizeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(out))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
