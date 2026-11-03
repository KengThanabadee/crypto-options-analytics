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
    from iv_surface.positioning import computable_oi_share, net_gex_by_strike

    assert computable_oi_share(net_gex_by_strike(chain)) == 1.0
    damaged = chain.copy()
    damaged.loc[damaged.symbol == "BTC-30OCT26-82000-C", "mark_iv"] = np.nan
    expected = 1 - 1698.2 / chain["open_interest"].sum()
    assert computable_oi_share(net_gex_by_strike(damaged)) == pytest.approx(expected)
    damaged.loc[damaged.symbol == "BTC-30OCT26-84000-C", "open_interest"] = np.nan
    assert np.isnan(computable_oi_share(net_gex_by_strike(damaged)))


def _title(figure, name):
    (annotation,) = [a for a in figure.layout.annotations if a.name == name]
    return annotation.text


def test_gex_panel_labels_source_unit_and_assumption(chain):
    from iv_surface.positioning import net_gex_by_strike

    table = net_gex_by_strike(chain)
    figure = _positioning_figure(chain, table)
    bars = figure.data[2]
    shown = table[(table.strike >= 75_000.0) & (table.strike <= 90_000.0)]
    assert bars.type == "bar" and bars.yaxis == "y2"
    assert list(bars.x) == shown["strike"].tolist()
    np.testing.assert_allclose(list(bars.y), shown["net_gex"])

    label = _title(figure, "gex_title")
    for text in ("Exchange mark IV", "USD per 1% BTC move", "Call+ / Put−",
                 "100% of OI computable", "All expiries"):
        assert text in label
    assert _title(figure, "oi_title") == "Open interest · All expiries"
    assert figure.layout.yaxis.title.text == "OI · BTC"
    assert "USD per 1% BTC move" in figure.layout.yaxis2.title.text

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


def test_net_states_the_assumption_as_a_scenario_and_gross_leaves_it_out(chain):
    from iv_surface.positioning import assumption_label, net_gex_by_strike

    table = net_gex_by_strike(chain)
    label = assumption_label({"call": -1, "put": -1})
    figures = {
        mode: _positioning_figure(chain, table, assumption=label, mode=mode)
        for mode in ("Net", "Gross")
    }
    shown = table[(table.strike >= 75_000.0) & (table.strike <= 90_000.0)]
    gross = figures["Gross"]
    np.testing.assert_allclose(list(gross.data[2].y), shown["gross_gex"])
    assert _title(gross, "gex_title").startswith("Gross gamma exposure")
    assert "Gross GEX" in gross.layout.yaxis2.title.text
    assert "Gross GEX: %{y:$,.0f} per 1% BTC move" in gross.data[2].hovertemplate
    net = figures["Net"]
    title = _title(net, "gex_title")
    assert "Scenario: Call− / Put− (Calls customer buys, Puts customer buys)" in title
    assert "not observed dealer inventory" in title
    assert "Scenario: Call− / Put−" in net.data[2].hovertemplate
    assert "Scenario" not in _title(gross, "gex_title")
    assert "Scenario" not in gross.data[2].hovertemplate


def test_gross_bars_have_their_own_colour(chain):
    from iv_surface.positioning import net_gex_by_strike

    figure = _positioning_figure(chain, net_gex_by_strike(chain), mode="Gross")
    oi_colours = {figure.data[0].marker.color, figure.data[1].marker.color}
    net_colours = set(_positioning_figure(chain, net_gex_by_strike(chain)).data[2].marker.color)
    gross_colour = figure.data[2].marker.color
    assert isinstance(gross_colour, str)
    assert gross_colour not in oi_colours | net_colours


def test_index_label_sits_inside_the_oi_panel_below_its_title(chain):
    from iv_surface.positioning import net_gex_by_strike

    figure = _positioning_figure(chain, net_gex_by_strike(chain))
    (label,) = [a for a in figure.layout.annotations if a.text.startswith("Index")]
    assert label.text == f"Index ${chain['index_price'].iloc[0]:,.2f}"
    # The OI title sits above the panel; the label hangs from the panel's top edge.
    assert label.yanchor == "top"
    assert label.yref == "y domain" and label.y <= 1


