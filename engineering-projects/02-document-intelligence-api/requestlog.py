"""Per-request log of cost, latency and outcome.

This is the file that turns "it works" into "I know what it costs to run", which the
brief wants for pricing. Every request is written here, including the failures - a 422
still burned two model calls, and a cost figure that counts only successes understates
the real number.

SQLite, from the standard library. The Phase 5 admin page needs to aggregate (p95
latency, mean cost, retry rate) and a JSONL file would mean loading and parsing the
whole history to answer that. No new dependency either way.

One deployment caveat: on Render's default filesystem this database is ephemeral and
resets when the instance restarts. That is acceptable for the operational view the
admin page provides; it is not a system of record, and anything needed permanently
should be shipped off-box.
"""

import contextlib
import os
import pathlib
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Iterator

DB_PATH = pathlib.Path(os.environ.get("DOCINTEL_LOG_DB", "requests.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    client            TEXT    NOT NULL,
    endpoint          TEXT    NOT NULL,
    status_code       INTEGER NOT NULL,
    latency_ms        INTEGER NOT NULL,
    model_calls       INTEGER NOT NULL DEFAULT 0,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL,
    document_chars    INTEGER,
    fields_lowered    INTEGER,
    error_kind        TEXT,
    filename          TEXT
);
CREATE INDEX IF NOT EXISTS requests_timestamp ON requests (timestamp);
"""

_lock = threading.Lock()


@contextlib.contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.executescript(SCHEMA)


def log_request(
    *,
    client: str,
    endpoint: str,
    status_code: int,
    latency_ms: int,
    model_calls: int = 0,
    prompt_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float | None = None,
    document_chars: int | None = None,
    fields_lowered: int | None = None,
    error_kind: str | None = None,
    filename: str | None = None,
) -> None:
    """Write one row. Never raises.

    A logging failure must not turn a successful extraction into a 500 - the client's
    result is already computed and paid for. A dropped row is a worse metric; a dropped
    response is a worse product.
    """
    try:
        with _lock, _connect() as connection:
            connection.execute(
                """
                INSERT INTO requests (
                    timestamp, client, endpoint, status_code, latency_ms, model_calls,
                    prompt_tokens, output_tokens, cost_usd, document_chars,
                    fields_lowered, error_kind, filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    client,
                    endpoint,
                    status_code,
                    latency_ms,
                    model_calls,
                    prompt_tokens,
                    output_tokens,
                    cost_usd,
                    document_chars,
                    fields_lowered,
                    error_kind,
                    filename,
                ),
            )
    except Exception:  # noqa: BLE001 - see docstring
        pass


def recent(limit: int = 50) -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM requests ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def summary() -> dict:
    """Aggregates for the admin page and the README's results section."""
    with _connect() as connection:
        totals = connection.execute(
            """
            SELECT COUNT(*)                                        AS requests,
                   SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) AS succeeded,
                   SUM(cost_usd)                                   AS total_cost,
                   AVG(cost_usd)                                   AS mean_cost,
                   AVG(latency_ms)                                 AS mean_latency,
                   SUM(prompt_tokens + output_tokens)              AS total_tokens,
                   -- Two calls is the no-retry baseline: one extraction, one
                   -- cross-check. Anything above that means the retry fired.
                   SUM(CASE WHEN model_calls > 2 THEN 1 ELSE 0 END) AS retried,
                   SUM(CASE WHEN fields_lowered > 0 THEN 1 ELSE 0 END) AS with_lowered
            FROM requests
            """
        ).fetchone()
        # Percentiles over successful requests only. A 401 never reached the model and
        # returns in a millisecond; mixing those in would drag the latency a client
        # actually experiences down towards zero and flatter the number.
        latencies = [
            row["latency_ms"]
            for row in connection.execute(
                "SELECT latency_ms FROM requests WHERE status_code = 200 "
                "ORDER BY latency_ms"
            )
        ]
        statuses = [
            dict(row)
            for row in connection.execute(
                "SELECT status_code, COUNT(*) AS count FROM requests "
                "GROUP BY status_code ORDER BY status_code"
            )
        ]

    result = dict(totals) if totals else {}
    result["p95_latency_ms"] = _percentile(latencies, 95)
    result["p50_latency_ms"] = _percentile(latencies, 50)
    result["by_status"] = statuses
    # Sample size for the percentiles, so the page can decline to show a p95 that is
    # really just the slowest of four requests.
    result["latency_samples"] = len(latencies)
    return result


def _percentile(values: list[int], percentile: int) -> int | None:
    """Nearest-rank percentile. Exact on small samples, where interpolating between
    two of the four requests you have invents precision that is not there."""
    if not values:
        return None
    rank = max(1, -(-percentile * len(values) // 100))  # ceil
    return values[min(rank, len(values)) - 1]
