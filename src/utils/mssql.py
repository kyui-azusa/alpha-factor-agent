from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import socket
from typing import Iterable, Sequence

import pandas as pd


@dataclass(frozen=True)
class MSSQLConfig:
    host: str
    port: int = 1433
    database: str | None = None
    user: str | None = None
    password: str | None = None
    driver: str = "ODBC Driver 18 for SQL Server"
    encrypt: str = "no"
    trust_server_certificate: str = "yes"
    timeout: int = 10

    @classmethod
    def from_env(cls, prefix: str = "ALPHA_MSSQL_") -> "MSSQLConfig":
        host = os.getenv(f"{prefix}HOST")
        if not host:
            raise ValueError(f"{prefix}HOST is required")
        return cls(
            host=host,
            port=int(os.getenv(f"{prefix}PORT", "1433")),
            database=os.getenv(f"{prefix}DATABASE") or None,
            user=os.getenv(f"{prefix}USER") or None,
            password=os.getenv(f"{prefix}PASSWORD") or None,
            driver=os.getenv(f"{prefix}DRIVER", "ODBC Driver 18 for SQL Server"),
            encrypt=os.getenv(f"{prefix}ENCRYPT", "no"),
            trust_server_certificate=os.getenv(f"{prefix}TRUST_SERVER_CERTIFICATE", "yes"),
            timeout=int(os.getenv(f"{prefix}TIMEOUT", "10")),
        )

    def connection_string(self, include_password: bool = True, include_user: bool = True) -> str:
        parts = [
            f"DRIVER={{{self.driver}}}",
            f"SERVER={self.host},{self.port}",
            f"Encrypt={self.encrypt}",
            f"TrustServerCertificate={self.trust_server_certificate}",
            f"Connection Timeout={self.timeout}",
        ]
        if self.database:
            parts.append(f"DATABASE={self.database}")
        if self.user:
            parts.append(f"UID={self.user if include_user else mask_identifier(self.user)}")
        if self.password:
            parts.append(f"PWD={self.password if include_password else '***'}")
        return ";".join(parts)


def connect(cfg: MSSQLConfig | None = None):
    cfg = cfg or MSSQLConfig.from_env()
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError("pyodbc is required for SQL Server access. Install it with `pip install pyodbc`.") from exc
    return pyodbc.connect(cfg.connection_string(), autocommit=True)


def check_tcp(cfg: MSSQLConfig | None = None) -> tuple[bool, str]:
    cfg = cfg or MSSQLConfig.from_env()
    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout):
            return True, "tcp ok"
    except OSError as exc:
        return False, str(exc)


def available_odbc_drivers() -> list[str]:
    try:
        import pyodbc
    except ImportError:
        return []
    return list(pyodbc.drivers())


def load_env_file(path: str | Path, override: bool = False) -> dict[str, str]:
    """Load simple KEY=VALUE lines without adding a python-dotenv dependency."""
    env_path = Path(path)
    loaded: dict[str, str] = {}
    for line_no, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise ValueError(f"Invalid env line {line_no} in {env_path}: expected KEY=VALUE")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid env line {line_no} in {env_path}: empty key")
        value = shlex.split(raw_value, comments=False, posix=True)
        parsed = " ".join(value) if value else ""
        loaded[key] = parsed
        if override or key not in os.environ:
            os.environ[key] = parsed
    return loaded


def query_dataframe(sql: str, params: Sequence | None = None, cfg: MSSQLConfig | None = None) -> pd.DataFrame:
    with connect(cfg) as conn:
        return pd.read_sql_query(sql, conn, params=params)


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("SQL identifier must be a non-empty string")
    return f"[{identifier.replace(']', ']]')}]"


def list_databases(cfg: MSSQLConfig | None = None) -> pd.DataFrame:
    return query_dataframe("SELECT name FROM sys.databases ORDER BY name", cfg=cfg)


def current_database(cfg: MSSQLConfig | None = None) -> str:
    frame = query_dataframe("SELECT DB_NAME() AS database_name", cfg=cfg)
    if frame.empty:
        return ""
    return str(frame.loc[0, "database_name"])


