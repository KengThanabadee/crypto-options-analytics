from copy import deepcopy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from options_analytics.deribit import load_deribit_snapshot, parse_deribit_snapshot
from options_analytics.chain import compute_tau
from options_analytics.solver import bs_price
from options_analytics.iv_source import QUOTE_MIDPOINT, build_iv_source_surface


FIXTURE = Path(__file__).resolve().parents[1] / "data/deribit_btc_options_snapshot.json"


def snapshot():
    return load_deribit_snapshot(FIXTURE)


def test_real_snapshot_reconciles_and_keeps_frozen_metadata(monkeypatch):
    import requests

    def fail(*args, **kwargs):
        raise AssertionError("Snapshot parsing must be offline")

    monkeypatch.setattr(requests.sessions.Session, "request", fail)
    raw = snapshot()
    chain = parse_deribit_snapshot(raw)
    assert len(raw["requests"][0]["response"]["result"]) == len(chain) == 936
    assert len(raw["requests"][1]["response"]["result"]) == 936
    assert chain.tau.nunique() == 12
    assert chain.symbol.nunique() == 936
    assert chain.mid_price.isna().sum() == 36
    captured = datetime.fromisoformat(raw["captured_at_utc"].replace("Z", "+00:00"))
    assert (chain.tau == chain.expiry_dt.map(lambda dt: compute_tau(dt, captured))).all()
    assert all(dt.tzinfo == timezone.utc for dt in chain.expiry_dt)
    assert (chain.index_price == 82227.73).all()
    assert (chain.estimated_delivery_price == 82256.17).all()
    assert chain.open_interest.notna().all() and chain.underlying_price.notna().all()
    np.testing.assert_allclose(chain.bid_price, chain.bid_price_btc * chain.index_price)
    np.testing.assert_allclose(chain.ask_price, chain.ask_price_btc * chain.index_price)
    np.testing.assert_allclose(chain.mid_price, chain.mid_price_btc * chain.index_price)
    assert not chain.duplicated(["flag", "tau", "strike"]).any()
    assert raw == snapshot()  # The adapter never rewrites raw data.


def _one_contract():
    raw = snapshot()
    instrument = deepcopy(raw["requests"][0]["response"]["result"][0])
    book = next(deepcopy(b) for b in raw["requests"][1]["response"]["result"]
                if b["instrument_name"] == instrument["instrument_name"])
    raw["requests"][0]["response"]["result"] = [instrument]
    raw["requests"][1]["response"]["result"] = [book]
    return raw, instrument, book


@pytest.mark.parametrize("flag", ["call", "put"])
def test_usd_conversion_recovers_known_iv_with_own_solver(flag):
    raw, instrument, book = _one_contract()
    spot, strike, sigma, rate = 100000, 100000, .45, .03
    raw["requests"][2]["response"]["result"]["index_price"] = spot
    instrument["strike"] = strike
    instrument["option_type"] = flag
    instrument["expiration_timestamp"] = datetime(2027, 3, 26, 8, tzinfo=timezone.utc).timestamp() * 1000
    captured = datetime.fromisoformat(raw["captured_at_utc"].replace("Z", "+00:00"))
    tau = compute_tau(datetime(2027, 3, 26, 8, tzinfo=timezone.utc), captured)
    price = bs_price(spot, strike, tau, rate, sigma, flag)
    book.update(bid_price=price / spot * .99, ask_price=price / spot * 1.01,
                mark_price=999, mark_iv=99, underlying_price=spot * np.exp(rate * tau))
    chain = parse_deribit_snapshot(raw)
    assert chain.iloc[0].mid_price == pytest.approx(price)
    assert chain.iloc[0].mark_iv == .99
    result = build_iv_source_surface(chain, QUOTE_MIDPOINT)
    assert result.spot_price == spot
    assert result.iv_surface[0, 0] == pytest.approx(sigma, abs=1e-6)


