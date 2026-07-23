from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


RUN_STATES = (
    "draft",
    "preflight_running",
    "awaiting_confirmation",
    "queued",
    "generating",
    "validating",
    "backtesting",
    "summarizing",
    "completed",
    "partial_completed",
    "failed",
    "canceled",
)
TERMINAL_STATES = frozenset({"completed", "partial_completed", "failed", "canceled"})
ERROR_CODES = frozenset({"timeout", "data_error", "pit_error", "expression_rejected", "system_error"})
ERROR_MESSAGES = {
    "timeout": "The stage exceeded its allowed execution time.",
    "data_error": "Required research data could not be loaded or validated.",
    "pit_error": "Point-in-time data validation failed; execution was blocked.",
    "expression_rejected": "The candidate expression did not pass deterministic validation.",
    "system_error": "An internal execution error interrupted the stage.",
}

_NEXT_STATES = {
    "draft": {"preflight_running"},
    "preflight_running": {"awaiting_confirmation"},
    "awaiting_confirmation": {"queued"},
    "queued": {"generating"},
    "generating": {"validating"},
    "validating": {"backtesting"},
    "backtesting": {"generating", "summarizing"},
    "summarizing": {"completed", "partial_completed"},
}
_STATE_STAGE = {
    "draft": "draft",
    "preflight_running": "preflight",
    "awaiting_confirmation": "confirmation",
    "queued": "queue",
    "generating": "generation",
    "validating": "validation",
    "backtesting": "backtest",
    "summarizing": "summary",
}
_STAGE_STATE = {stage: state for state, stage in _STATE_STAGE.items()}


class InvalidRunTransition(ValueError):
    """Raised when a run attempts to bypass the deterministic state machine."""


