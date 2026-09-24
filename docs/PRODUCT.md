# PRODUCT — logotrace

## Why it exists

Logos arrive as flat rasters: a JPEG from a client, a screenshot from a website, a photo of a business
card. Turning one back into vector curves by hand is an hour of pen-tool work in Illustrator. LogoTrace
does it in seconds and hands back a file that is ready for print and for further editing.

## Who it is for

Tim's own prepress work first (20 years of print, Illustrator), and through him the same problem for
clients.

## What it is not

- **Not a general-purpose tracer.** Flat logos only, 1–8 flat inks. No photos, no gradients, no
  AI shape-fit.
- **Not a colour-management tool.** The output is RGB; CMYK conversion stays where it belongs, in the
  print workflow.
- **Not a service with accounts.** No upload history, no user profiles, no gallery.
- **Not a batch converter (yet).** One file in, one file out.

## What it must do

| Scenario | Expected result |
|---|---|
| Drop a JPEG/PNG of a flat logo | a PDF with clean vector paths and the measured flat colours |
| A logo with a lightness ramp inside one hue | one solid ink instead of stripes (gradient crush) |
| A logo on a coloured plate | the plate survives as the background; nothing turns white |
| A multi-colour label (bread label, sample_11) | every distinct ink survives — bordeaux stays apart from brown |
| Only one or two inks wanted | manual mode: `palette=1…16`, exact K by mass, no crush |
| Logo with fine type | outlines stay readable at print size; the self-check refuses blank output |

## Quality bar

Area-weighted IoU of the output masks against the source (`src/eval.py`), baseline recorded in
`docs/EVAL-BASELINE.md`. The bar is "prints clean", not "maximally similar pixels": tiny accent masks
with a low IoU are allowed to lose a little, geometry that facets a curve is not.

## Constraints

- Runs on a small VPS, no GPU, cheap CPU; a logo is expected in seconds, not minutes.
- Runtime dependencies: the system `python3`, `librsvg2-bin`, and a virtualenv with the Python stack —
  the VTracer binary is bundled in `bin/`.
- Nothing leaves the machine: the raster is processed locally, no external API is called.