def list_tables(cfg: MSSQLConfig | None = None, schema: str | None = None) -> pd.DataFrame:
    sql = """
    SELECT TABLE_SCHEMA AS table_schema, TABLE_NAME AS table_name, TABLE_TYPE AS table_type
    FROM INFORMATION_SCHEMA.TABLES
    WHERE (? IS NULL OR TABLE_SCHEMA = ?)
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """
    return query_dataframe(sql, params=[schema, schema], cfg=cfg)


def list_columns(table: str, cfg: MSSQLConfig | None = None, schema: str = "dbo") -> pd.DataFrame:
    sql = """
    SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type, IS_NULLABLE AS is_nullable
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
    ORDER BY ORDINAL_POSITION
    """
    return query_dataframe(sql, params=[schema, table], cfg=cfg)


def list_all_columns(cfg: MSSQLConfig | None = None, schema: str | None = None) -> pd.DataFrame:
    sql = """
    SELECT
        TABLE_SCHEMA AS table_schema,
        TABLE_NAME AS table_name,
        ORDINAL_POSITION AS ordinal_position,
        COLUMN_NAME AS column_name,
        DATA_TYPE AS data_type,
        IS_NULLABLE AS is_nullable,
        CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
        NUMERIC_PRECISION AS numeric_precision,
        NUMERIC_SCALE AS numeric_scale,
        DATETIME_PRECISION AS datetime_precision
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE (? IS NULL OR TABLE_SCHEMA = ?)
    ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
    """
    return query_dataframe(sql, params=[schema, schema], cfg=cfg)


def list_row_counts(cfg: MSSQLConfig | None = None, schema: str | None = None) -> pd.DataFrame:
    sql = """
    SELECT
        s.name AS table_schema,
        t.name AS table_name,
        SUM(p.row_count) AS row_count
    FROM sys.dm_db_partition_stats p
    JOIN sys.tables t ON p.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE p.index_id IN (0, 1)
      AND (? IS NULL OR s.name = ?)
    GROUP BY s.name, t.name
    ORDER BY s.name, t.name
    """
    return query_dataframe(sql, params=[schema, schema], cfg=cfg)


def sample_table(table: str, cfg: MSSQLConfig | None = None, schema: str = "dbo", limit: int = 20) -> pd.DataFrame:
    if limit <= 0:
        raise ValueError("limit must be positive")
    sql = f"SELECT TOP {int(limit)} * FROM {quote_identifier(schema)}.{quote_identifier(table)}"
    return query_dataframe(sql, cfg=cfg)


def export_query(sql: str, output: str | Path, cfg: MSSQLConfig | None = None, params: Iterable | None = None) -> Path:
    frame = query_dataframe(sql, params=list(params or []), cfg=cfg)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        try:
            frame.to_parquet(path, index=False)
        except (ImportError, ValueError):
            fallback = path.with_suffix(".csv")
            frame.to_csv(fallback, index=False)
            return fallback
    elif path.suffix == ".pkl":
        frame.to_pickle(path)
    else:
        frame.to_csv(path, index=False)
    return path


def snapshot_metadata(
    output_dir: str | Path,
    cfg: MSSQLConfig | None = None,
    schema: str | None = None,
    include_row_counts: bool = False,
) -> dict[str, str | int | bool | None]:
    cfg = cfg or MSSQLConfig.from_env()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    databases = list_databases(cfg)
    tables = list_tables(cfg, schema=schema)
    columns = list_all_columns(cfg, schema=schema)

    databases.to_csv(out / "databases.csv", index=False)
    tables.to_csv(out / "tables.csv", index=False)
    columns.to_csv(out / "columns.csv", index=False)

    row_count_error = None
    if include_row_counts:
        try:
            list_row_counts(cfg, schema=schema).to_csv(out / "row_counts.csv", index=False)
        except Exception as exc:  # pragma: no cover - depends on database permissions.
            row_count_error = str(exc)

    manifest: dict[str, str | int | bool | None] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": current_database(cfg),
        "schema_filter": schema,
        "table_count": int(len(tables)),
        "column_count": int(len(columns)),
        "database_count": int(len(databases)),
        "include_row_counts": include_row_counts,
        "row_count_error": row_count_error,
        "driver": cfg.driver,
        "user": mask_identifier(cfg.user),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return "***"


def mask_identifier(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "***"
    return f"{value[:1]}***{value[-1:]}"
