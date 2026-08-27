"""Runtime configuration and the shared Gemini client.

python-dotenv is not a dependency of this project, and .env here is a handful of
KEY=value lines, so it is parsed directly rather than pulling in a package to read
seven lines of text.
"""

import functools
import os
import pathlib
import re

from google.genai import Client

# The main pass and the cross-check pass are named separately even though they
# currently resolve to the same model. The second pass is "cheap" by virtue of a much
# smaller schema and prompt, not a smaller model - but keeping the names apart means
# swapping one without the other is a config change, not an edit.
MAIN_MODEL = os.environ.get("DOCINTEL_MAIN_MODEL", "gemini-3.1-flash-lite")
SECOND_PASS_MODEL = os.environ.get("DOCINTEL_SECOND_PASS_MODEL", MAIN_MODEL)

# Deterministic by default. Confirmed deterministic in practice during the Phase 3
# prompt trials: three repetitions of every cell returned byte-identical scores.
TEMPERATURE = 0.0


def load_env(path: str | pathlib.Path = ".env") -> None:
    """Populate os.environ from a .env file, without overriding a real env var."""
    env_path = pathlib.Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        if match := re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line):
            os.environ.setdefault(match.group(1), match.group(2).strip().strip("\"'"))


@functools.cache
def get_client() -> Client:
    """One client for the process. Cached: constructing it per request is waste."""
    load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to .env or the environment."
        )
    return Client(api_key=key)
