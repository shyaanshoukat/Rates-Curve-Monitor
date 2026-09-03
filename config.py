"""
Config — single source of truth, mirroring the Config sheet of the original
Excel Rates Curve Monitor built on the CACIB rates desk.

Everything the monitor flags is controlled from here, so thresholds can be
tuned without touching the engine (the desk's request in the Excel version).
"""

# --- Data ---------------------------------------------------------------
# FRED series IDs for US Treasury constant-maturity par yields.
# fredgraph.csv is a public endpoint: no API key required.
TENORS = {
    "1M":  "DGS1MO",
    "3M":  "DGS3MO",
    "6M":  "DGS6MO",
    "1Y":  "DGS1",
    "2Y":  "DGS2",
    "3Y":  "DGS3",
    "5Y":  "DGS5",
    "7Y":  "DGS7",
    "10Y": "DGS10",
    "20Y": "DGS20",
    "30Y": "DGS30",
}

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}"

# --- Lookbacks ----------------------------------------------------------
LOOKBACK_DAYS = 365          # z-score and vol history window (calendar days)
MONTHLY_OFFSET_ROWS = 21     # trading days back for the 1M change column
VOL_WINDOW = 20              # trading days for realized vol of daily changes

# --- Flag thresholds (the desk-editable numbers) ------------------------
Z_FLAG = 2.0                 # |z| beyond this = EXTREME flag
Z_BUILDING = 1.5             # |z| beyond this = STRETCHED (watch list)
MIN_HISTORY = 120            # require this many observations before z-scoring

# --- Butterflies --------------------------------------------------------
# Curated flies: the classics the desk actually watches, wings x2 body.
FLIES = [
    ("1M", "3M", "6M"), ("3M", "6M", "1Y"), ("6M", "1Y", "2Y"),
    ("1Y", "2Y", "3Y"), ("2Y", "3Y", "5Y"), ("3Y", "5Y", "7Y"),
    ("5Y", "7Y", "10Y"), ("7Y", "10Y", "20Y"), ("10Y", "20Y", "30Y"),
    ("2Y", "5Y", "10Y"), ("2Y", "10Y", "30Y"), ("5Y", "10Y", "30Y"),
    ("1Y", "5Y", "10Y"), ("2Y", "5Y", "30Y"), ("3Y", "10Y", "30Y"),
    ("1Y", "2Y", "5Y"), ("2Y", "7Y", "30Y"), ("1Y", "10Y", "30Y"),
]

# --- Output -------------------------------------------------------------
FINDINGS_DIR = "sample_output"   # where the daily findings note is written
TOP_N = 8                        # max structures quoted in the findings note