@pytest.mark.parametrize("bid,ask", [(None,.01), (.01,None), (0,.01), (.01,0), (.02,.01), (-.01,.01), ("bad",.01)])
def test_invalid_quotes_stay_missing_despite_mark_and_exchange_mid(bid, ask):
    raw, _, book = _one_contract()
    book.update(bid_price=bid, ask_price=ask, mark_price=.01, mid_price=.01)
    chain = parse_deribit_snapshot(raw)
    assert np.isnan(chain.iloc[0].mid_price)
    assert chain.iloc[0].quote_source == "none"
    assert np.isfinite(chain.iloc[0].mark_price)


def test_absent_book_retains_instrument_as_missing():
    raw, _, _ = _one_contract()
    raw["requests"][1]["response"]["result"] = []
    chain = parse_deribit_snapshot(raw)
    assert len(chain) == 1
    assert np.isnan(chain.iloc[0].mid_price)
    assert chain.iloc[0].quote_source == "none"


@pytest.mark.parametrize("case", ["schema", "time", "rpc", "index", "currency", "contract", "duplicate", "identity", "join", "expiry", "flag", "book_currency"])
def test_rejects_invalid_snapshot_and_ambiguous_contracts(case):
    raw, instrument, book = _one_contract()
    if case == "schema": raw["schema_version"] = -1
    elif case == "time": raw["captured_at_utc"] = "2020-01-01T00:00:00Z"
    elif case == "rpc": raw["requests"][1]["response"]["error"] = {"code": 1}
    elif case == "index": raw["requests"][2]["response"]["result"]["index_price"] = 0
    elif case == "currency": instrument["quote_currency"] = "USDC"
    elif case == "contract": instrument["contract_size"] = 2
    elif case == "duplicate": raw["requests"][0]["response"]["result"].append(instrument)
    elif case == "identity":
        other = deepcopy(instrument); other["instrument_name"] += "-OTHER"
        raw["requests"][0]["response"]["result"].append(other)
    elif case == "join": book["instrument_name"] = "unknown"
    elif case == "expiry": instrument["expiration_timestamp"] = None
    elif case == "flag": instrument["option_type"] = "other"
    elif case == "book_currency": book["quote_currency"] = "USD"
    with pytest.raises(ValueError): parse_deribit_snapshot(raw)


def test_each_contract_carries_open_interest_and_reported_forward():
    raw, _, book = _one_contract()
    book.update(open_interest=12.5, underlying_price=83000.5)
    contract = parse_deribit_snapshot(raw).iloc[0]
    assert contract.open_interest == 12.5
    assert contract.underlying_price == 83000.5


@pytest.mark.parametrize("value", [None, "bad", "absent"])
def test_missing_open_interest_stays_missing_not_zero(value):
    raw, _, book = _one_contract()
    if value == "absent":
        raw["requests"][1]["response"]["result"] = []
    else:
        book["open_interest"] = value
    assert np.isnan(parse_deribit_snapshot(raw).iloc[0].open_interest)


def test_estimated_delivery_price_is_raw_data_and_index_stays_spot():
    raw, _, book = _one_contract()
    raw["requests"][2]["response"]["result"]["index_price"] = 80000
    book.update(estimated_delivery_price=90000, bid_price=.01, ask_price=.03)
    contract = parse_deribit_snapshot(raw).iloc[0]
    assert contract.estimated_delivery_price == 90000
    assert contract.index_price == 80000
    assert contract.mid_price == pytest.approx(.02 * 80000)


def _add_contract_expiring_at(raw, instrument, book, expiry, suffix):
    other, other_book = deepcopy(instrument), deepcopy(book)
    name = instrument["instrument_name"] + suffix
    other["instrument_name"] = other_book["instrument_name"] = name
    other["expiration_timestamp"] = expiry.timestamp() * 1000
    raw["requests"][0]["response"]["result"].append(other)
    raw["requests"][1]["response"]["result"].append(other_book)
    return name


def _captured(raw):
    return datetime.fromisoformat(raw["captured_at_utc"].replace("Z", "+00:00"))


