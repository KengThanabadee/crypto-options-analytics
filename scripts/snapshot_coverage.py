"""Print strike coverage and quote quality of a Deribit snapshot by K / S.

    python scripts/snapshot_coverage.py [snapshot.json] [--range 0.5 2.0]

Two tables, both on the OTM side the Combined IV wings use (puts below spot,
calls at or above it):

- by K / S bucket: listed contracts, two-sided quotes, Quote midpoint solves,
  Exchange mark IVs, median relative spread, open interest and expiries;
- by expiry: the listed K / S span, and observed, interpolated and blank cells
  of the 2D surface over ``--range``, as the dashboard draws it.

Defaults to the frozen snapshot in data/.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from options_analytics import deribit, iv_source
from options_analytics.surface_transforms import interpolate_surface_2d, moneyness_range_slice

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "deribit_btc_options_snapshot.json"
BUCKETS = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0, 3.0, np.inf]


def otm_contracts(chain):
    moneyness = chain["strike"] / chain["index_price"]
    otm = ((moneyness < 1) & chain["flag"].eq("put")) | (
        (moneyness >= 1) & chain["flag"].eq("call")
    )
    frame = chain.assign(moneyness=moneyness)
    frame["quote_iv"] = iv_source.contract_iv(chain, "Quote midpoint").to_numpy()
    frame["mark"] = iv_source.contract_iv(chain, "Exchange mark").to_numpy()
    return frame[otm]


def by_bucket(frame):
    two_sided = frame["bid_price_btc"].gt(0) & frame["ask_price_btc"].gt(0)
    spread = (frame["ask_price_btc"] - frame["bid_price_btc"]) / frame["mid_price_btc"]
    table = frame.assign(
        bucket=pd.cut(frame["moneyness"], BUCKETS),
        two_sided=two_sided,
        spread=spread.where(two_sided),
    ).groupby("bucket", observed=True).agg(
        contracts=("moneyness", "size"),
        two_sided=("two_sided", "sum"),
        quote_iv=("quote_iv", "count"),
        mark_iv=("mark", "count"),
        median_spread=("spread", "median"),
        open_interest=("open_interest", "sum"),
        expiries=("tau", "nunique"),
    )
    table["median_spread"] = table["median_spread"].map("{:.0%}".format)
    table.index.name = "K / S"
    return table


def by_expiry(chain, frame, low, high):
    result = iv_source.build_iv_source_surface(
        chain, "Exchange mark", bid_ask_iv=iv_source.solve_bid_ask_iv(chain)
    )
    # Build the whole surface, then slice the range, as the dashboard does.
    surface = moneyness_range_slice(
        interpolate_surface_2d(iv_source.iv_source_long_frame(result)), low, high
    )
    cells = surface.groupby("tau")["surface_value_type"].value_counts().unstack(fill_value=0)
    span = frame.groupby("tau").agg(
        expiry=("expiry_dt", "first"),
        listed_low=("moneyness", "min"),
        listed_high=("moneyness", "max"),
    )
    table = span.join(cells).reset_index(drop=True).set_index("expiry")
    blank = cells.get("Missing", 0).sum() / cells.to_numpy().sum()
    return table.round(2), blank


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("snapshot", nargs="?", default=SNAPSHOT, type=Path)
    parser.add_argument(
        "--range", nargs=2, type=float, default=(0.8, 1.2), metavar=("LOW", "HIGH"),
        help="K / S range of the surface cell counts (default: Core, 0.8 1.2)",
    )
    args = parser.parse_args()
    chain = deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot(args.snapshot))
    frame = otm_contracts(chain)
    print(f"Index {chain['index_price'].iloc[0]:,.2f} · OTM contracts by K / S\n")
    print(by_bucket(frame).to_string())
    low, high = args.range
    table, blank = by_expiry(chain, frame, low, high)
    print(f"\nSurface cells by expiry, K / S {low}–{high} · {blank:.0%} blank\n")
    print(table.to_string())


if __name__ == "__main__":
    main()
