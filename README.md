# US Treasury Rates Curve Monitor

A Python monitor for dislocations across the US Treasury curve. It rebuilds, on
public data, the principles of a curve monitor I built on the rates desk at
Crédit Agricole CIB during my Sales & Trading internship (the desk version ran
in Excel off live Bloomberg BDP/BDH feeds and screened the desk's contributed
quotes).

## What it does

1. **Pulls** daily par yields for 11 US Treasury tenors (1M to 30Y) from FRED —
   no API key needed.
2. **Builds** every curve structure from them: 11 outrights, all 55 pairwise
   spreads, and 18 curated butterflies (wings minus 2x body) — 84 structures.
3. **Scores** each structure against its own 1-year history with a z-score and
   computes 20-day realized vol of daily changes.
4. **Flags** dislocations: |z| ≥ 2.0 is `EXTREME`, |z| ≥ 1.5 is `STRETCHED`.
   Thresholds live in `config.py`, mirroring the desk-editable Config sheet of
   the original.
5. **Writes** a one-page daily findings note (`sample_output/`) — the Python
   version of the daily findings email the desk received. If an
   `ANTHROPIC_API_KEY` is set, the market-color paragraph is drafted by an LLM
   from the flagged table (numbers always come from the analytics, never the
   model); otherwise a deterministic template writes it.

A GitHub Actions workflow (`.github/workflows/daily.yml`) runs the monitor
every weekday evening and commits the findings note to the repo, so the
`sample_output/` folder becomes a growing archive of daily notes.

## Quick start

```bash
pip install -r requirements.txt
python monitor.py            # live FRED data
python monitor.py --demo     # synthetic data, runs offline
python monitor.py --no-llm   # skip the LLM even if a key is set
```

## Project layout

| File | Role (Excel-sheet equivalent) |
|---|---|
| `config.py` | Tenors, thresholds, lookbacks — the *Config* sheet |
| `monitor.py` | Data pull, structures, z-scores, flags — *Raw Data* + *Curve Analysis* |
| `commentary.py` | The daily findings note — the *Findings / Email* sheets |
| `sample_output/` | Daily notes archive |

## Method notes

* **Spread** = long tenor − short tenor, in bp. **Fly** = short + long − 2 ×
  body, so a positive fly means the body is cheap to the wings.
* Z-scores use the full 1-year window (a structure needs 120+ observations
  before it is scored), matching the original's `TODAY()-365` lookback.
* Realized vol is the standard deviation of daily changes over 20 trading
  days — the same vol input the desk version used to scale suggested
  bid/offer widths.
* Flags are screening signals for further work, not trade recommendations.

## Data

FRED constant-maturity Treasury series (`DGS1MO` … `DGS30`), pulled from the
public `fredgraph.csv` endpoint. Data is daily, percent, and lags the market
by one business day — fine for a daily monitor, not for intraday quoting (that
is what the Bloomberg version was for).
