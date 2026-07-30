"""
Build the static dashboard export (dashboard/dashboard.png).

Layout mirrors the Looker Studio dashboard used for stakeholder reporting:
a KPI header row plus four panels (volume trend, volume by room, category mix,
repeat rate by configuration). Run after generate_data.py.

Usage: python scripts/build_dashboard.py
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

# --- Palette (colorblind-validated categorical slots + ink roles) -----------
CONFIG_COLORS = {
    "nvx_standard": "#2a78d6",
    "legacy_matrix_v1": "#eb6834",
    "nvx_early": "#1baf7a",
}
CONFIG_LABELS = {
    "nvx_standard": "NVX standard",
    "legacy_matrix_v1": "Legacy matrix",
    "nvx_early": "NVX early rollout",
}
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"

plt.rcParams.update({
    "figure.facecolor": "#f9f9f7", "axes.facecolor": "white",
    "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK_2,
    "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "font.family": "sans-serif", "font.size": 10,
})

SIGNAL_SUBS = ["No display / HDMI handshake", "Input switching failure"]


def load():
    raw = pd.read_csv("data/av_tickets.csv", parse_dates=["created_at", "resolved_at"])
    rooms = pd.read_csv("data/classrooms.csv")

    t = raw[raw.created_by != "25Live"].copy()          # drop scheduling automation
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
    t = t.merge(rooms[["classroom_id", "config_variant"]], on="classroom_id", how="left")
    att = t[t.has_room].sort_values("created_at")
    prev = att.groupby(["classroom_id", "subcategory"])["created_at"].shift()
    t["is_repeat"] = ((att["created_at"] - prev).le(pd.Timedelta(days=14))
                      .reindex(t.index, fill_value=False))
    t["month"] = t["created_at"].dt.to_period("M").dt.to_timestamp()
    return raw, t, rooms


def kpi(ax, value, label, sub, accent=INK):
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, facecolor="white",
                               edgecolor="#e1e0d9", linewidth=1))
    ax.text(0.07, 0.68, value, transform=ax.transAxes, fontsize=20,
            fontweight="bold", color=accent, va="center")
    ax.text(0.07, 0.36, label, transform=ax.transAxes, fontsize=10,
            color=INK, va="center", fontweight="bold")
    ax.text(0.07, 0.16, sub, transform=ax.transAxes, fontsize=8.5,
            color=MUTED, va="center")


def main():
    raw, t, rooms = load()
    att = t[t.has_room]
    resolved = t[t.resolved_at.notna()]

    med_res_h = resolved["resolution_time_minutes"].median() / 60
    rep = att.groupby("config_variant")["is_repeat"].mean()
    legacy_att = att[att.config_variant == "legacy_matrix_v1"]
    other_share = att[att.config_variant != "legacy_matrix_v1"].subcategory.isin(SIGNAL_SUBS).mean()
    excess = (legacy_att.subcategory.isin(SIGNAL_SUBS).sum()
              - other_share * len(legacy_att))
    months = (t.created_at.max() - t.created_at.min()).days / 30.4

    fig = plt.figure(figsize=(15, 10.5))
    gs = GridSpec(3, 4, figure=fig, height_ratios=[0.55, 1.25, 1.25],
                  hspace=0.42, wspace=0.28,
                  left=0.055, right=0.97, top=0.86, bottom=0.06)

    fig.text(0.055, 0.955, "Classroom AV Support — Operations Dashboard",
             fontsize=17, fontweight="bold", color=INK)
    fig.text(0.055, 0.925, "Jan 2025 – Jun 2026 · 22 classrooms · "
             "SYNTHETIC DEMONSTRATION DATA, calibrated to real aggregate shapes (see README)",
             fontsize=10, color=MUTED)

    # --- KPI row ---
    kpi(fig.add_subplot(gs[0, 0]), f"{len(t):,}", "AV support tickets (18 mo)",
        f"after removing {1 - len(t)/len(raw):.0%} scheduling-sync noise")
    kpi(fig.add_subplot(gs[0, 1]), f"{med_res_h:.0f} h", "Median resolution (calendar)",
        "queue time included; half resolve same-day")
    kpi(fig.add_subplot(gs[0, 2]),
        f"{rep['legacy_matrix_v1']:.0%} vs {rep['nvx_standard']:.0%}",
        "14-day repeat rate", "legacy-matrix vs NVX-standard rooms",
        accent="#d95926")
    kpi(fig.add_subplot(gs[0, 3]), f"~{excess * 12 / months:.0f} / yr",
        "Excess display-signal tickets", "in 5 legacy rooms vs baseline rate",
        accent="#d95926")

    # --- Panel 1: monthly volume ---
    ax = fig.add_subplot(gs[1, :2])
    monthly = t.groupby("month").size()
    ax.plot(monthly.index, monthly.values, color="#2a78d6", linewidth=2,
            marker="o", markersize=4.5, markerfacecolor="white", markeredgewidth=1.5)
    ax.grid(axis="x", visible=False); ax.set_axisbelow(True)
    ax.set_title("Monthly ticket volume — spring peaks, summer & December troughs", loc="left")
    ax.set_ylim(0, monthly.max() * 1.2)
    ax.set_ylabel("Tickets")
    for x, lbl in [("2025-04-01", "spring peak"), ("2026-04-01", "spring peak"),
                   ("2025-08-01", "summer trough")]:
        xd = pd.Timestamp(x)
        ax.annotate(lbl, xy=(xd, monthly[xd]), xytext=(0, 10),
                    textcoords="offset points", ha="center", fontsize=8, color=MUTED)

    # --- Panel 2: volume by room (top 12, attributed) ---
    ax = fig.add_subplot(gs[1, 2:])
    by_room = (att.groupby(["classroom_id", "config_variant"]).size()
               .reset_index(name="n").nlargest(12, "n").sort_values("n"))
    ax.barh(by_room["classroom_id"], by_room["n"],
            color=by_room["config_variant"].map(CONFIG_COLORS), height=0.6)
    ax.grid(axis="y", visible=False); ax.set_axisbelow(True)
    ax.set_title("Top 12 rooms by ticket volume (room-attributed tickets)", loc="left")
    ax.set_xlabel("Tickets (18 mo)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=CONFIG_COLORS[k]) for k in CONFIG_LABELS]
    ax.legend(handles, CONFIG_LABELS.values(), frameon=False, loc="lower right",
              fontsize=8.5, title="AV configuration", title_fontsize=8.5)

    # --- Panel 3: category mix ---
    ax = fig.add_subplot(gs[2, :2])
    cats = t.groupby("category").size().sort_values()
    colors = ["#eb6834" if c == "AV Technical Support" else "#9ec5f4" for c in cats.index]
    ax.barh(cats.index, cats.values, color=colors, height=0.58)
    ax.grid(axis="y", visible=False); ax.set_axisbelow(True)
    for i, v in enumerate(cats.values):
        ax.text(v + 3, i, f"{v}", va="center", fontsize=9, color=INK_2)
    ax.set_title("Tickets by category — AV technical & lecture capture lead", loc="left")
    ax.set_xlim(0, cats.max() * 1.12)
    ax.set_xlabel("Tickets (18 mo)")

    # --- Panel 4: repeat rate by configuration ---
    ax = fig.add_subplot(gs[2, 2:])
    rr = rep.reindex(["nvx_early", "nvx_standard", "legacy_matrix_v1"])
    labels = [CONFIG_LABELS[k] for k in rr.index]
    ax.barh(labels, rr.values, color=[CONFIG_COLORS[k] for k in rr.index], height=0.5)
    ax.grid(axis="y", visible=False); ax.set_axisbelow(True)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    for i, v in enumerate(rr.values):
        ax.text(v + 0.008, i, f"{v:.0%}", va="center", fontsize=10, color=INK_2)
    ax.set_title("Repeat-ticket rate (same room + issue within 14 days)", loc="left")
    ax.set_xlim(0, rr.max() * 1.28)
    ax.set_xlabel("Repeat rate")

    fig.savefig("dashboard/dashboard.png", dpi=150, bbox_inches="tight", pad_inches=0.25)
    print("wrote dashboard/dashboard.png")


if __name__ == "__main__":
    main()
