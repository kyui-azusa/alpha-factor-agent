# Paper update round status

- Data source status: `raw data files present`
- MSSQL env file: `/Users/azusa/dev/研究/alpha-factor-agent/config/mssql.env` exists = `True`
- MSSQL env keys in current process: `none`

## Raw tables

| table | exists | rows | codes | date range | file |
|---|---:|---:|---:|---|---|
| prices | True | 1904369 | 4261 | 2020-01-02 to 2021-12-31 | `/Users/azusa/dev/研究/alpha-factor-agent/data/raw/prices.pkl` |
| fundamentals | True | 164881 | 5705 | 2018-04-04 to 2021-12-31 | `/Users/azusa/dev/研究/alpha-factor-agent/data/raw/fundamentals.csv` |
| universe | True | 1904369 | 4261 | 2020-01-02 to 2021-12-31 | `/Users/azusa/dev/研究/alpha-factor-agent/data/raw/universe.csv` |

## Result tables

- Baseline summary rows: `5`
- Candidate factor summary rows: `2`
