# 04: Net gamma exposure below OI

**What to build:** A Gamma Exposure bar chart sits directly below OI, sharing its strike axis, current-price line, expiry selection and zoom. It shows Net GEX in USD per 1% BTC move under the default assumption Call+ / Put− (Calls customer sells, Puts customer buys), computed from Exchange mark IV.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] A one-time capture of Deribit ticker data for a sample of contracts is stored as test data, and our per-contract gamma from `mark_iv` matches Deribit's ticker gamma within a stated per-contract relative tolerance after converting Deribit's basis (spec check 1).
- [ ] Gamma uses each contract's own maturity and `mark_iv`, with the index and every forward moving 1% together; Combined or interpolated IV is never used.
- [ ] A test computes one real contract's contribution `s × gamma × OI × X² × 0.01` step by step and matches the app (spec check 2).
- [ ] Each strike's bar equals the sum of its contracts' contributions (spec check 3, Net part).
- [ ] OI and GEX zoom together and stay aligned by strike.
- [ ] The chart label says GEX uses Exchange mark IV, shows the unit and the active assumption, and shows the computable OI share.
- [ ] Hover shows the value, unit and the strike's details.
