# 聚源 SQL Server 内网接入脚本

本项目通过 `scripts/mssql_tool.py` 连接学校内网 SQL Server,用于探库、查看表结构、抽样和导出原始数据。真实账号、密码、主机地址只放在环境变量或本地 `config/mssql.env` 中,不要写进代码、论文、README 或聊天记录。

## 1. 准备环境

安装依赖:

```bash
pip install -r requirements.txt
```

如果本机没有 SQL Server ODBC Driver,先安装 Microsoft ODBC Driver 18。macOS 可用 Homebrew:

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18 mssql-tools18
```

## 2. 写本地配置

复制占位模板:

```bash
cp config/mssql.env.example config/mssql.env
```

然后把 `config/mssql.env` 改成学校内网给你的真实连接信息。这个文件已经在 `.gitignore` 中,不会被提交。

支持的变量:

| variable | meaning |
|---|---|
| `ALPHA_MSSQL_HOST` | SQL Server 主机或 IP。 |
| `ALPHA_MSSQL_PORT` | 端口,默认 `1433`。 |
| `ALPHA_MSSQL_DATABASE` | 默认数据库;探库时可以先留空,导出时建议指定。 |
| `ALPHA_MSSQL_USER` | 用户名。 |
| `ALPHA_MSSQL_PASSWORD` | 密码。 |
| `ALPHA_MSSQL_DRIVER` | ODBC 驱动名,默认 `ODBC Driver 18 for SQL Server`。 |
| `ALPHA_MSSQL_ENCRYPT` | 内网一般可用 `no`;如果服务器要求加密再改。 |
| `ALPHA_MSSQL_TRUST_SERVER_CERTIFICATE` | 内网自签证书常用 `yes`。 |
| `ALPHA_MSSQL_TIMEOUT` | TCP/连接超时秒数。 |

也可以不用文件,直接 `export ALPHA_MSSQL_...`。当 `--env-file` 和 shell 环境变量同时存在时,shell 环境变量优先。

## 3. 诊断连接

在学校内网执行:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env doctor
```

这个命令会输出脱敏后的用户名/密码、可用 ODBC drivers、TCP 是否可达。可以把输出发给我排查,但发之前仍建议确认没有真实密码;如果内网主机名或数据库名也不便公开,也先删掉。

## 4. 探库和探表

列出可访问数据库:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env databases
```

设置好 `ALPHA_MSSQL_DATABASE` 后列出表:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env tables
python scripts/mssql_tool.py --env-file config/mssql.env tables --schema dbo
```

查看某张表的字段:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env columns SomeTable --schema dbo
```

抽样看前几行:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env sample SomeTable --schema dbo --limit 5
```

## 5. 记录离线元信息快照

学校内网不一定随时可用,连上后先保存库表字段元信息。这个快照只记录库名、表名、字段名、字段类型等结构信息,不导出真实行情/财务数据。

```bash
python scripts/mssql_tool.py --env-file config/mssql.env snapshot \
  --output-dir data/metadata/mssql/latest
```

如果权限允许,可以补充系统视图里的近似行数,用于快速判断哪些表是主表:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env snapshot \
  --output-dir data/metadata/mssql/latest \
  --row-counts
```

输出文件:

| file | content |
|---|---|
| `databases.csv` | 可访问数据库清单。 |
| `tables.csv` | 当前数据库的表清单。 |
| `columns.csv` | 当前数据库的字段清单和类型。 |
| `manifest.json` | 快照时间、当前数据库、表数量、字段数量。 |
| `row_counts.csv` | 可选,近似行数。 |

项目最需要的字段优先级见 `docs/DATABASE_FIELD_PRIORITY.md`。

## 6. 导出给项目使用的数据

本项目最终需要对齐到 `docs/DATA_SCHEMA.md` 的三张原始表:

| output | purpose |
|---|---|
| `data/raw/prices.csv` | 日频复权行情、成交量成交额、市值、行业。 |
| `data/raw/fundamentals.csv` | 财务/估值字段,必须包含 `ann_date`。 |
| `data/raw/universe.csv` | 历史股票池,避免幸存者偏差。 |

还不知道聚源具体表名时,先用 `databases`、`tables`、`columns` 找到行情、财务公告日、成分股/股票池相关表。确认字段后,用 `export` 导出:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env export \
  --sql "SELECT TOP 100 * FROM dbo.SomePriceTable" \
  --output data/raw/sample_prices.csv
```

更建议把正式 SQL 写成文件,避免命令行太长:

```bash
python scripts/mssql_tool.py --env-file config/mssql.env export \
  --sql-file sql/export_prices.sql \
  --output data/raw/prices.csv
```

`--output` 支持 `.csv`、`.pkl`、`.parquet`。如果没有 parquet 依赖,脚本会自动退回同名 `.csv`。

## 7. 对本项目最关键的字段选择

行情表需要能得到 `date`、`code`、复权 `open/high/low/close`、`vol`、`amount`、`adj_factor`,最好有 `mktcap` 和 `industry`。

财务表最关键的是 `ann_date`:回测 T 日只能使用 `ann_date <= T` 的记录。不能用报告期 `report_period` 冒充公告日,否则会产生 look-ahead。

股票池表要按历史日期导出,不能只拿今天的成分股倒推历史。

## 8. 复用流程

以后每次换机器或换内网环境,只需要:

```bash
cp config/mssql.env.example config/mssql.env
python scripts/mssql_tool.py --env-file config/mssql.env doctor
python scripts/mssql_tool.py --env-file config/mssql.env tables
python scripts/mssql_tool.py --env-file config/mssql.env snapshot --output-dir data/metadata/mssql/latest
```

等你把可公开的数据库名、表名、字段名发回来后,下一步就可以把 `sql/export_prices.sql`、`sql/export_fundamentals.sql`、`sql/export_universe.sql` 三个正式导出脚本补齐。
