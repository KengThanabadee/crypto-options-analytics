import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from iv_surface.positioning import contract_gamma


DATA = Path(__file__).resolve().parents[1] / "data"
# Ticker gamma is printed to 5 decimals (often one significant digit), so the
# relative check uses the gamma Deribit's own vega implies under the same
# undiscounted Black-76 model: gamma_F = 100 * vega / (F^2 * sigma * T).
GAMMA_RTOL = 1e-3
TICKER_GAMMA_STEP = 1e-5


def _ticker_contracts():
    tickers = json.loads((DATA / "deribit_btc_gamma_check_tickers.json").read_text())
    snapshot = json.loads((DATA / tickers["paired_snapshot"]).read_text())
    instruments = {
        item["instrument_name"]: item
        for item in snapshot["requests"][0]["response"]["result"]
    }
    rows = []
    for request in tickers["requests"]:
        ticker = request["response"]["result"]
        instrument = instruments[ticker["instrument_name"]]
        rows.append({
            "name": ticker["instrument_name"],
            "strike": float(instrument["strike"]),
            "tau": (instrument["expiration_timestamp"] - ticker["timestamp"])
            / 1000 / 86_400 / 365,
            "mark_iv": ticker["mark_iv"] / 100,
            "forward": ticker["underlying_price"],
            "index": ticker["index_price"],
            "gamma": ticker["greeks"]["gamma"],
            "vega": ticker["greeks"]["vega"],
        })
    return rows


def test_ticker_capture_records_its_time_params_and_paired_snapshot():
    tickers = json.loads((DATA / "deribit_btc_gamma_check_tickers.json").read_text())
    datetime.fromisoformat(tickers["captured_at_utc"].replace("Z", "+00:00"))
    assert len(tickers["requests"]) >= 30
    for request in tickers["requests"]:
        assert request["endpoint"] == "/api/v2/public/ticker"
        assert request["params"]["instrument_name"] == (
            request["response"]["result"]["instrument_name"]
        )
        assert request["received_at_utc"]


def test_gamma_from_mark_iv_matches_deribit_ticker_gamma_on_its_forward_basis():
    rows = _ticker_contracts()
    assert {row["name"][-1] for row in rows} == {"C", "P"}
    for row in rows:
        ours = contract_gamma(
            row["strike"], row["tau"], row["mark_iv"], row["forward"], row["index"]
        )
        # Deribit quotes gamma per $1 of its forward; ours is per $1 of the
        # index with the forward moving in proportion, so gamma_F = ours * X / F.
        on_forward = ours * row["index"] / row["forward"]
        from_vega = 100 * row["vega"] / (
            row["forward"] ** 2 * row["mark_iv"] * row["tau"]
        )
        assert on_forward == pytest.approx(from_vega, rel=GAMMA_RTOL), row["name"]
        assert abs(on_forward - row["gamma"]) <= TICKER_GAMMA_STEP / 2 * (1 + GAMMA_RTOL)


def test_basis_conversion_matters_for_long_dated_contracts():
    misses = 0
    for row in _ticker_contracts():
        ours = contract_gamma(
            row["strike"], row["tau"], row["mark_iv"], row["forward"], row["index"]
        )
        from_vega = 100 * row["vega"] / (
            row["forward"] ** 2 * row["mark_iv"] * row["tau"]
        )
        misses += not math.isclose(ours, from_vega, rel_tol=GAMMA_RTOL)
    assert misses >= 6


SNAPSHOT_PATH = DATA / "deribit_btc_options_snapshot.json"


@pytest.fixture
def chain():
    from iv_surface.deribit import load_deribit_snapshot, parse_deribit_snapshot

    return parse_deribit_snapshot(load_deribit_snapshot(SNAPSHOT_PATH))


def test_one_real_contract_contribution_by_hand(chain):
    from iv_surface.positioning import gex_contributions

    raw = json.loads(SNAPSHOT_PATH.read_text())
    results = [request["response"]["result"] for request in raw["requests"]]
    name = "BTC-30OCT26-82000-P"
    instrument = next(i for i in results[0] if i["instrument_name"] == name)
    summary = next(s for s in results[1] if s["instrument_name"] == name)
    index_price = results[2]["index_price"]
    captured = datetime.fromisoformat(raw["captured_at_utc"].replace("Z", "+00:00"))

    # Step by step from the raw API fields, 365-day year.
    tau = (instrument["expiration_timestamp"] / 1000 - captured.timestamp()) / (365 * 86_400)
    sigma = summary["mark_iv"] / 100
    forward = summary["underlying_price"]
    strike = instrument["strike"]
    d1 = (math.log(forward / strike) + 0.5 * sigma**2 * tau) / (sigma * math.sqrt(tau))
    gamma = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi) / (
        index_price * sigma * math.sqrt(tau)
    )
    sign = -1  # Put, customer buys under the default Call+ / Put-.
    expected = sign * gamma * summary["open_interest"] * index_price**2 * 0.01

    rows = gex_contributions(chain).set_index("symbol")
    assert rows.loc[name, "gamma"] == pytest.approx(gamma, rel=1e-9)
    assert rows.loc[name, "contribution"] == pytest.approx(expected, rel=1e-9)
    assert rows.loc[name, "contribution"] < 0