ALL_SIGNS = [
    {"call": 1, "put": -1},
    {"call": 1, "put": 1},
    {"call": -1, "put": 1},
    {"call": -1, "put": -1},
]


def test_customer_buys_gives_dealer_negative_gamma_on_every_expiry(chain):
    from iv_surface.positioning import gex_contributions

    rows = gex_contributions(chain, signs={"call": -1, "put": 1})
    calls, puts = rows[rows.flag == "call"], rows[rows.flag == "put"]
    # Zero OI or vanishing far-wing gamma gives zero; nothing takes the other sign.
    assert (calls["contribution"] <= 0).all() and (puts["contribution"] >= 0).all()
    for side, sign in ((calls, -1), (puts, 1)):
        nonzero = side[side["contribution"] != 0]
        assert nonzero["tau"].nunique() == chain["tau"].nunique()
        assert (np.sign(nonzero["contribution"]) == sign).all()


def test_gross_adds_magnitudes_so_calls_and_puts_do_not_cancel():
    import pandas as pd

    from iv_surface.positioning import net_gex_by_strike

    contract = dict(strike=80_000.0, tau=0.05, mark_iv=0.5, underlying_price=80_100.0,
                    index_price=80_000.0, open_interest=10.0)
    chain = pd.DataFrame([
        dict(contract, symbol="C", flag="call"),
        dict(contract, symbol="P", flag="put", open_interest=4.0),
    ])
    row = net_gex_by_strike(chain).iloc[0]
    # Call 10 BTC long gamma, Put 4 BTC short gamma: Net 6 units, Gross 14.
    unit = row["call_gex"] / 10.0
    assert row["net_gex"] == pytest.approx(6 * unit)
    assert row["gross_gex"] == pytest.approx(14 * unit)


def test_gross_keeps_the_net_computability_rule():
    import pandas as pd

    from iv_surface.positioning import net_gex_by_strike

    contract = dict(strike=80_000.0, tau=0.05, underlying_price=80_100.0,
                    index_price=80_000.0, open_interest=10.0)
    chain = pd.DataFrame([
        dict(contract, symbol="C", flag="call", mark_iv=0.5),
        dict(contract, symbol="P", flag="put", mark_iv=np.nan),
    ])
    row = net_gex_by_strike(chain).iloc[0]
    assert np.isnan(row["net_gex"]) == np.isnan(row["gross_gex"])


def test_flipping_an_assumption_changes_only_signs(chain):
    """Spec check 3: Gross >= |Net| per strike; flips leave Gross unchanged."""
    from iv_surface.positioning import gex_contributions, net_gex_by_strike

    taus = sorted(chain["tau"].unique())
    base_rows = gex_contributions(chain)
    base = net_gex_by_strike(chain, expiries=taus[:3])
    nets = set()
    for signs in ALL_SIGNS:
        rows = gex_contributions(chain, signs=signs)
        np.testing.assert_array_equal(rows["gamma"], base_rows["gamma"])
        np.testing.assert_array_equal(rows["open_interest"], base_rows["open_interest"])
        np.testing.assert_allclose(rows["contribution"].abs(), base_rows["contribution"].abs())

        table = net_gex_by_strike(chain, expiries=taus[:3], signs=signs)
        np.testing.assert_allclose(table["gross_gex"], base["gross_gex"], rtol=1e-12)
        assert (table["gross_gex"] >= table["net_gex"].abs() * (1 - 1e-12)).all()
        nets.add(tuple(np.round(table["net_gex"], 6)))
    assert len(nets) == 4

def _strike_chain(**overrides):
    import pandas as pd

    contract = dict(strike=80_000.0, tau=0.05, mark_iv=0.5, underlying_price=80_100.0,
                    index_price=80_000.0, open_interest=10.0)
    rows = [
        dict(contract, symbol="C1", flag="call"),
        dict(contract, symbol="P1", flag="put"),
        dict(contract, symbol="C2", flag="call", tau=0.1, open_interest=30.0),
    ]
    for symbol, fields in overrides.items():
        next(row for row in rows if row["symbol"] == symbol).update(fields)
    return pd.DataFrame(rows)


