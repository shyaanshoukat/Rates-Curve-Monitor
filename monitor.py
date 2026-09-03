"""
US Treasury Rates Curve Monitor
================================
A Python rebuild of the Rates Curve Monitor I built on the rates desk at
Crédit Agricole CIB (the original ran in Excel off live Bloomberg BDP/BDH
feeds). Same principles, public data:

  1. Pull daily par yields for 11 Treasury tenors (FRED, no API key).
  2. Build every curve structure: outrights, all pairwise spreads, and a
     curated set of butterflies (wings minus 2x body).
  3. Z-score each structure against a 1-year history and compute 20-day
     realized vol of daily changes.
  4. Flag dislocations beyond configurable thresholds (2 SD = EXTREME,
     1.5 SD = STRETCHED), exactly as the desk version flagged quotes.
  5. Write a one-page daily findings note (optionally drafted by an LLM).

Usage:
    python monitor.py               # live data from FRED
    python monitor.py --demo        # synthetic data, runs offline
    python monitor.py --no-llm      # skip the LLM, use the template note

Author: Shyaan Shoukat
"""

import argparse
import io
import sys
from datetime import date, timedelta
from itertools import combinations

import numpy as np
import pandas as pd

import config
from commentary import write_findings


# ---------------------------------------------------------------------------
# 1. Data  (the "Raw Data" sheet)
# ---------------------------------------------------------------------------

def fetch_history() -> pd.DataFrame:
    """Pull daily par yields for all tenors from FRED's keyless CSV endpoint.

    Returns a DataFrame indexed by date with one column per tenor, in percent.
    """
    import requests

    ids = ",".join(config.TENORS.values())
    url = config.FRED_CSV_URL.format(ids=ids)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise SystemExit(
            f"Could not reach FRED ({e.__class__.__name__}). Check your "
            "internet connection, or run 'python monitor.py --demo' to see "
            "the monitor work on synthetic data."
        ) from e

    df = pd.read_csv(io.StringIO(resp.text))
    date_col = df.columns[0]  # FRED names it 'observation_date'
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)

    # Rename FRED series IDs back to tenor labels and coerce to numeric
    # (FRED marks holidays with '.').
    id_to_tenor = {v: k for k, v in config.TENORS.items()}
    df = df.rename(columns=id_to_tenor)
    df = df.apply(pd.to_numeric, errors="coerce")

    cutoff = pd.Timestamp(date.today() - timedelta(days=config.LOOKBACK_DAYS))
    df = df[df.index >= cutoff].dropna(how="all")
    return df[list(config.TENORS.keys())]


def demo_history(seed: int = 7) -> pd.DataFrame:
    """Synthetic yield history so the monitor runs offline (tests, demos).

    Random-walks each tenor around a plausible starting curve with
    correlated daily moves, so z-scores and flags behave realistically.
    """
    rng = np.random.default_rng(seed)
    tenors = list(config.TENORS.keys())
    start = {"1M": 4.90, "3M": 4.80, "6M": 4.65, "1Y": 4.40, "2Y": 4.10,
             "3Y": 4.00, "5Y": 3.95, "7Y": 4.00, "10Y": 4.10, "20Y": 4.45,
             "30Y": 4.35}
    days = pd.bdate_range(end=date.today(), periods=260)
    common = rng.normal(0, 0.035, len(days))          # level factor
    slope = rng.normal(0, 0.02, len(days))            # slope factor
    data = {}
    for i, t in enumerate(tenors):
        idio = rng.normal(0, 0.015, len(days))
        w = (i - len(tenors) / 2) / len(tenors)       # slope loading
        path = start[t] + np.cumsum(common + w * slope + idio)
        data[t] = np.round(path, 2)
    return pd.DataFrame(data, index=days)


# ---------------------------------------------------------------------------
# 2. Structures  (outrights, spreads, flies — the "Curve Analysis" sheet)
# ---------------------------------------------------------------------------

