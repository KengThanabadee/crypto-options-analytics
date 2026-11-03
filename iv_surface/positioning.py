"""Open interest positioning by strike from a parsed Deribit chain."""

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
