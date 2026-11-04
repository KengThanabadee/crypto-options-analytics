from pathlib import Path

import numpy as np
import pytest

from options_analytics import deribit
from options_analytics.iv_source import (
    build_iv_source_surface,
    combine_call_put_iv,
    contract_iv,
)
from options_analytics.solver import bs_price


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


def _side_iv(row, price):
    from options_analytics.solver import solve_iv

    rate = np.log(row.underlying_price / row.index_price) / row.tau
    return solve_iv(price, row.index_price, row.strike, row.tau, rate, row.flag)


def _two_sided_pair(chain, moneyness_test):
    spot = chain["index_price"].iloc[0]
    quoted = chain[
        (chain["quote_source"] == "mid") & moneyness_test(chain["strike"] / spot)
    ]
    for _, group in quoted.groupby(["tau", "strike"]):
        if len(group) == 2:
            call = group[group["flag"] == "call"].iloc[0]
            put = group[group["flag"] == "put"].iloc[0]
            try:
                sides = [_side_iv(row, row[p]) for row in (call, put)
                         for p in ("bid_price", "ask_price")]
            except ValueError:
                continue
            return call, put, sides
    raise AssertionError("no two-sided pair solved")


@pytest.mark.parametrize("iv_source", ["Exchange mark", "Quote midpoint"])
def test_near_atm_band_blends_bid_with_bid_and_ask_with_ask(chain, iv_source):
    call, put, (call_bid, call_ask, put_bid, put_ask) = _two_sided_pair(
        chain, lambda m: (m >= 0.98) & (m <= 1.02)
    )
    result = build_iv_source_surface(chain, iv_source)
    i, j = _cell(result, call)
    assert result.source_grid[i, j] == "near_atm_average"
    assert result.band_low[i, j] == pytest.approx((call_bid + put_bid) / 2, abs=1e-4)
    assert result.band_high[i, j] == pytest.approx((call_ask + put_ask) / 2, abs=1e-4)


def test_wing_band_uses_the_line_side_bid_and_ask(chain):
    call, put, (_, _, put_bid, put_ask) = _two_sided_pair(chain, lambda m: m < 0.95)
    result = build_iv_source_surface(chain, "Exchange mark")
    i, j = _cell(result, put)
    assert result.source_grid[i, j] == "put"
    assert result.band_low[i, j] == pytest.approx(put_bid, abs=1e-4)
    assert result.band_high[i, j] == pytest.approx(put_ask, abs=1e-4)


def test_band_is_missing_where_a_weighted_side_has_no_quote(chain):
    call, put, _ = _two_sided_pair(chain, lambda m: (m >= 0.98) & (m <= 1.02))
    damaged = chain.copy()
    damaged.loc[damaged["symbol"] == call.symbol, "bid_price"] = np.nan
    result = build_iv_source_surface(damaged, "Exchange mark")
    i, j = _cell(result, call)
    assert result.source_grid[i, j] == "near_atm_average"
    assert np.isnan(result.band_low[i, j])
    assert np.isfinite(result.band_high[i, j])


@pytest.fixture(scope="module")
def midpoint_frame(chain):
    from options_analytics.iv_source import iv_source_long_frame

    result = build_iv_source_surface(chain, "Quote midpoint")
    dates = chain.drop_duplicates("tau").set_index("tau")["expiry_dt"]
    return result, iv_source_long_frame(
        result, expiry_datetimes=dates.reindex(result.expiries).tolist()
    )


def test_long_frame_carries_line_band_and_source(midpoint_frame):
    result, frame = midpoint_frame
    np.testing.assert_array_equal(frame["iv"], result.iv_surface.reshape(-1))
    np.testing.assert_array_equal(frame["band_low"], result.band_low.reshape(-1))
    np.testing.assert_array_equal(frame["band_high"], result.band_high.reshape(-1))
    np.testing.assert_array_equal(frame["source"], result.source_grid.reshape(-1))
    assert set(frame["iv_source"]) == {"Quote midpoint"}


