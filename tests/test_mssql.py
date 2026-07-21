from __future__ import annotations

import pandas as pd
import pytest

from src.utils import mssql
from src.utils.mssql import MSSQLConfig


ENV_KEYS = [
    "ALPHA_MSSQL_HOST",
    "ALPHA_MSSQL_PORT",
    "ALPHA_MSSQL_DATABASE",
    "ALPHA_MSSQL_USER",
    "ALPHA_MSSQL_PASSWORD",
    "ALPHA_MSSQL_DRIVER",
    "ALPHA_MSSQL_ENCRYPT",
    "ALPHA_MSSQL_TRUST_SERVER_CERTIFICATE",
    "ALPHA_MSSQL_TIMEOUT",
]


def test_mssql_config_from_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ALPHA_MSSQL_HOST", "db.intranet.local")
    monkeypatch.setenv("ALPHA_MSSQL_PORT", "11433")
    monkeypatch.setenv("ALPHA_MSSQL_DATABASE", "JYDB")
    monkeypatch.setenv("ALPHA_MSSQL_USER", "student_user")
    monkeypatch.setenv("ALPHA_MSSQL_PASSWORD", "secret-password")

    cfg = MSSQLConfig.from_env()

    assert cfg.host == "db.intranet.local"
    assert cfg.port == 11433
    assert cfg.database == "JYDB"
    assert cfg.user == "student_user"
    assert cfg.password == "secret-password"


def test_mssql_config_requires_host(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="ALPHA_MSSQL_HOST"):
        MSSQLConfig.from_env()


def test_connection_string_can_be_redacted():
    cfg = MSSQLConfig(
        host="db.intranet.local",
        database="JYDB",
        user="student_user",
        password="secret-password",
    )

    redacted = cfg.connection_string(include_password=False, include_user=False)

    assert "secret-password" not in redacted
    assert "student_user" not in redacted
    assert "PWD=***" in redacted
    assert "UID=s***r" in redacted


def test_mask_helpers():
    assert mssql.mask_secret(None) == ""
    assert mssql.mask_secret("abc") == "***"
    assert mssql.mask_secret("abcdef") == "***"
    assert mssql.mask_identifier("u") == "***"
    assert mssql.mask_identifier("student_user") == "s***r"


def test_load_env_file_respects_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / "mssql.env"
    env_file.write_text(
        "\n".join(
            [
                "# local SQL Server config",
                "export ALPHA_MSSQL_HOST=db.from.file",
                "ALPHA_MSSQL_DATABASE=JYDB",
                "ALPHA_MSSQL_DRIVER=ODBC Driver 18 for SQL Server",
                "ALPHA_MSSQL_PASSWORD='value with spaces'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ALPHA_MSSQL_HOST", "db.from.shell")

    loaded = mssql.load_env_file(env_file)

    assert loaded["ALPHA_MSSQL_HOST"] == "db.from.file"
    assert loaded["ALPHA_MSSQL_PASSWORD"] == "value with spaces"
    assert loaded["ALPHA_MSSQL_DRIVER"] == "ODBC Driver 18 for SQL Server"
    assert mssql.MSSQLConfig.from_env().host == "db.from.shell"
    assert mssql.MSSQLConfig.from_env().database == "JYDB"


def test_load_env_file_override(tmp_path, monkeypatch):
    env_file = tmp_path / "mssql.env"
    env_file.write_text("ALPHA_MSSQL_HOST=db.from.file\n", encoding="utf-8")
    monkeypatch.setenv("ALPHA_MSSQL_HOST", "db.from.shell")

    mssql.load_env_file(env_file, override=True)

    assert mssql.MSSQLConfig.from_env().host == "db.from.file"


def test_quote_identifier_and_sample_table(monkeypatch):
    captured = {}

    def fake_query_dataframe(sql, params=None, cfg=None):
        captured["sql"] = sql
        captured["params"] = params
        captured["cfg"] = cfg
        return pd.DataFrame({"ok": [1]})

    monkeypatch.setattr(mssql, "query_dataframe", fake_query_dataframe)
    cfg = MSSQLConfig(host="db.intranet.local")

    frame = mssql.sample_table("Daily]Quote", cfg=cfg, schema="dbo", limit=5)

    assert frame["ok"].tolist() == [1]
    assert captured["sql"] == "SELECT TOP 5 * FROM [dbo].[Daily]]Quote]"
    assert captured["cfg"] == cfg


def test_sample_table_requires_positive_limit():
    with pytest.raises(ValueError, match="limit"):
        mssql.sample_table("SomeTable", limit=0)


def test_snapshot_metadata_writes_offline_catalog(tmp_path, monkeypatch):
    cfg = MSSQLConfig(host="db.intranet.local", database="JYDB", user="student_user")

    monkeypatch.setattr(mssql, "list_databases", lambda cfg=None: pd.DataFrame({"name": ["JYDB"]}))
    monkeypatch.setattr(
        mssql,
        "list_tables",
        lambda cfg=None, schema=None: pd.DataFrame(
            {"table_schema": ["dbo"], "table_name": ["DailyQuote"], "table_type": ["BASE TABLE"]}
        ),
    )
    monkeypatch.setattr(
        mssql,
        "list_all_columns",
        lambda cfg=None, schema=None: pd.DataFrame(
            {
                "table_schema": ["dbo"],
                "table_name": ["DailyQuote"],
                "ordinal_position": [1],
                "column_name": ["ClosePrice"],
                "data_type": ["decimal"],
                "is_nullable": ["YES"],
                "character_maximum_length": [None],
                "numeric_precision": [18],
                "numeric_scale": [4],
                "datetime_precision": [None],
            }
        ),
    )
    monkeypatch.setattr(mssql, "current_database", lambda cfg=None: "JYDB")

    manifest = mssql.snapshot_metadata(tmp_path, cfg=cfg, schema="dbo")

    assert manifest["database"] == "JYDB"
    assert manifest["schema_filter"] == "dbo"
    assert manifest["table_count"] == 1
    assert manifest["column_count"] == 1
    assert manifest["user"] == "s***r"
    assert (tmp_path / "databases.csv").exists()
    assert (tmp_path / "tables.csv").exists()
    assert (tmp_path / "columns.csv").exists()
    assert (tmp_path / "manifest.json").exists()
    assert "DailyQuote" in (tmp_path / "tables.csv").read_text(encoding="utf-8")


def test_snapshot_metadata_can_write_row_counts(tmp_path, monkeypatch):
    cfg = MSSQLConfig(host="db.intranet.local")
    monkeypatch.setattr(mssql, "list_databases", lambda cfg=None: pd.DataFrame({"name": ["JYDB"]}))
    monkeypatch.setattr(mssql, "list_tables", lambda cfg=None, schema=None: pd.DataFrame({"table_name": ["T"]}))
    monkeypatch.setattr(mssql, "list_all_columns", lambda cfg=None, schema=None: pd.DataFrame({"column_name": ["C"]}))
    monkeypatch.setattr(mssql, "list_row_counts", lambda cfg=None, schema=None: pd.DataFrame({"row_count": [123]}))
    monkeypatch.setattr(mssql, "current_database", lambda cfg=None: "JYDB")

    manifest = mssql.snapshot_metadata(tmp_path, cfg=cfg, include_row_counts=True)

    assert manifest["include_row_counts"] is True
    assert manifest["row_count_error"] is None
    assert "123" in (tmp_path / "row_counts.csv").read_text(encoding="utf-8")
