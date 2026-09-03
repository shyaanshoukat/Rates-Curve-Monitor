"""
Findings note generator — the "daily findings email" of the Excel version.

Two modes:
  * Template mode (default, always works): builds the note from the analytics
    table with deterministic rules. No keys, no network.
  * LLM mode: if an ANTHROPIC_API_KEY environment variable is set, the note's
    market-color paragraph is drafted by Claude from the flagged structures,
    then checked and framed by the same template skeleton. The numbers always
    come from the analytics table, never from the model.
"""

import os
from datetime import date

import pandas as pd

import config


def _direction(z: float) -> str:
    return "rich/high vs 1y history" if z > 0 else "cheap/low vs 1y history"


def _template_paragraph(flagged: pd.DataFrame) -> str:
    if flagged.empty:
        return ("No structures are trading beyond the flag thresholds today. "
                "The curve sits inside its 1-year ranges across outrights, "
                "spreads, and flies.")
    lines = []
    for name, row in flagged.head(config.TOP_N).iterrows():
        lines.append(
            f"{name} at {row.level_bp}bp is {abs(row.z):.1f} standard "
            f"deviations {_direction(row.z)} ({row.chg_1d_bp:+.1f}bp on the "
            f"day, {row.chg_1m_bp:+.1f}bp on the month, 20d vol "
            f"{row.vol_20d_bp}bp)."
        )
    return " ".join(lines)


def _llm_paragraph(flagged: pd.DataFrame) -> str | None:
    """Ask Claude to draft the color paragraph. Returns None on any failure
    so the template path always backs it up."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or flagged.empty:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        table = flagged.head(config.TOP_N).to_string()
        msg = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "You are drafting one paragraph of a rates desk morning "
                    "note. Using ONLY the numbers in this table of flagged US "
                    "Treasury curve structures (levels in bp, z vs 1-year "
                    "history), write a tight, professional paragraph a trader "
                    "reads in 30 seconds. No advice, no invented numbers.\n\n"
                    + table
                ),
            }],
        )
        return msg.content[0].text.strip()
    except Exception:
        return None


def write_findings(table: pd.DataFrame, hist: pd.DataFrame,
                   use_llm: bool = True, demo: bool = False) -> str:
    """Assemble and write the daily findings note; return the file path."""
    today = date.today().isoformat()
    flagged = table[table["flag"] != ""]
    extreme = table[table["flag"] == "EXTREME"]

    para = (_llm_paragraph(flagged) if use_llm else None) \
        or _template_paragraph(flagged)

    front = hist.iloc[-1]
    twos, tens, thirties = front.get("2Y"), front.get("10Y"), front.get("30Y")

    lines = [
        f"# Rates Curve Monitor — Daily Findings ({today})",
        "",
        "*" + ("DEMO DATA — synthetic history, not live market levels. "
               if demo else "") +
        f"Universe: {len(table)} structures | "
        f"Flags: {len(flagged)} ({len(extreme)} EXTREME) | "
        f"Thresholds: {config.Z_BUILDING}/{config.Z_FLAG} SD*",
        "",
        "## Curve snapshot",
        f"2Y {twos:.2f}%  |  10Y {tens:.2f}%  |  30Y {thirties:.2f}%  |  "
        f"2s10s {(tens - twos) * 100:.0f}bp  |  "
        f"10s30s {(thirties - tens) * 100:.0f}bp",
        "",
        "## Dislocations",
        para,
        "",
        "## Flagged structures",
        "",
        (flagged.head(config.TOP_N).to_markdown()
         if not flagged.empty else "_None today._"),
        "",
        "---",
        "*Levels in bp. z = standard deviations vs 1-year history. "
        "Flags are screening signals, not trade recommendations.*",
    ]

    os.makedirs(config.FINDINGS_DIR, exist_ok=True)
    path = os.path.join(config.FINDINGS_DIR, f"findings_{today}.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path