@dataclass(frozen=True)
class RetryResult:
    run_id: str
    source_run_id: str
    resumed_stage: str
    created_child: bool
    idempotent_replay: bool


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def input_fingerprint(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _decode(value: str | None, fallback: Any) -> Any:
    return json.loads(value) if value else fallback


class RunStore:
    """SQLite-backed research-run state, stage, candidate, and retry ledger."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    parent_run_id TEXT REFERENCES runs(run_id),
                    status TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    incomplete INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT
                );

                CREATE INDEX IF NOT EXISTS runs_request_id_idx ON runs(request_id, created_at);

                CREATE TABLE IF NOT EXISTS stage_attempts (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    stage TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    input_artifacts_json TEXT NOT NULL DEFAULT '{}',
                    output_artifacts_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    PRIMARY KEY (run_id, stage, attempt)
                );

                CREATE TABLE IF NOT EXISTS candidates (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    candidate_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    artifact_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT,
                    error_message TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, candidate_id)
                );

                CREATE TABLE IF NOT EXISTS retry_requests (
                    source_run_id TEXT NOT NULL REFERENCES runs(run_id),
                    idempotency_key TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    target_run_id TEXT NOT NULL REFERENCES runs(run_id),
                    resumed_stage TEXT NOT NULL,
                    created_child INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (source_run_id, idempotency_key)
                );
                """
            )

    def create_run(
        self,
        request_id: str,
        inputs: Mapping[str, Any],
        *,
        run_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or f"run_{uuid4().hex}"
        now = _utc_now()
        initial_state = "draft"
        stage = _STATE_STAGE[initial_state]
        payload = dict(inputs)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, request_id, parent_run_id, status, current_stage,
                    input_fingerprint, input_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    request_id,
                    parent_run_id,
                    initial_state,
                    stage,
                    input_fingerprint(payload),
                    _json(payload),
                    now,
                    now,
                ),
            )
            self._insert_stage(connection, run_id, stage, 1, "running", {}, now)
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run_id: {run_id}")
        return self._run_dict(row)

    def list_runs(self, *, request_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM runs"
        params: tuple[Any, ...] = ()
        if request_id is not None:
            query += " WHERE request_id = ?"
            params = (request_id,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._run_dict(row) for row in rows]

    def transition(
        self,
        run_id: str,
        target_state: str,
        *,
        output_artifacts: Mapping[str, Any] | None = None,
        input_artifacts: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._get_run_row(connection, run_id)
            current = row["status"]
            allowed = _NEXT_STATES.get(current, set())
            if target_state not in allowed:
                raise InvalidRunTransition(f"illegal run transition: {current} -> {target_state}")

            current_stage = row["current_stage"]
            self._finish_current_stage(connection, run_id, current_stage, "completed", output_artifacts or {}, now)
            artifacts = _decode(row["artifacts_json"], {})
            if output_artifacts:
                artifacts[current_stage] = dict(output_artifacts)

            if target_state in TERMINAL_STATES:
                connection.execute(
                    """
                    UPDATE runs SET status = ?, artifacts_json = ?, incomplete = ?,
                        updated_at = ?, ended_at = ? WHERE run_id = ?
                    """,
                    (target_state, _json(artifacts), int(target_state == "partial_completed"), now, now, run_id),
                )
            else:
                next_stage = _STATE_STAGE[target_state]
                connection.execute(
                    """
                    UPDATE runs SET status = ?, current_stage = ?, artifacts_json = ?,
                        updated_at = ? WHERE run_id = ?
                    """,
                    (target_state, next_stage, _json(artifacts), now, run_id),
                )
                attempt = self._next_attempt(connection, run_id, next_stage)
                self._insert_stage(connection, run_id, next_stage, attempt, "running", input_artifacts or {}, now)
        return self.get_run(run_id)

    def fail_run(self, run_id: str, error_code: str, message: str) -> dict[str, Any]:
        if error_code not in ERROR_CODES:
            raise ValueError(f"unsupported error code: {error_code}")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._get_run_row(connection, run_id)
            if row["status"] in TERMINAL_STATES:
                raise InvalidRunTransition(f"cannot fail terminal run in state {row['status']}")
            self._finish_current_stage(
                connection, run_id, row["current_stage"], "failed", {}, now, error_code=error_code, message=message
            )
            connection.execute(
                """
                UPDATE runs SET status = 'failed', error_code = ?, error_message = ?,
                    incomplete = 1, updated_at = ?, ended_at = ? WHERE run_id = ?
                """,
                (error_code, message, now, now, run_id),
            )
        return self.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._get_run_row(connection, run_id)
            if row["status"] in TERMINAL_STATES:
                if row["status"] == "canceled":
                    return self._run_dict(row)
                raise InvalidRunTransition(f"cannot cancel terminal run in state {row['status']}")
            self._finish_current_stage(connection, run_id, row["current_stage"], "canceled", {}, now)
            connection.execute(
                """
                UPDATE runs SET status = 'canceled', incomplete = 1,
                    updated_at = ?, ended_at = ? WHERE run_id = ?
                """,
                (now, now, run_id),
            )
        return self.get_run(run_id)

    def retry_failed(
        self,
        run_id: str,
        *,
        idempotency_key: str,
        inputs: Mapping[str, Any] | None = None,
    ) -> RetryResult:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = self._get_run_row(connection, run_id)
            payload = dict(inputs) if inputs is not None else _decode(source["input_json"], {})
            fingerprint = input_fingerprint(payload)
            existing = connection.execute(
                "SELECT * FROM retry_requests WHERE source_run_id = ? AND idempotency_key = ?",
                (run_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["input_fingerprint"] != fingerprint:
                    raise ValueError("idempotency_key was already used with different retry inputs")
                return RetryResult(
                    run_id=existing["target_run_id"],
                    source_run_id=run_id,
                    resumed_stage=existing["resumed_stage"],
                    created_child=bool(existing["created_child"]),
                    idempotent_replay=True,
                )

            if source["status"] != "failed":
                raise InvalidRunTransition("only failed runs can be retried")
            created_child = fingerprint != source["input_fingerprint"]

            if created_child:
                target_run_id = f"run_{uuid4().hex}"
                resumed_stage = "draft"
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, request_id, parent_run_id, status, current_stage,
                        input_fingerprint, input_json, artifacts_json, retry_count,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        target_run_id,
                        source["request_id"],
                        run_id,
                        "draft",
                        resumed_stage,
                        fingerprint,
                        _json(payload),
                        _json({}),
                        int(source["retry_count"]) + 1,
                        now,
                        now,
                    ),
                )
                self._insert_stage(connection, target_run_id, resumed_stage, 1, "running", {}, now)
            else:
                resumed_stage = source["current_stage"]
                target_run_id = run_id
                attempt = self._next_attempt(connection, run_id, resumed_stage)
                connection.execute(
                    """
                    UPDATE runs SET status = ?, error_code = NULL, error_message = NULL,
                        retry_count = retry_count + 1, ended_at = NULL, updated_at = ?
                    WHERE run_id = ?
                    """,
                    (_STAGE_STATE[resumed_stage], now, run_id),
                )
                self._insert_stage(connection, run_id, resumed_stage, attempt, "running", {}, now)

            connection.execute(
                """
                INSERT INTO retry_requests (
                    source_run_id, idempotency_key, input_fingerprint, target_run_id,
                    resumed_stage, created_child, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, idempotency_key, fingerprint, target_run_id, resumed_stage, int(created_child), now),
            )
        return RetryResult(target_run_id, run_id, resumed_stage, created_child, False)

    def upsert_candidate(
        self,
        run_id: str,
        candidate_id: str,
        status: str,
        *,
        artifact: Mapping[str, Any] | None = None,
        error_code: str | None = None,
        message: str | None = None,
    ) -> None:
        if status not in {"queued", "running", "completed", "failed", "canceled"}:
            raise ValueError(f"unsupported candidate status: {status}")
        if error_code is not None and error_code not in ERROR_CODES:
            raise ValueError(f"unsupported error code: {error_code}")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = self._get_run_row(connection, run_id)
            if run["status"] in TERMINAL_STATES:
                raise InvalidRunTransition(f"cannot update candidates after run is {run['status']}")
            connection.execute(
                """
                INSERT INTO candidates (
                    run_id, candidate_id, status, artifact_json, error_code, error_message, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, candidate_id) DO UPDATE SET
                    status = excluded.status,
                    artifact_json = excluded.artifact_json,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    updated_at = excluded.updated_at
                """,
                (run_id, candidate_id, status, _json(artifact or {}), error_code, message, _utc_now()),
            )

    def list_candidates(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM candidates WHERE run_id = ? ORDER BY candidate_id", (run_id,)
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "candidate_id": row["candidate_id"],
                "status": row["status"],
                "artifact": _decode(row["artifact_json"], {}),
                "error_code": row["error_code"],
                "error_message": row["error_message"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def finalize_from_candidates(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] != "summarizing":
            raise InvalidRunTransition("candidate finalization requires the summarizing state")
        candidates = self.list_candidates(run_id)
        succeeded = [item for item in candidates if item["status"] == "completed"]
        failed = [item for item in candidates if item["status"] == "failed"]
        if not candidates or any(item["status"] in {"queued", "running"} for item in candidates):
            raise InvalidRunTransition("all candidates must be terminal before finalization")
        if succeeded and failed:
            return self.transition(run_id, "partial_completed", output_artifacts={"candidates": candidates})
        if succeeded and not failed:
            return self.transition(run_id, "completed", output_artifacts={"candidates": candidates})
        return self.fail_run(run_id, "system_error", "no candidate completed successfully")

    def stage_attempts(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM stage_attempts WHERE run_id = ? ORDER BY started_at, attempt", (run_id,)
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "stage": row["stage"],
                "attempt": row["attempt"],
                "status": row["status"],
                "input_artifacts": _decode(row["input_artifacts_json"], {}),
                "output_artifacts": _decode(row["output_artifacts_json"], {}),
                "error_code": row["error_code"],
                "error_message": row["error_message"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "request_id": row["request_id"],
            "parent_run_id": row["parent_run_id"],
            "status": row["status"],
            "current_stage": row["current_stage"],
            "input_fingerprint": row["input_fingerprint"],
            "inputs": _decode(row["input_json"], {}),
            "artifacts": _decode(row["artifacts_json"], {}),
            "error_code": row["error_code"],
            "error_message": row["error_message"],
            "retry_count": row["retry_count"],
            "incomplete": bool(row["incomplete"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "ended_at": row["ended_at"],
        }

    @staticmethod
    def _get_run_row(connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown run_id: {run_id}")
        return row

    @staticmethod
    def _insert_stage(
        connection: sqlite3.Connection,
        run_id: str,
        stage: str,
        attempt: int,
        status: str,
        input_artifacts: Mapping[str, Any],
        started_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO stage_attempts (
                run_id, stage, attempt, status, input_artifacts_json, started_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, stage, attempt, status, _json(dict(input_artifacts)), started_at),
        )

    @staticmethod
    def _finish_current_stage(
        connection: sqlite3.Connection,
        run_id: str,
        stage: str,
        status: str,
        output_artifacts: Mapping[str, Any],
        ended_at: str,
        *,
        error_code: str | None = None,
        message: str | None = None,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE stage_attempts
            SET status = ?, output_artifacts_json = ?, error_code = ?, error_message = ?, ended_at = ?
            WHERE run_id = ? AND stage = ? AND ended_at IS NULL
            """,
            (status, _json(dict(output_artifacts)), error_code, message, ended_at, run_id, stage),
        )
        if cursor.rowcount != 1:
            raise InvalidRunTransition(f"run {run_id} has no active {stage} stage")

    @staticmethod
    def _next_attempt(connection: sqlite3.Connection, run_id: str, stage: str) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(attempt), 0) + 1 AS value FROM stage_attempts WHERE run_id = ? AND stage = ?",
            (run_id, stage),
        ).fetchone()
        return int(row["value"])
