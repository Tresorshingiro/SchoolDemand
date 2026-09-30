"""A check report: errors block Publish, warnings are for reading. Each problem keeps its first rows."""
from __future__ import annotations

import json

import pandas as pd


class Report:
    MAX_ROWS = 20  # example rows kept per problem in the report (all of them go to the issues CSV)

    def __init__(self) -> None:
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.changes: dict | None = None
        self.summary: dict = {}
        self._frames: list[pd.DataFrame] = []

    def error(self, code: str, message: str, rows: pd.DataFrame | None = None) -> None:
        self._add(self.errors, "error", code, message, rows)

    def warning(self, code: str, message: str, rows: pd.DataFrame | None = None) -> None:
        self._add(self.warnings, "warning", code, message, rows)

    def _add(self, bucket: list, severity: str, code: str, message: str, rows: pd.DataFrame | None) -> None:
        if rows is not None and rows.empty:
            return
        sample = json.loads(rows.head(self.MAX_ROWS).to_json(orient="records", date_format="iso")) if rows is not None else []
        bucket.append({"code": code, "message": message, "count": len(rows) if rows is not None else 1, "rows": sample})
        if rows is not None:
            self._frames.append(rows.assign(severity=severity, problem=message))

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_json(self) -> dict:
        return {"errors": self.errors, "warnings": self.warnings, "changes": self.changes, "summary": self.summary}

    def issues(self) -> pd.DataFrame:
        """Every row concerned by a problem (for the CSV download), severity and problem first."""
        if not self._frames:
            return pd.DataFrame(columns=["severity", "problem"])
        t = pd.concat(self._frames, ignore_index=True)
        return t[["severity", "problem", *[c for c in t.columns if c not in ("severity", "problem")]]]
