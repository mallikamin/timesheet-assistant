"""
Append-only interaction log for fine-tuning + analytics.

Captures every meaningful user/AI interaction so we can later:
- Measure quality (approve/edit/delete rates per user, per project, per model)
- Build a fine-tuning corpus from confirmed-correct entries
- Diagnose regressions when prompt or model changes

Storage: JSONL at `poc/data/training_log.jsonl`. One JSON record per line, append-only.
The schema mirrors the Postgres table this should land in once the VPS migration
happens — at that point the loader is a 20-line script, no shape change needed.

Postgres migration target:

    CREATE TABLE chat_interactions (
        id            UUID PRIMARY KEY,
        ts            TIMESTAMPTZ NOT NULL,
        user_email    TEXT NOT NULL,
        user_name     TEXT,
        kind          TEXT NOT NULL,                    -- chat | weekly_categorize | categorize_correction | approve | edit | delete
        input         JSONB NOT NULL,
        context       JSONB DEFAULT '{}'::jsonb,
        output        JSONB NOT NULL,
        metrics       JSONB DEFAULT '{}'::jsonb,
        related_id    UUID                              -- links e.g. an approve event back to the chat interaction that produced it
    );
    CREATE INDEX ix_chat_user        ON chat_interactions (user_email);
    CREATE INDEX ix_chat_kind_ts     ON chat_interactions (kind, ts DESC);
    CREATE INDEX ix_chat_related     ON chat_interactions (related_id);

Privacy: we store user-typed chat messages (they originated from the user, this
is their own input) and calendar event metadata (the user explicitly clicked
"pull my calendar"). We do NOT store email body content — only metadata, per
the Australian Privacy Act 1988 architecture commitment.
"""

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_DATA_DIR = Path(__file__).resolve().parent / "data"
_LOG_PATH = _DATA_DIR / "training_log.jsonl"
_lock = threading.Lock()


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _hash_prompt(blocks: Any) -> str:
    """Stable short hash of the system prompt — lets us correlate prompt
    versions across thousands of interactions without storing the full text
    every time."""
    try:
        text = json.dumps(blocks, sort_keys=True) if not isinstance(blocks, str) else blocks
    except (TypeError, ValueError):
        text = str(blocks)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _serializable(obj: Any) -> Any:
    """Make Anthropic SDK objects JSON-serializable. Handles common types and
    falls back to repr for anything weird so the log never crashes."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    if hasattr(obj, "model_dump"):  # pydantic v2
        try:
            return _serializable(obj.model_dump())
        except Exception:
            pass
    if hasattr(obj, "dict"):  # pydantic v1 / similar
        try:
            return _serializable(obj.dict())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return _serializable(vars(obj))
    return repr(obj)


def log(
    *,
    kind: str,
    user_email: str,
    user_name: str = "",
    input_payload: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    output: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    related_id: Optional[str] = None,
) -> str:
    """Append one interaction to the log. Returns the row's id so a follow-up
    event (e.g. an approve) can reference it via `related_id`."""
    interaction_id = str(uuid.uuid4())
    record = {
        "id": interaction_id,
        "ts": _now(),
        "user_email": (user_email or "").lower().strip(),
        "user_name": user_name or "",
        "kind": kind,
        "input": _serializable(input_payload or {}),
        "context": _serializable(context or {}),
        "output": _serializable(output or {}),
        "metrics": _serializable(metrics or {}),
        "related_id": related_id,
    }
    try:
        _ensure_dir()
        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            with _LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as e:
        # Never crash the request because logging failed
        print(f"[WARN] training_log.log failed: {e}")

    # Mirror to Google Sheets ChatLog tab so the record survives Render's
    # ephemeral filesystem (free tier wipes data/ on every deploy/restart).
    # Imported lazily to avoid pulling gspread + service-account creds into
    # processes that don't have Sheets configured.
    try:
        import sheets_sync
        sheets_sync.log_chat_to_sheet(record)
    except Exception as e:
        print(f"[WARN] training_log -> sheets mirror failed: {e}")

    return interaction_id


def usage_metrics(response: Any) -> Dict[str, Any]:
    """Pull token counts off an Anthropic SDK response. Returns {} if the
    response has no usage attribute (e.g. a streamed mock)."""
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
    }


def prompt_signature(system_blocks: Any) -> str:
    """Public: short hash for use in the `context.system_prompt_hash` field."""
    return _hash_prompt(system_blocks)


def export_for_postgres(out_path: Optional[str] = None, limit: Optional[int] = None) -> str:
    """Generate a SQL INSERT script for migrating the JSONL log to Postgres.
    Use `limit` for a sample run before bulk loading."""
    if not _LOG_PATH.exists():
        return "-- training_log.jsonl is empty.\n"

    sql_parts = [
        "-- Generated by training_log.export_for_postgres()",
        "-- Run after CREATE TABLE chat_interactions (see file docstring).",
        "BEGIN;",
    ]
    rows = 0
    with _LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            cols = ["id", "ts", "user_email", "user_name", "kind", "input", "context", "output", "metrics", "related_id"]
            vals = [
                _sql_str(rec.get("id", str(uuid.uuid4()))),
                _sql_str(rec.get("ts", _now())),
                _sql_str(rec.get("user_email", "")),
                _sql_str(rec.get("user_name", "")),
                _sql_str(rec.get("kind", "unknown")),
                _sql_jsonb(rec.get("input", {})),
                _sql_jsonb(rec.get("context", {})),
                _sql_jsonb(rec.get("output", {})),
                _sql_jsonb(rec.get("metrics", {})),
                "NULL" if not rec.get("related_id") else _sql_str(rec["related_id"]),
            ]
            sql_parts.append(
                f"INSERT INTO chat_interactions ({', '.join(cols)}) VALUES "
                f"({', '.join(vals)}) ON CONFLICT (id) DO NOTHING;"
            )
            rows += 1
            if limit and rows >= limit:
                break
    sql_parts.append("COMMIT;")
    sql = "\n".join(sql_parts)
    if out_path:
        Path(out_path).write_text(sql, encoding="utf-8")
    return sql


def _sql_str(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _sql_jsonb(obj: Any) -> str:
    return _sql_str(json.dumps(obj, ensure_ascii=False)) + "::jsonb"