def build_structures(hist: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame of daily levels for every curve structure, in bp.

    Outrights are kept in percent x100 (bp) for comparability.
    Spread  = long tenor minus short tenor.
    Fly     = wings minus 2x body  (short + long - 2*mid).
    """
    tenors = list(hist.columns)
    out = {}

    for t in tenors:                                   # outrights
        out[t] = hist[t] * 100

    for a, b in combinations(tenors, 2):               # all pairwise spreads
        out[f"{a}/{b}"] = (hist[b] - hist[a]) * 100

    for a, b, c in config.FLIES:                       # curated butterflies
        out[f"{a}/{b}/{c}"] = (hist[a] + hist[c] - 2 * hist[b]) * 100

    return pd.DataFrame(out, index=hist.index)


# ---------------------------------------------------------------------------
# 3. Analytics  (z-scores, changes, realized vol)
# ---------------------------------------------------------------------------

def analyze(levels: pd.DataFrame) -> pd.DataFrame:
    """One row per structure: live level, changes, z-score, vol, flag."""
    rows = []
    for name, series in levels.items():
        s = series.dropna()
        if len(s) < config.MIN_HISTORY:
            continue

        live = s.iloc[-1]
        mean, std = s.mean(), s.std()
        z = (live - mean) / std if std > 0 else np.nan

        chg_1d = live - s.iloc[-2]
        idx_1m = max(0, len(s) - 1 - config.MONTHLY_OFFSET_ROWS)
        chg_1m = live - s.iloc[idx_1m]

        daily_moves = s.diff().dropna()
        vol_20d = daily_moves.tail(config.VOL_WINDOW).std()

        if abs(z) >= config.Z_FLAG:
            flag = "EXTREME"
        elif abs(z) >= config.Z_BUILDING:
            flag = "STRETCHED"
        else:
            flag = ""

        kind = "fly" if name.count("/") == 2 else ("spread" if "/" in name
                                                   else "outright")
        rows.append({
            "structure": name, "type": kind, "level_bp": round(live, 1),
            "chg_1d_bp": round(chg_1d, 1), "chg_1m_bp": round(chg_1m, 1),
            "mean_1y": round(mean, 1), "z": round(z, 2),
            "vol_20d_bp": round(vol_20d, 2), "flag": flag,
        })

    cols = ["structure", "type", "level_bp", "chg_1d_bp", "chg_1m_bp",
            "mean_1y", "z", "vol_20d_bp", "flag"]
    if not rows:                      # nothing had enough history to score
        return pd.DataFrame(columns=cols).set_index("structure")

    df = pd.DataFrame(rows, columns=cols).set_index("structure")
    return df.sort_values("z", key=abs, ascending=False)


# ---------------------------------------------------------------------------
# 4. Run
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="US Treasury curve monitor")
    ap.add_argument("--demo", action="store_true",
                    help="run on synthetic data (offline)")
    ap.add_argument("--no-llm", action="store_true",
                    help="always use the template note, never call an LLM")
    args = ap.parse_args()

    print("Loading yield history...")
    hist = demo_history() if args.demo else fetch_history()
    print(f"  {len(hist)} days x {len(hist.columns)} tenors "
          f"({hist.index[0].date()} to {hist.index[-1].date()})")

    levels = build_structures(hist)
    print(f"  {levels.shape[1]} structures built "
          f"({len(hist.columns)} outrights, "
          f"{sum(1 for c in levels if c.count('/') == 1)} spreads, "
          f"{sum(1 for c in levels if c.count('/') == 2)} flies)")

    table = analyze(levels)
    flagged = table[table["flag"] != ""]
    print(f"  {len(flagged)} structures flagged beyond "
          f"{config.Z_BUILDING} SD ({(table['flag'] == 'EXTREME').sum()} EXTREME)")

    path = write_findings(table, hist, use_llm=not args.no_llm,
                          demo=args.demo)
    print(f"\nFindings note written to {path}\n")
    print(table.head(12).to_string())


if __name__ == "__main__":
    sys.exit(main())
