"""Entry point for the hosting template.

The application itself lives in `src/api.py`; the deploy template always starts
`uvicorn app:app` from the live directory, so this module only re-exports it.
"""

from src.api import app  # noqa: F401
