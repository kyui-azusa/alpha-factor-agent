from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.mssql import (
    MSSQLConfig,
    available_odbc_drivers,
    check_tcp,
    export_query,
    list_columns,
    list_databases,
    list_tables,
    load_env_file,
    mask_identifier,
    mask_secret,
    sample_table,
    snapshot_metadata,
)


def _cfg() -> MSSQLConfig:
    return MSSQLConfig.from_env()


def cmd_doctor(_: argparse.Namespace) -> None:
    cfg = _cfg()
    tcp_ok, tcp_message = check_tcp(cfg)
    payload = {
        "host": cfg.host,
        "port": cfg.port,
        "database": cfg.database,
        "user": mask_identifier(cfg.user),
        "password": mask_secret(cfg.password),
        "driver": cfg.driver,
        "available_drivers": available_odbc_drivers(),
        "tcp_ok": tcp_ok,
        "tcp_message": tcp_message,
        "connection_string": cfg.connection_string(include_password=False, include_user=False),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_databases(_: argparse.Namespace) -> None:
    print(list_databases(_cfg()).to_string(index=False))


def cmd_tables(args: argparse.Namespace) -> None:
    print(list_tables(_cfg(), schema=args.schema).to_string(index=False))


def cmd_columns(args: argparse.Namespace) -> None:
    print(list_columns(args.table, cfg=_cfg(), schema=args.schema).to_string(index=False))


def cmd_sample(args: argparse.Namespace) -> None:
    print(sample_table(args.table, cfg=_cfg(), schema=args.schema, limit=args.limit).to_string(index=False))


def cmd_snapshot(args: argparse.Namespace) -> None:
    manifest = snapshot_metadata(
        args.output_dir,
        cfg=_cfg(),
        schema=args.schema,
        include_row_counts=args.row_counts,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    sql = args.sql or Path(args.sql_file).read_text(encoding="utf-8")
    output = export_query(sql, args.output, cfg=_cfg())
    print(output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reusable SQL Server helper for alpha-factor-agent.")
    parser.add_argument(
        "--env-file",
        help="Optional local env file such as config/mssql.env. Shell env vars take precedence.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Check env, ODBC drivers, and TCP reachability.")
    doctor.set_defaults(func=cmd_doctor)

    databases = sub.add_parser("databases", help="List accessible databases.")
    databases.set_defaults(func=cmd_databases)

    tables = sub.add_parser("tables", help="List tables in the selected database.")
    tables.add_argument("--schema", default=None)
    tables.set_defaults(func=cmd_tables)

    columns = sub.add_parser("columns", help="List columns for one table.")
    columns.add_argument("table")
    columns.add_argument("--schema", default="dbo")
    columns.set_defaults(func=cmd_columns)

    sample = sub.add_parser("sample", help="Print the first rows from one table.")
    sample.add_argument("table")
    sample.add_argument("--schema", default="dbo")
    sample.add_argument("--limit", type=int, default=20)
    sample.set_defaults(func=cmd_sample)

    snapshot = sub.add_parser("snapshot", help="Save database/table/column metadata for offline development.")
    snapshot.add_argument("--schema", default=None)
    snapshot.add_argument("--output-dir", default="data/metadata/mssql/latest")
    snapshot.add_argument("--row-counts", action="store_true", help="Also save approximate table row counts.")
    snapshot.set_defaults(func=cmd_snapshot)

    export = sub.add_parser("export", help="Export a SQL query to CSV/parquet/pkl.")
    source = export.add_mutually_exclusive_group(required=True)
    source.add_argument("--sql")
    source.add_argument("--sql-file")
    export.add_argument("--output", required=True)
    export.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.env_file:
        load_env_file(args.env_file)
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