def test_settled_contracts_are_left_out_and_unexpired_ones_kept():
    raw, instrument, book = _one_contract()
    captured = _captured(raw)
    _add_contract_expiring_at(raw, instrument, book, captured, "-AT-END")
    _add_contract_expiring_at(
        raw, instrument, book, captured - timedelta(hours=1), "-SETTLED")
    just_after = _add_contract_expiring_at(
        raw, instrument, book, captured + timedelta(seconds=1), "-LAST-SECOND")
    chain = parse_deribit_snapshot(raw)
    assert set(chain.symbol) == {instrument["instrument_name"], just_after}
    assert (chain.tau > 0).all()


def test_snapshot_with_only_settled_contracts_is_rejected():
    raw, instrument, _ = _one_contract()
    instrument["expiration_timestamp"] = _captured(raw).timestamp() * 1000
    with pytest.raises(ValueError, match="unexpired"):
        parse_deribit_snapshot(raw)


class _ReplaySession:
    """Serve the frozen responses by endpoint, as Deribit's public API would."""

    def __init__(self, raw, fail_on=None, error=None):
        self.responses = {r["endpoint"]: r["response"] for r in raw["requests"]}
        self.fail_on, self.error, self.calls = fail_on, error, []

    def get(self, url, params=None, timeout=None):
        import requests

        endpoint = url.removeprefix("https://www.deribit.com")
        self.calls.append((endpoint, params, timeout))
        if endpoint == self.fail_on:
            raise self.error
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(self.responses[endpoint]).encode()
        return response


def test_fetched_snapshot_has_the_frozen_shape_and_parses_like_it():
    from options_analytics.deribit import fetch_deribit_snapshot

    raw = snapshot()
    session = _ReplaySession(raw)
    before = datetime.now(timezone.utc)
    fetched = fetch_deribit_snapshot(session=session)
    after = datetime.now(timezone.utc)

    assert {k: fetched[k] for k in ("schema_version", "exchange", "currency", "base_url")} == {
        "schema_version": 1, "exchange": "deribit", "currency": "BTC",
        "base_url": "https://www.deribit.com",
    }
    assert [(r["endpoint"], r["params"]) for r in fetched["requests"]] == [
        (r["endpoint"], r["params"]) for r in raw["requests"]
    ]
    assert [r["response"] for r in fetched["requests"]] == [r["response"] for r in raw["requests"]]
    times = [fetched["capture_started_at_utc"]]
    times += [r["received_at_utc"] for r in fetched["requests"]]
    parsed = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in times]
    assert before <= parsed[0] <= parsed[1] <= parsed[2] <= parsed[3] <= after
    assert fetched["captured_at_utc"] == fetched["requests"][-1]["received_at_utc"]
    assert all(timeout for _, _, timeout in session.calls)
    chain = parse_deribit_snapshot(fetched)
    assert (chain.index_price == 82227.73).all()
    assert json.loads(json.dumps(fetched)) == fetched  # saveable like the frozen file


@pytest.mark.parametrize("case", ["network", "rpc_error", "invalid_index"])
def test_fetch_failures_raise_one_error_type_with_the_reason(case):
    import requests
    from options_analytics.deribit import DeribitFetchError, fetch_deribit_snapshot

    raw = snapshot()
    index = "/api/v2/public/get_index_price"
    session = _ReplaySession(raw)
    if case == "network":
        session = _ReplaySession(raw, fail_on=index, error=requests.ConnectionError("offline"))
        reason = "offline"
    elif case == "rpc_error":
        session.responses[index] = {
            "jsonrpc": "2.0", "error": {"code": 10028, "message": "too_many_requests"},
        }
        reason = "too_many_requests"
    else:
        session.responses[index] = {"jsonrpc": "2.0", "testnet": False}
        reason = "JSON-RPC"
    with pytest.raises(DeribitFetchError, match=reason):
        fetch_deribit_snapshot(session=session)
