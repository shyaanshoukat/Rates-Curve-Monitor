"""
Sanity tests for the curve monitor. Run with: python test_monitor.py

These check the maths that everything else depends on — if a spread or a fly
is built wrong, every z-score and flag downstream is wrong too.
"""

import numpy as np
import pandas as pd

import config
from monitor import analyze, build_structures, demo_history


def test_spread_and_fly_maths():
    """Spreads and flies must be built from the yields exactly as defined."""
    hist = pd.DataFrame(
        {t: [1.0 + i * 0.1] * 200 for i, t in enumerate(config.TENORS)},
        index=pd.bdate_range(end="2026-01-01", periods=200),
    )
    # Perturb so the last row differs from history
    hist.iloc[-1] = hist.iloc[-1] + 0.5

    levels = build_structures(hist)

    # 2Y is index 4 (1.4%), 10Y is index 8 (1.8%) -> spread = 40bp
    assert abs(levels["2Y/10Y"].iloc[0] - 40.0) < 1e-6, "spread maths wrong"

    # Fly = short + long - 2*body. With an evenly spaced curve every fly
    # built from equally spaced tenors should be flat at 0.
    assert abs(levels["2Y/3Y/5Y"].iloc[0] - 0.0) < 1e-6, "fly maths wrong"
    print("PASS  spread and fly construction")


def test_structure_count():
    """11 outrights + 55 pairwise spreads + 18 curated flies = 84."""
    levels = build_structures(demo_history())
    n_out = sum(1 for c in levels if "/" not in c)
    n_spr = sum(1 for c in levels if c.count("/") == 1)
    n_fly = sum(1 for c in levels if c.count("/") == 2)
    assert n_out == len(config.TENORS), f"expected 11 outrights, got {n_out}"
    assert n_spr == 55, f"expected 55 spreads, got {n_spr}"
    assert n_fly == len(config.FLIES), f"expected 18 flies, got {n_fly}"
    print(f"PASS  structure count ({n_out} + {n_spr} + {n_fly} = "
          f"{n_out + n_spr + n_fly})")


def test_zscore_and_flags():
    """A structure sitting at its mean scores ~0; a spike breaches 2 SD."""
    idx = pd.bdate_range(end="2026-01-01", periods=200)
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 1, 199)
    noise -= noise.mean()                      # centre the history on 50.0

    # Last value equals the historical mean -> z should be ~0, no flag.
    calm = pd.Series(np.r_[50.0 + noise, 50.0], index=idx)
    # Last value 10 SD-ish above the mean -> z should breach 2 SD.
    spike = pd.Series(np.r_[50.0 + noise, 60.0], index=idx)

    table = analyze(pd.DataFrame({"CALM": calm, "SPIKE": spike}))

    assert abs(table.loc["CALM", "z"]) < 0.1, "at-mean series should score ~0"
    assert table.loc["CALM", "flag"] == "", "at-mean series should not flag"
    assert table.loc["SPIKE", "z"] > config.Z_FLAG, "spike should breach 2 SD"
    assert table.loc["SPIKE", "flag"] == "EXTREME", "spike should flag EXTREME"
    print("PASS  z-scores and flag thresholds")


def test_min_history_filter():
    """Structures with too little history are dropped, not scored on noise."""
    idx = pd.bdate_range(end="2026-01-01", periods=config.MIN_HISTORY - 10)
    short = pd.DataFrame({"SHORT": np.arange(len(idx), dtype=float)}, index=idx)
    assert analyze(short).empty, "short history should be filtered out"
    print("PASS  minimum-history filter")


if __name__ == "__main__":
    test_spread_and_fly_maths()
    test_structure_count()
    test_zscore_and_flags()
    test_min_history_filter()
    print("\nAll tests passed.")
