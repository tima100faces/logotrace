from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from src.colors import COLORS_MODE_EXACT, COLORS_MODE_UP_TO
from src.config import DEFAULT_COLORS, MAX_COLORS, MIN_COLORS
from src.geometry import GEOM_BASIC, GEOM_OFF, GEOM_STRICT
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
        help="Ink palette size N (with --colors-mode)",
    ),
    colors_mode: str = typer.Option(
        COLORS_MODE_UP_TO,
        "--colors-mode",
        help="up_to=auto smart (default, may crush gradients); exact=manual K solids",
    ),
    fmt: str = typer.Option(
        "pdf",
        "--format",
        "-f",
        help="Output format: pdf (default) or svg (debug)",
    ),
    geom: str = typer.Option(
        GEOM_OFF,
        "--geom",
        "-g",
        help="Geometry normalize: off (default) | basic | strict (experimental)",
    ),
    upscale: bool = typer.Option(
        True,
        "--upscale/--no-upscale",
        help="Auto upscale before trace (default: on, v4 policy; --no-upscale for off)",
    ),
) -> None:
    """Convert a flat logo image to RGB vector PDF (SVG optional)."""
    fmt_l = fmt.lower().strip()
    if fmt_l not in ("pdf", "svg"):
        typer.secho("error: --format must be pdf or svg", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    cm = colors_mode.lower().strip()
    if cm not in (COLORS_MODE_UP_TO, COLORS_MODE_EXACT):
        typer.secho("error: --colors-mode must be up_to or exact", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    gl = geom.lower().strip()
    if gl not in (GEOM_OFF, GEOM_BASIC, GEOM_STRICT):
        typer.secho("error: --geom must be off|basic|strict", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    out = output
    if out is None:
        out = input.with_suffix(f".{fmt_l}")
    try:
        path = vectorize_file(
            input,
            colors=colors,
            colors_mode=cm,
            output_path=out,
            fmt=fmt_l,
            geom=gl,
            upscale=upscale,
        )
    except VectorizeError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(path))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