def test_known_zero_oi_contributes_zero_even_without_iv():
    from iv_surface.positioning import gex_contributions, net_gex_by_strike

    chain = _strike_chain(P1=dict(open_interest=0.0, mark_iv=np.nan))
    rows = gex_contributions(chain).set_index("symbol")
    assert rows.loc["P1", "contribution"] == 0.0
    row = net_gex_by_strike(chain).iloc[0]
    assert row["status"] == "complete"
    assert row["net_gex"] == pytest.approx(rows["contribution"].sum())


def test_removing_one_contracts_iv_gives_incomplete_data_with_details():
    from iv_surface.positioning import gex_contributions, net_gex_by_strike

    full = gex_contributions(_strike_chain()).set_index("symbol")["contribution"]
    row = net_gex_by_strike(_strike_chain(P1=dict(mark_iv=np.nan))).iloc[0]
    assert row["status"] == "incomplete"
    assert np.isnan(row["net_gex"])
    assert row["partial_net_gex"] == pytest.approx(full["C1"] + full["C2"])
    assert (row["usable"], row["contracts"]) == (2, 3)
    assert row["oi_share"] == pytest.approx(40 / 50)
    assert row["reason"] == "1 Put: no mark IV"


def test_missing_oi_is_not_zero_and_leaves_the_oi_share_unknown():
    from iv_surface.positioning import net_gex_by_strike

    row = net_gex_by_strike(_strike_chain(C2=dict(open_interest=np.nan))).iloc[0]
    assert row["status"] == "incomplete"
    assert np.isnan(row["net_gex"]) and np.isnan(row["oi_share"])
    assert row["reason"] == "1 Call: no OI"


def test_removing_every_contracts_input_gives_insufficient_data():
    from iv_surface.positioning import net_gex_by_strike

    chain = _strike_chain(C1=dict(mark_iv=np.nan), P1=dict(open_interest=np.nan),
                          C2=dict(mark_iv=np.nan))
    row = net_gex_by_strike(chain).iloc[0]
    assert row["status"] == "insufficient"
    assert np.isnan(row["net_gex"]) and np.isnan(row["partial_net_gex"])
    assert row["usable"] == 0
    assert row["reason"] == "1 Put: no OI; 2 Calls: no mark IV"


def test_partial_subtotal_adds_magnitudes_for_gross():
    from iv_surface.positioning import gex_contributions, strike_coverage

    rows = gex_contributions(_strike_chain(C2=dict(mark_iv=np.nan)))
    rows["mark_iv"] = [0.5, 0.5, np.nan]
    coverage = strike_coverage(rows, rows["contribution"].abs())
    call, put = rows["contribution"].iloc[0], rows["contribution"].iloc[1]
    assert call > 0 > put
    assert coverage["partial"] == pytest.approx(call - put)


def test_incomplete_strike_shows_the_partial_subtotal_of_the_selected_mode():
    from iv_surface.positioning import gex_contributions, net_gex_by_strike

    full = gex_contributions(_strike_chain()).set_index("symbol")["contribution"]
    chain = _strike_chain(C2=dict(mark_iv=np.nan))
    table = net_gex_by_strike(chain)
    row = table.iloc[0]
    assert full["C1"] > 0 > full["P1"]
    assert row["partial_net_gex"] == pytest.approx(full["C1"] + full["P1"])
    assert row["partial_gross_gex"] == pytest.approx(full["C1"] - full["P1"])
    assert np.isnan(row["gross_gex"])

    for mode, partial in (("Net", full["C1"] + full["P1"]), ("Gross", full["C1"] - full["P1"])):
        figure = _positioning_figure(
            chain, table, strike_range=(75_000.0, 85_000.0), oi_share=np.nan, mode=mode,
        )
        (text,) = figure.data[3].hovertext
        assert f"Partial {mode} GEX (computable contracts only): ${partial:,.0f}" in text


