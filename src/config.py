from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLORS = 4
MIN_COLORS = 1
MAX_COLORS = 16
VTRACER_BIN = PROJECT_ROOT / "bin" / "vtracer"
# Fallback to PATH if bundled binary missing
VTRACER_BIN_FALLBACK = "vtracer"
TRACE_TIMEOUT_SEC = 120
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
# VTracer defaults tuned for flat logos (poster-like)
VTRACER_FILTER_SPECKLE = 4
VTRACER_SEGMENT_LENGTH = 10  # px, subdivide splines until all segments < this
VTRACER_COLOR_PRECISION = 6
VTRACER_MODE = "spline"
VTRACER_HIERARCHICAL = "stacked"
