-- 复权因子的**事件记录**:每次除权除息一行,自 ex_date 起生效。
-- 展开到每个交易日由 Python 侧 merge_asof(direction="backward")完成,
-- 不要在 SQL 里用 OUTER APPLY 关联日行情 —— 见 sql/export_prices.sql 的说明。
SELECT
    CONCAT(
        s.SecuCode,
        CASE
            WHEN s.SecuMarket = 90 THEN '.SZ'
            WHEN s.SecuMarket = 83 THEN '.SH'
        END
    ) AS code,
    CAST(f.ExDiviDate AS date) AS ex_date,
    CAST(f.RatioAdjustingFactor AS float) AS adj_factor
FROM dbo.QT_AdjustingFactor AS f
INNER JOIN dbo.SecuMain AS s
    ON s.InnerCode = f.InnerCode
WHERE s.SecuCategory = 1
  AND s.SecuMarket IN (83, 90)
  AND f.ExDiviDate <= '2021-12-31';
