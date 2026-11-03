"""Open interest positioning by strike from a parsed Deribit chain."""

import numpy as np
import pandas as pd


def open_interest_by_strike(chain: pd.DataFrame, expiries=None) -> pd.DataFrame:
    """Sum open interest (BTC) by strike, separately for Calls and Puts.

    ``expiries`` is a list of ``tau`` values; ``None`` means All expiries.
    A strike with no contract of one type has zero OI for that type; a
    contract with missing OI makes its strike/type sum NaN, never zero.
    """
    rows = chain if expiries is None else chain[chain["tau"].isin(list(expiries))]
    grouped = rows.groupby(["strike", "flag"])["open_interest"].agg(
        total="sum", known="count", contracts="size"
    )
    totals = grouped["total"].where(grouped["known"] == grouped["contracts"])
    table = totals.unstack("flag").reindex(columns=["call", "put"])
    absent = grouped["contracts"].unstack("flag").reindex(columns=["call", "put"]).isna()
    table = table.mask(absent, 0.0)
    return pd.DataFrame({
        "strike": table.index.to_numpy(dtype=float),
        "call_oi": table["call"].to_numpy(dtype=float),
        "put_oi": table["put"].to_numpy(dtype=float),
    })


NEAR_SPOT_FRACTION = 0.10
# Absorbs float error so a strike exactly at the ±10% boundary stays inside.
_BOUNDARY_RTOL = 1e-9


def near_spot_range(index_price: float) -> tuple[float, float]:
    """Return the default Near spot strike range: ±10% of the index."""
    return (
        index_price * (1 - NEAR_SPOT_FRACTION),
        index_price * (1 + NEAR_SPOT_FRACTION),
    )


def strikes_in_range(table: pd.DataFrame, strike_range) -> pd.DataFrame:
    """Return the rows whose strike lies in ``strike_range``, both ends included.

    The range is a display zoom: the input table is not changed.
    """
    low, high = strike_range
    strikes = table["strike"]
    inside = (strikes >= low * (1 - _BOUNDARY_RTOL)) & (
        strikes <= high * (1 + _BOUNDARY_RTOL)
    )
    return table.loc[inside].reset_index(drop=True)


def expiry_scope_label(chain: pd.DataFrame, expiries=None) -> str:
    """Name the OI expiry scope: All expiries or the selected UTC dates."""
    if expiries is None:
        return "All expiries"
    dates = (
        chain.loc[chain["tau"].isin(list(expiries))]
        .drop_duplicates("tau")
        .sort_values("tau")["expiry_dt"]
    )
    return ", ".join(pd.Timestamp(date).strftime("%Y-%m-%d") for date in dates)


