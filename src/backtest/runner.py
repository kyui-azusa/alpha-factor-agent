from __future__ import annotations

import pandas as pd

from src.backtest.metrics import ic_ir, long_short_return, quantile_returns, rank_ic, turnover
from src.config import CONFIG, Config
from src.factors.engine import FactorExpr, evaluate, expression_names
from src.utils.field_availability import validate_field_availability


def backtest(
    expr: FactorExpr,
    panel: pd.DataFrame,
    fwd_ret: pd.DataFrame | pd.Series,
    cfg: Config = CONFIG,
    forward_column: str = "fwd_ret_5",
    n_quantiles: int = 5,
) -> dict:
    ok, reason = validate_field_availability(expression_names(expr.expression) | set(expr.fields_used), panel)
    if not ok:
        raise ValueError(f"factor field availability check failed: {reason}")
    factor = evaluate(expr, panel)
    if isinstance(fwd_ret, pd.DataFrame):
        returns = fwd_ret[forward_column]
    else:
        returns = fwd_ret
    returns = returns.sort_index()

    train_end = pd.Timestamp(cfg.train_end)
    dates = factor.index.get_level_values("date")
    oos_factor = factor.loc[dates > train_end]
    oos_returns = returns.loc[returns.index.get_level_values("date") > train_end]

    ic = rank_ic(oos_factor, oos_returns)
    qret = quantile_returns(oos_factor, oos_returns, n=n_quantiles)
    ls = long_short_return(qret)
    turn = turnover(oos_factor, n=n_quantiles).reindex(ls.index).fillna(0.0)
    net = ls - turn * (cfg.cost_bps / 10000.0)
    net.name = "net_long_short"

    summary = {
        "name": expr.name,
        "start_date": str(oos_factor.index.get_level_values("date").min().date()) if len(oos_factor) else None,
        "end_date": str(oos_factor.index.get_level_values("date").max().date()) if len(oos_factor) else None,
        "train_end": cfg.train_end,
        "ic_mean": float(ic.mean()) if not ic.empty else float("nan"),
        "ic_ir": ic_ir(ic),
        "long_short_mean": float(ls.mean()) if not ls.empty else float("nan"),
        "turnover_mean": float(turn.mean()) if not turn.empty else float("nan"),
        "net_long_short_mean": float(net.mean()) if not net.empty else float("nan"),
        "observations": int(pd.concat([oos_factor.rename("factor"), oos_returns.rename("fwd_ret")], axis=1).dropna().shape[0]),
        "cost_bps": cfg.cost_bps,
    }
    return {
        "expr": expr.to_dict(),
        "summary": summary,
        "factor": factor,
        "rank_ic": ic,
        "quantile_returns": qret,
        "long_short": ls,
        "turnover": turn,
        "net_long_short": net,
    }
