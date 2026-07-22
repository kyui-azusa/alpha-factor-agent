-- 申万一级行业(Standard = 38)的**变更记录**,不是快照。
-- 每行是一次分类生效:info_publ_date 起生效,cancel_date 起失效(NULL = 至今有效)。
-- 必须在 Python 侧按 PIT 展开(date 落在 [info_publ_date, cancel_date) 内才可用),
-- 直接拿最新一版回填历史属于 look-ahead。
SELECT
    CONCAT(
        s.SecuCode,
        CASE
            WHEN s.SecuMarket = 90 THEN '.SZ'
            WHEN s.SecuMarket = 83 THEN '.SH'
        END
    ) AS code,
    CAST(i.InfoPublDate AS date) AS info_publ_date,
    CAST(i.CancelDate AS date) AS cancel_date,
    i.FirstIndustryName AS industry
FROM dbo.LC_ExgIndustry AS i
INNER JOIN (
    SELECT DISTINCT CompanyCode, SecuCode, SecuMarket
    FROM dbo.SecuMain
    WHERE SecuCategory = 1 AND SecuMarket IN (83, 90)
) AS s
    ON i.CompanyCode = s.CompanyCode
WHERE i.Standard = 38
  AND i.FirstIndustryName IS NOT NULL
  AND i.InfoPublDate <= '2021-12-31';
