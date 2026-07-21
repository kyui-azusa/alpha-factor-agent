WITH a_share AS (
    SELECT DISTINCT
        CompanyCode,
        SecuCode,
        SecuMarket
    FROM dbo.SecuMain
    WHERE SecuCategory = 1
      AND SecuMarket IN (83, 90)
),
base AS (
    SELECT
        CONCAT(
            s.SecuCode,
            CASE
                WHEN s.SecuMarket = 90 THEN '.SZ'
                WHEN s.SecuMarket = 83 THEN '.SH'
            END
        ) AS code,
        CAST(f.EndDate AS date) AS report_period,
        CAST(f.InfoPublDate AS date) AS ann_date,
        CAST(f.TotalAssets AS float) AS total_assets,
        CAST(COALESCE(f.SEWithoutMI, f.TotalShareholderEquity) AS float) AS total_equity,
        CAST(COALESCE(f.NPFromParentCompanyOwners, f.NetProfit) AS float) AS net_income,
        CAST(f.OperatingReenue AS float) AS revenue,
        CAST(f.NetOperateCashFlow AS float) AS operating_cash_flow,
        CAST(f.TotalShares AS float) AS shares_outstanding,
        CAST(COALESCE(f.NAPSAdjusted, f.NAPS) AS float) AS book_value_per_share,
        CAST(COALESCE(f.EPS, f.BasicEPS, f.DilutedEPS) AS float) AS eps,
        ROW_NUMBER() OVER (
            PARTITION BY s.SecuCode, s.SecuMarket, f.EndDate, f.InfoPublDate
            ORDER BY f.InfoPublDate DESC, f.EndDate DESC, f.JSID DESC
        ) AS rn
    FROM a_share AS s
    INNER JOIN dbo.LC_MainDataNew AS f
        ON f.CompanyCode = s.CompanyCode
    WHERE f.InfoPublDate IS NOT NULL
      AND f.EndDate IS NOT NULL
      AND f.InfoPublDate <= '2021-12-31'
      AND f.EndDate >= '2018-01-01'
)
SELECT
    code,
    report_period,
    ann_date,
    total_assets,
    total_equity,
    net_income,
    revenue,
    operating_cash_flow,
    shares_outstanding,
    book_value_per_share,
    eps
FROM base
WHERE rn = 1;
