"""Small repetition / dropout workbooks in the MINEDUC layout (no database needed)."""
import pandas as pd


def sheet(title: str, rows: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """A sheet as pandas reads it with header=None: rows = {district: (average 2022/23, average 2023/24)}."""
    head = [[None] * 8, [None, "Level", title, None, None, None, None, None],
            [None, None, "2022/23", None, None, "2023/24", None, None],
            [None, None, "Male", "Female", "Average", "Male", "Female", "Average"]]
    body = [[None, d, 0, 0, a, 0, 0, b] for d, (a, b) in rows.items()]
    return pd.DataFrame(head + body)


def two_sheets(gasabo: tuple[float, float] = (0.107, 0.035), rwanda: bool = True) -> dict[str, pd.DataFrame]:
    """Both sheets with Gasabo (repetition, dropout in 2023/24) and, unless rwanda=False, the Rwanda row."""
    rep = {"Gasabo": (0.25, gasabo[0])}
    drop = {"Gasabo": (0.04, gasabo[1])}
    if rwanda:
        rep["Rwanda"], drop["Rwanda"] = (0.3, 0.204), (0.05, 0.049)
    return {"Repetition Rate": sheet("Repetion rate", rep), "Dropout Rate": sheet("Dropout Rate", drop)}
