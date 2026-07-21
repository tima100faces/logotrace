from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from src.config import DEFAULT_COLORS, MAX_COLORS, MIN_COLORS
from src.pipeline import VectorizeError, vectorize_file

app = typer.Typer(add_completion=False, no_args_is_help=True, help="LogoTrace — flat logo to PDF")


@app.command()
def main(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="Input raster (JPEG/PNG)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output path (.pdf default)"),
    colors: int = typer.Option(
        DEFAULT_COLORS,
        "--colors",
        "-c",
        min=MIN_COLORS,
        max=MAX_COLORS,
        help="Max logo palette size (up to N ink colors, bg excluded)",
    ),
    fmt: str = typer.Option(
        "pdf",
        "--format",
        "-f",
        help="Output format: pdf (default) or svg (debug)",
    ),
) -> None:
    """Convert a flat logo image to RGB vector PDF (SVG optional)."""
    fmt_l = fmt.lower().strip()
    if fmt_l not in ("pdf", "svg"):
        typer.secho("error: --format must be pdf or svg", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    out = output
    if out is None:
        out = input.with_suffix(f".{fmt_l}")
    try:
        path = vectorize_file(input, colors=colors, output_path=out, fmt=fmt_l)
    except VectorizeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(path))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
