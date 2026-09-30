"""The physical room ID (test_code) of each class group."""
from __future__ import annotations

import pandas as pd


def room_ids(df: pd.DataFrame) -> pd.Series:
    """Room ID from classroom_id, per school. A room recorded with 3 or more class groups is a data-entry error (a room
    holds at most a morning and an afternoon session): it becomes one room per group (<id>#1, #2 ...). A class group
    without classroom_id gets a room of its own (row-<file row>). Reproduces Version 2.xlsx's test_code."""
    cid = df["classroom_id"]
    present = cid.notna() & (cid.astype(str).str.strip() != "")
    text = cid.astype(str).str.strip()
    key = df["school_code"].astype(str) + "|" + text
    n = key.map(key[present].value_counts()).fillna(0)
    seq = df.groupby(key, dropna=False).cumcount() + 1  # a missing id is a missing key in pandas 3: keep integers
    out = text.where(n <= 2, text + "#" + seq.astype(str))
    return out.where(present, "row-" + df["row"].astype(str))
