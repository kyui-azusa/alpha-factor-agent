-- 日行情。**不含复权因子** —— adj_factor 由 sql/export_adj_factors.sql 单独导出,
-- 在 Python 侧用 merge_asof 按 ex_date 前向填充(见 src/utils/data_loader.py)。
-- 曾试过在本查询里用 OUTER APPLY 关联 QT_AdjustingFactor 取最近一条因子,
-- 580 万行跑了 16 分钟未出结果(关联列无合适索引);而因子表本身只有 3.8 万行,
-- 单独导出 4 秒完成。拆开导 + 本地 asof 合并是正确解法。
SELECT
    CAST(q.TradingDay AS date) AS [date],
    CONCAT(
        s.SecuCode,
        CASE
            WHEN s.SecuMarket = 90 THEN '.SZ'
            WHEN s.SecuMarket = 83 THEN '.SH'
        END
    ) AS code,
    CAST(q.OpenPrice AS float) AS [open],
    CAST(q.HighPrice AS float) AS high,
    CAST(q.LowPrice AS float) AS low,
    CAST(q.ClosePrice AS float) AS [close],
    CAST(q.TurnoverVolume AS float) AS vol,
    CAST(q.TurnoverValue AS float) AS amount
FROM dbo.QT_DailyQuote AS q
INNER JOIN dbo.SecuMain AS s
    ON q.InnerCode = s.InnerCode
WHERE s.SecuCategory = 1
  AND s.SecuMarket IN (83, 90)
  AND q.TradingDay >= '2015-01-01'
  AND q.TradingDay <= '2021-12-31'
  AND q.ClosePrice IS NOT NULL;