def test_real_snapshot_damage_marks_only_the_damaged_strike(chain):
    from iv_surface.positioning import net_gex_by_strike

    clean = net_gex_by_strike(chain).set_index("strike")
    assert set(clean["status"]) == {"complete"}
    damaged = chain.copy()
    damaged.loc[damaged.symbol == "BTC-30OCT26-82000-C", "mark_iv"] = np.nan
    table = net_gex_by_strike(damaged).set_index("strike")
    assert table.loc[82_000.0, "status"] == "incomplete"
    assert np.isnan(table.loc[82_000.0, "net_gex"])
    assert (table.drop(82_000.0)["status"] == "complete").all()

    damaged.loc[damaged.strike == 82_000.0, "mark_iv"] = np.nan
    row = net_gex_by_strike(damaged).set_index("strike").loc[82_000.0]
    assert row["status"] == "insufficient" and np.isnan(row["net_gex"])
    assert row["usable"] == 0 and "no mark IV" in row["reason"]


def test_gex_figure_marks_incomplete_and_insufficient_strikes_without_bars(chain):
    from iv_surface.positioning import net_gex_by_strike

    damaged = chain.copy()
    damaged.loc[damaged.symbol == "BTC-30OCT26-82000-C", "mark_iv"] = np.nan
    damaged.loc[damaged.strike == 84_000.0, "open_interest"] = np.nan
    table = net_gex_by_strike(damaged)
    figure = _positioning_figure(damaged, table, oi_share=np.nan)
    bars, incomplete, insufficient = figure.data[2:]
    shown_bars = dict(zip(bars.x, bars.y))
    assert np.isnan(shown_bars[82_000.0]) and np.isnan(shown_bars[84_000.0])
    assert all(np.isfinite(y) for x, y in shown_bars.items() if x not in (82_000.0, 84_000.0))

    assert incomplete.name == "Incomplete data" and list(incomplete.x) == [82_000.0]
    assert insufficient.name == "Insufficient data" and list(insufficient.x) == [84_000.0]
    # Markers sit in a strip on their own axis, away from the GEX zero line.
    assert incomplete.yaxis == insufficient.yaxis == "y3"
    assert incomplete.xaxis == insufficient.xaxis == "x2"
    assert figure.layout.yaxis3.overlaying == "y2"

    row = table.set_index("strike").loc[82_000.0]
    (text,) = incomplete.hovertext
    for detail in ("Incomplete data", "Partial Net GEX (computable contracts only)",
                   f"{row['usable']} of {row['contracts']} contracts",
                   f"{row['oi_share']:.1%} of strike OI computable",
                   "Reason: 1 Call: no mark IV"):
        assert detail in text
    (text,) = insufficient.hovertext
    assert "Insufficient data" in text and "Reason:" in text and "no OI" in text

    complete = int((table.status == "complete").sum())
    title = _title(figure, "gex_title")
    assert "unknown share of OI computable" in title
    assert f"{complete} of {len(table)} strikes complete" in title
    assert "every strike in All expiries" in title


def _positioning_figure(chain, gex_table=None, strike_range=(75_000.0, 90_000.0), **kwargs):
    from iv_surface.positioning import net_gex_by_strike, open_interest_by_strike
    from iv_surface.visualization import make_positioning_figure

    options = dict(scope="All expiries", assumption="Call+ / Put−", oi_share=1.0)
    options.update(kwargs)
    return make_positioning_figure(
        open_interest_by_strike(chain),
        net_gex_by_strike(chain) if gex_table is None else gex_table,
        index_price=float(chain["index_price"].iloc[0]),
        strike_range=strike_range,
        **options,
    )


def test_oi_and_gex_share_one_strike_axis_so_strikes_line_up_and_zoom_together(chain):
    figure = _positioning_figure(chain)
    call, put, gex = figure.data[:3]
    assert (call.name, put.name, gex.name) == ("Call", "Put", "Net GEX")
    assert list(call.x) == list(gex.x)
    assert call.xaxis == put.xaxis == "x" and gex.xaxis == "x2"
    # Same horizontal domain: a strike sits at the same pixel in both panels.
    assert figure.layout.xaxis.domain == figure.layout.xaxis2.domain
    # Matched axes: a drag-zoom in either panel zooms the other.
    assert figure.layout.xaxis.matches == "x2"
    assert list(figure.layout.xaxis.range) == [74_750.0, 90_250.0]
    index_price = float(chain["index_price"].iloc[0])
    assert [shape.x0 for shape in figure.layout.shapes] == [index_price, index_price]
