"""Print strike coverage and quote quality of a Deribit snapshot by K / S.

    python scripts/snapshot_coverage.py [snapshot.json] [--range Wide]
        [--source "Quote midpoint"]

Two tables, both on the OTM side the Combined IV wings use (puts below spot,
calls at or above it):

- by K / S bucket: listed contracts, two-sided quotes, Quote midpoint solves,
  Exchange mark IVs, median relative spread, open interest and expiries;
- by expiry: the listed K / S span, and observed, interpolated and blank cells
  of the 2D surface over ``--range``, as the dashboard draws it: ``--range``
  takes a range name (Core, Wide, All listed) or LOW HIGH bounds, and
  ``--source`` the IV source (default Exchange mark).

Defaults to the frozen snapshot in data/.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from options_analytics import deribit, iv_source
from options_analytics.surface_transforms import (
    MONEYNESS_RANGES,
    interpolate_surface_2d,
    moneyness_range_bounds,
    moneyness_range_slice,
)

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


def by_expiry(chain, frame, moneyness_range, source):
    """Cell counts by expiry over a range name or (low, high), and the bounds."""
    result = iv_source.build_iv_source_surface(
        chain, source, bid_ask_iv=iv_source.solve_bid_ask_iv(chain)
    )
    # Build the whole surface, then slice the range, as the dashboard does.
    surface = interpolate_surface_2d(iv_source.iv_source_long_frame(result))
    if isinstance(moneyness_range, str):
        low, high = moneyness_range_bounds(moneyness_range, surface)
    else:
        low, high = moneyness_range
    surface = moneyness_range_slice(surface, low, high)
    cells = surface.groupby("tau")["surface_value_type"].value_counts().unstack(fill_value=0)
    span = frame.groupby("tau").agg(
        expiry=("expiry_dt", "first"),
        listed_low=("moneyness", "min"),
        listed_high=("moneyness", "max"),
    )
    table = span.join(cells).reset_index(drop=True).set_index("expiry")
    blank = (int(cells.get("Missing", 0).sum()), int(cells.to_numpy().sum()))
    return table.round(2), blank, (low, high)


def parse_range(values):
    """A range name, or two numbers LOW HIGH."""
    text = " ".join(values)
    if text in MONEYNESS_RANGES:
        return text
    try:
        low, high = (float(value) for value in values)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--range takes one of {', '.join(MONEYNESS_RANGES)} or LOW HIGH"
        ) from None
    return low, high


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("snapshot", nargs="?", default=SNAPSHOT, type=Path)
    parser.add_argument(
        "--range", nargs="+", default=["Core"], metavar="RANGE",
        help=(
            "K / S range of the surface cell counts: Core, Wide, All listed, "
            "or LOW HIGH (default: Core)"
        ),
    )
    parser.add_argument(
        "--source", choices=iv_source.IV_SOURCES, default="Exchange mark",
        help="IV source of the surface cell counts (default: Exchange mark)",
    )
    args = parser.parse_args()
    try:
        moneyness_range = parse_range(args.range)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    chain = deribit.parse_deribit_snapshot(deribit.load_deribit_snapshot(args.snapshot))
    frame = otm_contracts(chain)
    print(f"Index {chain['index_price'].iloc[0]:,.2f} · OTM contracts by K / S\n")
    print(by_bucket(frame).to_string())
    table, blank, (low, high) = by_expiry(chain, frame, moneyness_range, args.source)
    print(
        f"\nSurface cells by expiry, {args.source}, K / S {low:.2f}–{high:.2f} "
        f"· {blank[0]} of {blank[1]} cells blank ({blank[0] / blank[1]:.0%})\n"
    )
    print(table.to_string())


if __name__ == "__main__":
    main()
