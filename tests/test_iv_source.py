from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from iv_surface import deribit
from iv_surface.iv_source import build_iv_source_surface, contract_iv
from iv_surface.solver import bs_price


SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data/deribit_btc_options_snapshot.json"


@pytest.fixture(scope="module")
def chain():
    return deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot(SNAPSHOT_PATH))


def _reprice(row, sigma):
    # Deribit inverse convention: R = ln(F / X) / T with the index X as spot.
    rate = np.log(row.underlying_price / row.index_price) / row.tau
    return bs_price(row.index_price, row.strike, row.tau, rate, sigma, row.flag)


def test_quote_midpoint_iv_prices_back_to_the_midpoint_within_one_cent(chain):
    iv = contract_iv(chain, "Quote midpoint")

    assert iv.index.equals(chain.index)
    solved = chain[np.isfinite(iv)]
    # The 2026-10-15 snapshot: 900 two-sided midpoints, 882 solve (research).
    assert len(solved) == 882
    residuals = [
        abs(_reprice(row, sigma) - row.mid_price)
        for row, sigma in zip(solved.itertuples(), iv[np.isfinite(iv)])
    ]
    assert max(residuals) <= 0.01


def test_unsolved_or_unquoted_midpoints_count_as_missing(chain):
    iv = contract_iv(chain, "Quote midpoint")

    no_quote = chain["quote_source"] != "mid"
    assert iv[no_quote].isna().all()
    assert np.isfinite(chain["mid_price"]).sum() - np.isfinite(iv).sum() == 18


def _cell(result, row):
    return result.expiries.index(row.tau), result.strikes.index(row.strike)


def _contract(chain, flag, moneyness_test):
    spot = chain["index_price"].iloc[0]
    candidates = chain[
        (chain["flag"] == flag)
        & np.isfinite(chain["mark_iv"])
        & moneyness_test(chain["strike"] / spot)
    ]
    return candidates.iloc[len(candidates) // 2]


@pytest.mark.parametrize("iv_source", ["Exchange mark", "Quote midpoint"])
def test_both_sources_follow_the_combined_iv_rule(chain, iv_source):
    result = build_iv_source_surface(chain, iv_source)
    iv = contract_iv(chain, iv_source)
    keyed = {
        (row.flag, row.tau, row.strike): value
        for row, value in zip(chain.itertuples(), iv)
    }
    spot = chain["index_price"].iloc[0]
    assert result.spot_price == spot
    assert result.iv_source == iv_source
    checked = {"put": 0, "call": 0, "near_atm_average": 0}
    for i, tau in enumerate(result.expiries):
        for j, strike in enumerate(result.strikes):
            call = keyed.get(("call", tau, strike), np.nan)
            put = keyed.get(("put", tau, strike), np.nan)
            moneyness = strike / spot
            if 0.98 <= moneyness <= 1.02 and np.isfinite(call) and np.isfinite(put):
                expected, label = (call + put) / 2, "near_atm_average"
            elif moneyness < 0.98 and np.isfinite(put):
                expected, label = put, "put"
            elif moneyness > 1.02 and np.isfinite(call):
                expected, label = call, "call"
            else:
                continue
            assert result.source_grid[i, j] == label
            assert result.iv_surface[i, j] == pytest.approx(expected)
            checked[label] += 1
    assert min(checked.values()) > 0


def test_exchange_mark_surface_uses_mark_iv_as_reported(chain):
    put = _contract(chain, "put", lambda m: m < 0.9)
    result = build_iv_source_surface(chain, "Exchange mark")
    i, j = _cell(result, put)
    assert result.iv_surface[i, j] == put.mark_iv
    assert result.source_grid[i, j] == "put"


def test_unusable_selected_source_iv_is_missing_and_never_filled_from_the_other(chain):
    midpoint = contract_iv(chain, "Quote midpoint")
    both_solve = chain.assign(mid_iv=midpoint).groupby(["tau", "strike"]).filter(
        lambda group: len(group) == 2 and np.isfinite(group["mid_iv"]).all()
    )
    target = both_solve.iloc[0]
    damaged = chain.copy()
    same_cell = (damaged["tau"] == target.tau) & (damaged["strike"] == target.strike)
    damaged.loc[same_cell, "mark_iv"] = [np.nan, -0.1]

    result = build_iv_source_surface(damaged, "Exchange mark")
    i, j = _cell(result, target)
    assert np.isnan(result.iv_surface[i, j])
    assert result.source_grid[i, j] == "missing"