def contract_gamma(strike, tau, mark_iv, forward, index_price):
    """Spot gamma of an inverse option's USD value, per USD of index move.

    Deribit values the option with undiscounted Black-76 on its reported
    forward ``F`` and converts the BTC premium to USD with the index ``X``:
    ``V = X / F * Black76(F, K, sigma, T)``. Moving ``X`` and every forward by
    the same factor gives ``d2V/dX2 = phi(d1) / (X * sigma * sqrt(T))`` with
    ``d1`` on ``F``. Deribit's ticker gamma is per USD of ``F``: multiply this
    by ``X / F`` to compare. ``mark_iv`` is a decimal. Missing inputs give NaN.
    """
    strike, tau, sigma, forward, index_price = (
        np.asarray(value, dtype=float)
        for value in (strike, tau, mark_iv, forward, index_price)
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        root_t = sigma * np.sqrt(tau)
        d1 = (np.log(forward / strike) + 0.5 * root_t**2) / root_t
        gamma = np.exp(-0.5 * d1**2) / np.sqrt(2 * np.pi) / (index_price * root_t)
        valid = (tau > 0) & (sigma > 0) & (strike > 0) & (forward > 0) & (index_price > 0)
    gamma = np.where(valid, gamma, np.nan)
    return gamma.item() if gamma.ndim == 0 else gamma


# Dealer sign per option type: customer sells -> dealer long gamma (+1),
# customer buys -> dealer short gamma (-1). Default: Call+ / Put-.
DEFAULT_SIGNS = {"call": 1, "put": -1}
GEX_MOVE = 0.01


def assumption_label(signs=None) -> str:
    """Name the active customer-side assumption.

    The default reads ``Call+ / Put− (Calls customer sells, Puts customer buys)``.
    """
    signs = DEFAULT_SIGNS if signs is None else signs
    mark = {1: "+", -1: "−"}
    side = {1: "sells", -1: "buys"}
    return (
        f"Call{mark[signs['call']]} / Put{mark[signs['put']]} "
        f"(Calls customer {side[signs['call']]}, Puts customer {side[signs['put']]})"
    )


def gex_contributions(chain: pd.DataFrame, signs=None) -> pd.DataFrame:
    """Per-contract GEX in USD per 1% BTC move: ``s * gamma * OI * X^2 * 0.01``.

    Gamma always comes from the contract's own ``tau`` and Exchange mark IV
    (``mark_iv``) on its reported forward; ``s`` is +1 where the customer
    sells and -1 where the customer buys. Missing inputs give NaN.
    """
    signs = DEFAULT_SIGNS if signs is None else signs
    index_price = chain["index_price"].to_numpy(dtype=float)
    gamma = contract_gamma(
        chain["strike"], chain["tau"], chain["mark_iv"],
        chain["underlying_price"], index_price,
    )
    sign = chain["flag"].map(signs).to_numpy(dtype=float)
    open_interest = chain["open_interest"].to_numpy(dtype=float)
    contribution = sign * gamma * open_interest * index_price**2 * GEX_MOVE
    return pd.DataFrame({
        "symbol": chain["symbol"].to_numpy(),
        "flag": chain["flag"].to_numpy(),
        "strike": chain["strike"].to_numpy(dtype=float),
        "tau": chain["tau"].to_numpy(dtype=float),
        "open_interest": open_interest,
        "gamma": gamma,
        "contribution": contribution,
    })


def _in_expiries(chain, expiries):
    return chain if expiries is None else chain[chain["tau"].isin(list(expiries))]


def _complete_sum(values: pd.Series) -> float:
    return float(values.sum()) if values.notna().all() else np.nan


def net_gex_by_strike(chain: pd.DataFrame, expiries=None, signs=None) -> pd.DataFrame:
    """Sum signed GEX contributions by strike (Net), USD per 1% BTC move.

    Calls and Puts can cancel. ``call_gex``/``put_gex`` are the per-type
    subtotals and ``call_oi``/``put_oi`` the strike's OI in BTC. A strike with
    any non-computable contract gets NaN, never a partial sum.
    """
    rows = gex_contributions(_in_expiries(chain, expiries), signs)
    records = []
    for strike, group in rows.groupby("strike", sort=True):
        by_type = {flag: group[group["flag"] == flag] for flag in ("call", "put")}
        records.append({
            "strike": float(strike),
            "net_gex": _complete_sum(group["contribution"]),
            "call_gex": _complete_sum(by_type["call"]["contribution"]),
            "put_gex": _complete_sum(by_type["put"]["contribution"]),
            "call_oi": _complete_sum(by_type["call"]["open_interest"]),
            "put_oi": _complete_sum(by_type["put"]["open_interest"]),
            "contracts": len(group),
        })
    columns = ["strike", "net_gex", "call_gex", "put_gex", "call_oi", "put_oi", "contracts"]
    return pd.DataFrame(records, columns=columns)


def computable_oi_share(chain: pd.DataFrame, expiries=None) -> float:
    """Share of OI (BTC) whose GEX contribution is computable.

    NaN when any OI in scope is missing or the total is zero.
    """
    rows = gex_contributions(_in_expiries(chain, expiries))
    total = _complete_sum(rows["open_interest"])
    if not total > 0:
        return np.nan
    return float(rows.loc[rows["contribution"].notna(), "open_interest"].sum() / total)
