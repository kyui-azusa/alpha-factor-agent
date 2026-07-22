SELECT DISTINCT
    CAST(q.TradingDay AS date) AS [date],
    CONCAT(
        s.SecuCode,
        CASE
            WHEN s.SecuMarket = 90 THEN '.SZ'
            WHEN s.SecuMarket = 83 THEN '.SH'
        END
    ) AS code,
    CAST(1.0 AS float) AS weight
FROM dbo.QT_DailyQuote AS q
INNER JOIN dbo.SecuMain AS s
    ON q.InnerCode = s.InnerCode
WHERE s.SecuCategory = 1
  AND s.SecuMarket IN (83, 90)
  AND q.TradingDay >= '2015-01-01'
  AND q.TradingDay <= '2021-12-31'
  AND q.ClosePrice IS NOT NULL;