def test_each_strike_bar_is_the_sum_of_its_contracts(chain):
    from iv_surface.positioning import gex_contributions, net_gex_by_strike

    taus = sorted(chain["tau"].unique())
    chosen = [taus[4], taus[5]]
    table = net_gex_by_strike(chain, expiries=chosen).set_index("strike")
    rows = gex_contributions(chain).set_index("symbol")
    names = ["BTC-23OCT26-82000-C", "BTC-23OCT26-82000-P",
             "BTC-30OCT26-82000-C", "BTC-30OCT26-82000-P"]
    assert table.loc[82_000.0, "net_gex"] == pytest.approx(
        rows.loc[names, "contribution"].sum(), rel=1e-12
    )
    assert table.loc[82_000.0, "call_gex"] == pytest.approx(
        rows.loc[names[::2], "contribution"].sum(), rel=1e-12
    )
    assert table.loc[82_000.0, "contracts"] == 4
    assert sorted(table.index) == sorted(chain.loc[chain.tau.isin(chosen), "strike"].unique())


def test_net_lets_calls_and_puts_cancel():
    import pandas as pd

    from iv_surface.positioning import net_gex_by_strike

    contract = dict(strike=80_000.0, tau=0.05, mark_iv=0.5, underlying_price=80_100.0,
                    index_price=80_000.0, open_interest=10.0)
    chain = pd.DataFrame([
        dict(contract, symbol="C", flag="call"),
        dict(contract, symbol="P", flag="put"),
    ])
    row = net_gex_by_strike(chain).iloc[0]
    assert row["call_gex"] > 0 and row["put_gex"] == pytest.approx(-row["call_gex"])
    assert row["net_gex"] == pytest.approx(0.0, abs=1e-9)


def test_computable_oi_share_counts_oi_with_a_gamma(chain):
    from iv_surface.positioning import computable_oi_share

    assert computable_oi_share(chain) == 1.0
    damaged = chain.copy()
    damaged.loc[damaged.symbol == "BTC-30OCT26-82000-C", "mark_iv"] = np.nan
    expected = 1 - 1698.2 / chain["open_interest"].sum()
    assert computable_oi_share(damaged) == pytest.approx(expected)


def test_gex_figure_shares_the_oi_strike_axis_and_labels_source_unit_and_assumption(chain):
    from iv_surface.positioning import net_gex_by_strike, open_interest_by_strike
    from iv_surface.visualization import make_gex_figure, make_open_interest_figure

    index_price = float(chain["index_price"].iloc[0])
    strike_range = (75_000.0, 90_000.0)
    table = net_gex_by_strike(chain)
    figure = make_gex_figure(
        table, index_price=index_price, strike_range=strike_range,
        scope="All expiries", assumption="Call+ / Put−", oi_share=1.0,
    )
    oi_figure = make_open_interest_figure(
        open_interest_by_strike(chain), index_price=index_price,
        strike_range=strike_range, scope="All expiries",
    )
    (bars,) = figure.data
    shown = table[(table.strike >= 75_000.0) & (table.strike <= 90_000.0)]
    assert bars.type == "bar"
    assert list(bars.x) == list(oi_figure.data[0].x) == shown["strike"].tolist()
    np.testing.assert_allclose(list(bars.y), shown["net_gex"])
    assert list(figure.layout.xaxis.range) == list(oi_figure.layout.xaxis.range)
    assert [shape.x0 for shape in figure.layout.shapes] == [index_price]

    label = figure.layout.title.text
    for text in ("Exchange mark IV", "USD per 1% BTC move", "Call+ / Put−",
                 "100% of OI computable", "All expiries"):
        assert text in label
    assert "USD per 1% BTC move" in figure.layout.yaxis.title.text

    hover = bars.hovertemplate
    assert "Strike: $%{x:,.0f}" in hover
    assert "Net GEX: %{y:$,.0f} per 1% BTC move" in hover
    for detail in ("Call GEX", "Put GEX", "Call OI", "Put OI", "Contracts"):
        assert detail in hover
    first = shown.iloc[0]
    np.testing.assert_allclose(
        bars.customdata[0],
        first[["call_gex", "put_gex", "call_oi", "put_oi", "contracts"]].to_numpy(dtype=float),
    )
