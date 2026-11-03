"""One-time capture of Deribit ticker greeks for the gamma check (spec check 1).

Captures a fresh snapshot in the frozen file's shape, then reads
``public/ticker`` for a sample of its contracts: for six expiries spread over
the term structure, the Call and Put at the listed strikes nearest 90%, 100%
and 110% of the index. Writes both to ``data/`` with capture times and request
params; the tests read them offline.

    .venv/bin/python -B experiments/capture_deribit_ticker_gamma.py
"""

import json
from pathlib import Path

import numpy as np
import requests

from iv_surface.deribit import (
    BASE_URL,
    _get_json,
    _utc_now_text,
    fetch_deribit_snapshot,
    parse_deribit_snapshot,
)

DATA = Path(__file__).resolve().parents[1] / "data"
SNAPSHOT_OUT = DATA / "deribit_btc_gamma_check_snapshot.json"
TICKERS_OUT = DATA / "deribit_btc_gamma_check_tickers.json"
EXPIRY_COUNT = 6
STRIKE_FRACTIONS = (0.9, 1.0, 1.1)


def sample_symbols(chain):
    index_price = float(chain["index_price"].iloc[0])
    taus = np.sort(chain["tau"].unique())
    picks = np.unique(np.linspace(0, len(taus) - 1, EXPIRY_COUNT).round().astype(int))
    symbols = []
    for tau in taus[picks]:
        rows = chain[chain["tau"] == tau]
        strikes = np.sort(rows["strike"].unique())
        for fraction in STRIKE_FRACTIONS:
            strike = strikes[np.abs(strikes - fraction * index_price).argmin()]
            for flag in ("call", "put"):
                match = rows[(rows["strike"] == strike) & (rows["flag"] == flag)]
                symbols.extend(match["symbol"].tolist())
    return sorted(set(symbols))


def main():
    session = requests.Session()
    snapshot = fetch_deribit_snapshot(session)
    chain = parse_deribit_snapshot(snapshot)
    started = _utc_now_text()
    tickers = []
    for symbol in sample_symbols(chain):
        params = {"instrument_name": symbol}
        payload = _get_json(session, "/api/v2/public/ticker", params)
        tickers.append({
            "endpoint": "/api/v2/public/ticker", "params": params,
            "received_at_utc": _utc_now_text(), "response": payload,
        })
    capture = {
        "schema_version": 1, "exchange": "deribit", "currency": "BTC",
        "purpose": "One-time ticker greeks capture for the per-contract gamma check.",
        "base_url": BASE_URL,
        "paired_snapshot": SNAPSHOT_OUT.name,
        "capture_started_at_utc": started,
        "captured_at_utc": tickers[-1]["received_at_utc"],
        "requests": tickers,
    }
    SNAPSHOT_OUT.write_text(json.dumps(snapshot, indent=1) + "\n", encoding="utf-8")
    TICKERS_OUT.write_text(json.dumps(capture, indent=1) + "\n", encoding="utf-8")
    print(f"{len(tickers)} tickers; snapshot {snapshot['captured_at_utc']}")


if __name__ == "__main__":
    main()
