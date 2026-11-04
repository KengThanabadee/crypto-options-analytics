import numpy as np
import pytest
from options_analytics.solver import bs_price, solve_iv

def test_solve_iv_round_trip():
    spot_price = 100
    K = 100
    T = 1
    r = 0.03
    sigma = 0.2
    flag = "call"

    option_price = bs_price(spot_price, K, T, r, sigma, flag)
    implied_vol = solve_iv(option_price, spot_price, K, T, r, flag)
    assert abs(implied_vol - sigma) < 1e-4

def test_solve_iv_bad_price():
    with pytest.raises(ValueError):
        solve_iv(101, 100, 100, 1, 0.03, "call")

def test_solve_iv_rejects_non_finite_price():
    with pytest.raises(ValueError):
        solve_iv(np.inf, 100, 100, 1, 0.03, "call")

    with pytest.raises(ValueError):
        solve_iv(-np.inf, 100, 100, 1, 0.03, "call")

    with pytest.raises(ValueError):
        solve_iv(np.nan, 100, 100, 1, 0.03, "call")

def test_solve_iv_returns_lower_bracket_endpoint():
    spot_price = 100
    K = 100
    T = 1
    r = 0.03
    sigma_low = 1e-6
    flag = "call"

    option_price = bs_price(spot_price, K, T, r, sigma_low, flag)
    implied_vol = solve_iv(option_price, spot_price, K, T, r, flag)

    assert abs(implied_vol - sigma_low) < 1e-4

def test_solve_iv_returns_upper_bracket_endpoint():
    spot_price = 100
    K = 100
    T = 1
    r = 0.03
    sigma_high = 10.0
    flag = "call"

    option_price = bs_price(spot_price, K, T, r, sigma_high, flag)
    implied_vol = solve_iv(option_price, spot_price, K, T, r, flag)

    assert abs(implied_vol - sigma_high) < 1e-4

def test_solve_iv_rejects_expired_option():
    with pytest.raises(ValueError):
        solve_iv(0, 100, 100, 0, 0.03, "call")

def test_solve_iv_rejects_non_finite_inputs():
    cases = [
        {"option_price": 10, "spot_price": np.nan, "K": 100, "T": 1, "r": 0.03, "flag": "call"},
        {"option_price": 10, "spot_price": 100, "K": np.nan, "T": 1, "r": 0.03, "flag": "call"},
        {"option_price": 10, "spot_price": 100, "K": 100, "T": np.nan, "r": 0.03, "flag": "call"},
        {"option_price": 10, "spot_price": 100, "K": 100, "T": 1, "r": np.nan, "flag": "call"},
    ]

    for kwargs in cases:
        with pytest.raises(ValueError):
            solve_iv(**kwargs)
