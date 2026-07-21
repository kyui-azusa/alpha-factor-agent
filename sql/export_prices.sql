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
    CAST(q.TurnoverValue AS float) AS amount,
    CAST(1.0 AS float) AS adj_factor
FROM dbo.QT_DailyQuote AS q
INNER JOIN dbo.SecuMain AS s
    ON q.InnerCode = s.InnerCode
WHERE s.SecuCategory = 1
  AND s.SecuMarket IN (83, 90)
  AND q.TradingDay >= '2020-01-01'
  AND q.TradingDay <= '2021-12-31'
  AND q.ClosePrice IS NOT NULL;
