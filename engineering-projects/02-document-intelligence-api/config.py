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

def env(name: str, default: str = "") -> str:
    """Read a setting, treating blank as absent.

    os.environ.get returns "" for a variable that is set but empty, and empty is what a
    deployment dashboard field left blank, or a bare `KEY=` line in a .env file,
    actually produces. That empty string then travels on as if it were a real value: an
    empty model name reaches the API, an empty path resolves to a directory. Throughout
    this service, blank means "not configured" and the default applies.
    """
    return os.environ.get(name, "").strip() or default


def env_int(name: str, default: int) -> int:
    """Read a numeric setting. Blank or unparseable falls back to the default.

    A bad value must not be fatal at import time - a typo in one dashboard field should
    not stop the service from starting, when a sane default is right there.
    """
    raw = env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# The main pass and the cross-check pass are named separately even though they
# currently resolve to the same model. The second pass is "cheap" by virtue of a much
# smaller schema and prompt, not a smaller model - but keeping the names apart means
# swapping one without the other is a config change, not an edit.
#
# Read at import, so these follow real environment variables only. A value placed in
# .env cannot reach them: load_env() runs at application startup, after this module has
# already been imported and these names bound. Set the model in the environment proper.
MAIN_MODEL = env("DOCINTEL_MAIN_MODEL", "gemini-3.1-flash-lite")
SECOND_PASS_MODEL = env("DOCINTEL_SECOND_PASS_MODEL", MAIN_MODEL)

# Deterministic by default, and deterministic in practice: repeated identical requests
# at this temperature returned byte-identical confidence scores across three runs of
# every case measured.
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
