"""How to read the bid–ask IV shading, shared by the smile and ATM charts."""

import streamlit as st

BAND_CAPTION = "shading = bid–ask IV band, wider where quotes are wider"

BAND_NOTES = (
    "At each strike the band belongs to the same option the line uses, shown "
    "as \"IV from\" in the hover: the Put below 0.98 K/S, the Call above "
    "1.02, and the Call–Put average in between. Where that side has no IV, "
    "the line and band both switch to the other side.",
    "The lower edge is the IV our solver implies from the best bid, the upper "
    "edge the IV from the best ask. Quote midpoint IV always sits between them.",
    "Width shows how far apart buyers and sellers are. A narrow band means the "
    "IV is well pinned by quotes; a wide band means the quotes leave the IV "
    "loose, so read the line there with caution.",
    "Where a strike's neighbours have no band, its band is a short vertical "
    "bar. Where the line continues with no shading, the bid or ask is missing "
    "or did not solve: short-dated far out-of-the-money contracts often have "
    "no bid, yet Exchange mark IV still exists there. In Quote midpoint the "
    "line can fall back to a deep in-the-money contract whose bid sits below "
    "intrinsic value; no volatility gives that price, so it has no bid IV.",
    "Within 2% of spot each edge is an average of two solved IVs: the lower "
    "edge averages the Call bid IV and the Put bid IV, the upper edge the Call "
    "ask IV and the Put ask IV. Each price is solved to IV first, because a "
    "Call and a Put at one strike have very different prices but comparable "
    "IVs. It is a display band, not a "
    "tradable quote; Exchange mark IV comes from Deribit's own model and can "
    "sit outside it.",
)


def band_expander():
    with st.expander("Reading the bid–ask shading"):
        for note in BAND_NOTES:
            st.caption(note)