def test_smile_draws_a_labelled_display_band_and_names_the_source(midpoint_frame):
    from options_analytics.visualization import make_smile_figure

    result, frame = midpoint_frame
    tau = result.expiries[-1]
    figure = make_smile_figure(frame, selected_expiries=[tau], iv_source="Quote midpoint")
    lines = [trace for trace in figure.data if trace.mode == "lines+markers"]
    band, *bars = [trace for trace in figure.data if trace.mode != "lines+markers"]
    assert len(lines) == 1
    assert "Quote midpoint IV: %{y:.2%}" in lines[0].hovertemplate
    assert "display band" in lines[0].hovertemplate
    # The band names the option it belongs to, the same one as "IV from".
    assert "IV from: %{customdata[1]}" in lines[0].hovertemplate
    assert "bid–ask display band of %{customdata[1]}:" in lines[0].hovertemplate
    row = result.expiries.index(tau)
    order = np.argsort(result.strikes)
    moneyness = np.asarray(result.strikes)[order] / result.spot_price
    low, high = result.band_low[row, order], result.band_high[row, order]
    both = np.isfinite(low) & np.isfinite(high)
    expected = sorted(
        [(m, v) for m, v in zip(moneyness[both], high[both])]
        + [(m, v) for m, v in zip(moneyness[both], low[both])]
    )
    drawn = sorted(
        (x, y)
        for trace in [band, *bars]
        for x, y in zip(trace.x, trace.y)
        if x is not None
    )
    np.testing.assert_allclose(drawn, expected)
    assert all(trace.connectgaps is False for trace in figure.data)
    assert "display band" in band.name


@pytest.mark.parametrize("builder", ["make_iv_heatmap", "make_iv_surface_figure"])
def test_surface_hover_names_the_iv_source(midpoint_frame, builder):
    from options_analytics import visualization

    _, frame = midpoint_frame
    figure = getattr(visualization, builder)(frame, iv_source="Exchange mark")
    trace = figure.data[0]
    hover = trace.hovertemplate or " ".join(np.asarray(trace.text).reshape(-1)[:5])
    assert "Exchange mark IV:" in hover


def test_atm_hover_names_the_iv_source(midpoint_frame):
    from options_analytics.surface_transforms import atm_term_structure_frame
    from options_analytics.visualization import make_atm_term_structure_figure

    _, frame = midpoint_frame
    figure = make_atm_term_structure_figure(
        atm_term_structure_frame(frame), iv_source="Quote midpoint"
    )
    (line,) = [trace for trace in figure.data if trace.mode == "lines+markers"]
    assert "Quote midpoint IV: %{y:.2%}" in line.hovertemplate


@pytest.mark.parametrize("source", ["Exchange mark", "Quote midpoint"])
def test_a_shared_bid_ask_solve_gives_the_same_surface(chain, source):
    from options_analytics.iv_source import solve_bid_ask_iv

    shared = build_iv_source_surface(chain, source, bid_ask_iv=solve_bid_ask_iv(chain))
    own = build_iv_source_surface(chain, source)
    np.testing.assert_array_equal(shared.band_low, own.band_low)
    np.testing.assert_array_equal(shared.band_high, own.band_high)
    np.testing.assert_array_equal(shared.iv_surface, own.iv_surface)


def test_combined_iv_blends_near_atm_and_prefers_otm_wings():
    strikes = [95, 98, 100, 102, 105]
    call_iv = [[0.21, 0.22, 0.24, 0.26, 0.28]]
    put_iv = [[0.31, 0.32, 0.34, 0.36, 0.38]]

    combined, source_grid = combine_call_put_iv(call_iv, put_iv, strikes, 100)

    assert source_grid.tolist() == [[
        "put", "near_atm_average", "near_atm_average", "near_atm_average", "call",
    ]]
    np.testing.assert_allclose(combined[0], [0.31, 0.27, 0.29, 0.31, 0.28])


def test_combined_iv_wings_use_only_the_out_of_the_money_side():
    strikes = [95, 100, 105, 110]
    # The only IV at 95 is a Call and at 105 a Put: both in the money.
    call_iv = [[0.20, np.nan, np.nan, np.nan]]
    put_iv = [[np.nan, 0.30, 0.40, np.nan]]

    combined, source_grid = combine_call_put_iv(call_iv, put_iv, strikes, 100)

    assert source_grid.tolist() == [[
        "missing", "near_atm_put_only", "missing", "missing",
    ]]
    np.testing.assert_allclose(combined[0], [np.nan, 0.30, np.nan, np.nan])


def test_quote_midpoint_wings_have_no_in_the_money_iv(chain):
    result = build_iv_source_surface(chain, "Quote midpoint")
    moneyness = np.asarray(result.strikes) / result.spot_price
    labels = set(result.source_grid[:, moneyness < 0.98].reshape(-1))
    assert labels <= {"put", "missing"}
    labels = set(result.source_grid[:, moneyness > 1.02].reshape(-1))
    assert labels <= {"call", "missing"}
