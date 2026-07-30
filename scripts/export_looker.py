"""
Export an analysis-ready flat table for Looker Studio / Tableau.

Applies the same cleaning as the notebook (automation filter, dedup, trim,
canonical categories, room join) and pre-computes the flags the dashboard
needs (repeat, display-signal, resolution bands), so BI charts require no
calculated fields.

Output: dashboard/looker/av_tickets_looker.csv

Usage: python scripts/export_looker.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SIGNAL_SUBS = ["No display / HDMI handshake", "Input switching failure"]
CONFIG_LABELS = {
    "nvx_standard": "NVX standard (2023)",
    "legacy_matrix_v1": "Legacy matrix (2017)",
    "nvx_early": "NVX early rollout (2021)",
}


def main():
    raw = pd.read_csv("data/av_tickets.csv", parse_dates=["created_at", "resolved_at"])
    rooms = pd.read_csv("data/classrooms.csv")

    # Same cleaning pipeline as the notebook
    t = raw[raw.created_by != "25Live"].copy()
    t["classroom_id"] = t["classroom_id"].fillna("").str.strip()
    canon = {c.lower(): c for c in ["AV Technical Support", "Lecture Capture",
                                    "Webconferencing", "Equipment Maintenance & Repair",
                                    "Setup & Configuration", "Consultation"]}
    t["category"] = t["category"].str.lower().map(canon)
    t = t.sort_values("created_at")
    has_room = t["classroom_id"] != ""
    gap = t[has_room].groupby(["classroom_id", "subcategory"])["created_at"].diff()
    dup = gap.le(pd.Timedelta(minutes=15)).reindex(t.index, fill_value=False)
    t = t[~dup].copy()
    t["has_room"] = t["classroom_id"] != ""
    t = t.merge(rooms[["classroom_id", "seats", "config_variant"]],
                on="classroom_id", how="left", validate="many_to_one")

    att = t[t.has_room].sort_values("created_at")
    prev = att.groupby(["classroom_id", "subcategory"])["created_at"].shift()
    t["is_repeat"] = ((att["created_at"] - prev).le(pd.Timedelta(days=14))
                      .reindex(t.index, fill_value=False))

    # BI-friendly derived columns (no calculated fields needed in Looker Studio)
    res_hours = t.resolution_time_minutes / 60
    out = pd.DataFrame({
        "ticket_id": t.ticket_id,
        "created_date": t.created_at.dt.strftime("%Y-%m-%d"),
        "created_hour": t.created_at.dt.hour,
        "created_weekday": t.created_at.dt.day_name(),
        "classroom": t.classroom_id.replace("", "Unattributed"),
        "room_attributed": np.where(t.has_room, "Yes", "No"),
        "av_configuration": t.config_variant.map(CONFIG_LABELS).fillna("Unattributed"),
        "category": t.category,
        "subcategory": t.subcategory,
        "is_display_signal": np.where(t.subcategory.isin(SIGNAL_SUBS), "Yes", "No"),
        "is_repeat_14d": np.where(t.is_repeat, "Yes", "No"),
        "status": np.where(t.resolved_at.isna(), "Open", "Resolved"),
        "resolution_hours": res_hours.round(2),
        "resolution_band": pd.cut(
            res_hours,
            bins=[0, 1, 24, 168, np.inf],
            labels=["Under 1 hour", "Same day (1-24h)", "Within a week", "Over a week"],
        ).cat.add_categories("Open").fillna("Open"),
        "requester": t.created_by,
        "assigned_technician": t.assigned_technician,
    })

    dest = Path("dashboard/looker")
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "av_tickets_looker.csv"
    out.to_csv(path, index=False)
    print(f"Wrote {len(out):,} rows x {len(out.columns)} columns to {path}\n")
    print(out.head(3).to_string())


if __name__ == "__main__":
    main()
