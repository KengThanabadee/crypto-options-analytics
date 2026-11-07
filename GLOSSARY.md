# Crypto options analytics

Analytics on a Deribit BTC options snapshot: open interest, gamma exposure and
implied volatility.

## Language

**Moneyness**:
A strike's position relative to spot, `K / S`, where `S` is the Deribit index
price. A moneyness of 1.25 is a strike 25% above spot.
_Avoid_: forward moneyness, strike ratio

**Log-moneyness**:
The natural log of moneyness, `ln(K / S)`. A strike at half of spot and one at
twice spot are the same distance from spot in log-moneyness.
_Avoid_: log-strike

**Moneyness range**:
The named moneyness window the IV surface shows: Core (0.8–1.2), Wide
(0.5–2.0) or All listed (every strike listed in the snapshot).
_Avoid_: strike range (that is the open-interest chart's USD window)
