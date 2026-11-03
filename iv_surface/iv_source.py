"""Per-contract IV for the dashboard's IV source selector.

Exchange mark IV is Deribit's reported ``mark_iv``. Quote midpoint IV is this
repository's solver on the bid/ask midpoint, priced with Deribit's inverse
convention: the index ``X`` is spot and each contract's reported forward ``F``
sets ``R = ln(F / X) / T``, so no rate is chosen.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from iv_surface.solver import bs_price, solve_iv
from iv_surface.surface_builder import combine_call_put_iv


EXCHANGE_MARK = "Exchange mark"
QUOTE_MIDPOINT = "Quote midpoint"
IV_SOURCES = (EXCHANGE_MARK, QUOTE_MIDPOINT)
DEFAULT_IV_SOURCE = EXCHANGE_MARK
# A solved IV must reprice its USD premium within one cent, else it is missing.
REPRICE_TOLERANCE_USD = 0.01


def _numeric(chain: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(chain[column], errors="coerce").to_numpy(dtype=float)


def solve_contract_iv(chain: pd.DataFrame, price_column: str) -> pd.Series:
    """Solve each contract's USD premium in ``price_column`` at its forward rate.

    Unusable inputs, failed solves and solves that do not reprice within
    ``REPRICE_TOLERANCE_USD`` stay ``NaN``.
    """
    price = _numeric(chain, price_column)
    spot = _numeric(chain, "index_price")
    forward = _numeric(chain, "underlying_price")
    strike = _numeric(chain, "strike")
    tau = _numeric(chain, "tau")
    flags = chain["flag"].to_numpy()

    iv = np.full(len(chain), np.nan)
    for i in range(len(chain)):
        inputs = (price[i], spot[i], forward[i], strike[i], tau[i])
        if not all(np.isfinite(inputs)) or min(inputs) <= 0:
            continue
        if flags[i] not in ("call", "put"):
            continue
        rate = np.log(forward[i] / spot[i]) / tau[i]
        try:
            sigma = solve_iv(price[i], spot[i], strike[i], tau[i], rate, flags[i])
        except ValueError:
            continue
        repriced = bs_price(spot[i], strike[i], tau[i], rate, sigma, flags[i])
        if abs(repriced - price[i]) <= REPRICE_TOLERANCE_USD:
            iv[i] = sigma
    return pd.Series(iv, index=chain.index, name="iv")


def contract_iv(chain: pd.DataFrame, iv_source: str) -> pd.Series:
    """Return each contract's IV from one source; unusable values are ``NaN``."""
    if iv_source == EXCHANGE_MARK:
        mark = _numeric(chain, "mark_iv")
        usable = np.isfinite(mark) & (mark > 0)
        return pd.Series(np.where(usable, mark, np.nan), index=chain.index, name="iv")
    if iv_source == QUOTE_MIDPOINT:
        quoted = chain["quote_source"].eq("mid")
        return solve_contract_iv(chain, "mid_price").where(quoted)
    raise ValueError(f"iv_source must be one of {IV_SOURCES}, got {iv_source!r}")


@dataclass(frozen=True)
class IVSourceResult:
    """Combined IV for one source, as expiry rows by strike columns."""

    iv_source: str
    iv_surface: np.ndarray
    source_grid: np.ndarray
    call_iv_surface: np.ndarray
    put_iv_surface: np.ndarray
    spot_price: float
    expiries: list[float]
    strikes: list[float]


def _contract_grid(chain, values, flag, expiries, strikes):
    grid = np.full((len(expiries), len(strikes)), np.nan)
    rows = {tau: i for i, tau in enumerate(expiries)}
    columns = {strike: j for j, strike in enumerate(strikes)}
    side = chain["flag"].to_numpy() == flag
    for tau, strike, value in zip(
        chain["tau"].to_numpy()[side],
        chain["strike"].to_numpy()[side],
        np.asarray(values, dtype=float)[side],
    ):
        grid[rows[tau], columns[strike]] = value
    return grid


def _chain_axes(chain):
    tau = _numeric(chain, "tau")
    strike = _numeric(chain, "strike")
    spot = _numeric(chain, "index_price")
    valid = (
        chain["flag"].isin(["call", "put"]).to_numpy()
        & np.isfinite(tau) & (tau > 0) & np.isfinite(strike) & (strike > 0)
    )
    if not valid.any():
        raise ValueError("chain has no valid Call or Put expiry/strike rows")
    usable_spot = spot[np.isfinite(spot) & (spot > 0)]
    if usable_spot.size == 0:
        raise ValueError("chain has no finite positive index_price")
    data = chain[valid]
    if data.duplicated(["flag", "tau", "strike"]).any():
        raise ValueError("chain contains duplicate rows for the same flag, tau, and strike")
    return (
        data,
        sorted(data["tau"].unique().tolist()),
        sorted(data["strike"].unique().tolist()),
        float(np.median(usable_spot)),
    )


def build_iv_source_surface(chain: pd.DataFrame, iv_source: str) -> IVSourceResult:
    """Build the Combined IV surface from one IV source, never mixing sources."""
    data, expiries, strikes, spot_price = _chain_axes(chain)
    iv = contract_iv(data, iv_source)
    call_iv = _contract_grid(data, iv, "call", expiries, strikes)
    put_iv = _contract_grid(data, iv, "put", expiries, strikes)
    combined, source_grid = combine_call_put_iv(call_iv, put_iv, strikes, spot_price)
    return IVSourceResult(
        iv_source=iv_source,
        iv_surface=combined,
        source_grid=source_grid,
        call_iv_surface=call_iv,
        put_iv_surface=put_iv,
        spot_price=spot_price,
        expiries=expiries,
        strikes=strikes,
    )
