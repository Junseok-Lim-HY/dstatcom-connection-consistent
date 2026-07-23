"""Faithful, data-accurate reproduction of the Fig. 1 workflow overview.

Every panel uses the paper's ACTUAL data/topology so the figure is consistent
with the manuscript (seven selected buses 740/741/711/738/737/735/736; real
IEEE 37-node one-line geometry with bus labels; measured optimizer convergence;
the real 24-h optimal-dispatch envelope). Layout is placed inside four colored
frames with generous margins so no axis/label overflows its box.
Output: paper/ieee_access/figs/fig1_overall.pdf/png.
"""
from __future__ import annotations
import csv, json, re
from pathlib import Path

import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch

import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
DSSDIR = ROOT / "data" / "raw" / "ieee37_dss"
MASTER = (DSSDIR / "Master.DSS").resolve()
REP = ROOT / "reports"
OUT = ROOT / "paper" / "ieee_access" / "figs"

SEL = ["735", "740", "741"]                                    # 3 D-STATCOM buses (canonical)
# major trunk/junction buses to annotate (kept sparse to avoid clutter;
# the dense downstream cluster is left unlabelled except the E-STATCOM buses)
TRUNK = ["701", "702", "703", "704", "733", "734"]

mpl.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 13,
    "axes.titlesize": 13, "axes.labelsize": 13.5,
    "xtick.labelsize": 11.5, "ytick.labelsize": 11.5, "legend.fontsize": 11.5,
    "axes.linewidth": 1.0, "figure.dpi": 300, "savefig.dpi": 300,
    "svg.fonttype": "none",   # keep text as editable text in SVG (PowerPoint/Illustrator)
})
C1, C2, C3, C4 = "#2E5E9E", "#D9832B", "#3C8C52", "#7A55A6"
TINT = {C1: "#EAF1F9", C2: "#FDF1E4", C3: "#EAF5EE", C4: "#F1ECF7"}
TITLE_FS = 15


def title_bar(ax, text, color):
    ax.set_title(text, color="white", fontweight="bold", fontsize=TITLE_FS,
                 bbox=dict(boxstyle="round,pad=0.34", fc=color, ec="none"),
                 loc="center", pad=8)


# ---------- data ----------
def screening_topN(n=10):
    """Read the canonical ten-bus line-to-line screening CSV (single source)."""
    import csv
    rows = list(csv.DictReader(open(REP / "dstatcom_screening.csv")))
    ranked = [(r["bus"], float(r["worst_min"])) for r in rows]
    ranked.sort(key=lambda kv: kv[1])
    return ranked[:n]


def read_coords():
    xy = {}
    with (DSSDIR / "IEEE37_BusXY.csv").open() as fh:
        for line in fh:
            p = [t.strip() for t in line.split(",")]
            if len(p) >= 3:
                try:
                    xy[p[0].lower()] = (float(p[1]), float(p[2]))
                except ValueError:
                    pass
    return xy


def read_edges():
    txt = (DSSDIR / "Master.DSS").read_text()
    edges = [(m.group(1).lower(), m.group(2).lower())
             for m in re.finditer(r"Bus1=(\w+)[.\d]*\s+Bus2=(\w+)", txt, re.I)]
    edges += [("sourcebus", "799"), ("799", "799r"), ("709", "775")]
    return edges


# ---------- panels ----------
def panel_system(ax):
    title_bar(ax, "①  System model", C1)
    xy, edges = read_coords(), read_edges()
    for a, b in edges:
        if a in xy and b in xy:
            ax.plot([xy[a][0], xy[b][0]], [xy[a][1], xy[b][1]],
                    color="#8c8c8c", lw=1.3, zorder=1)
    xs = [p[0] for p in xy.values()]; ys = [p[1] for p in xy.values()]
    ax.scatter(xs, ys, s=16, color="#4a4a4a", zorder=2)
    for b in SEL:
        if b in xy:
            ax.scatter(*xy[b], s=120, color=C3, edgecolor="#1e3d2b",
                       linewidth=1.0, zorder=3)
    # substation
    if "799" in xy:
        ax.scatter(*xy["799"], marker="s", s=160, color="#333",
                   edgecolor="k", zorder=4)
        ax.annotate("Substation (799)", xy["799"], textcoords="offset points",
                    xytext=(11, 1), fontsize=11.5, fontweight="bold", zorder=6)
    # spread-out trunk buses are labelled individually (no overlap)
    for b in TRUNK:
        if b in xy:
            ax.annotate(b, xy[b], textcoords="offset points", xytext=(7, 5),
                        fontsize=10, color="#555", zorder=5)
    # the seven E-STATCOM buses form a tight downstream cluster -> single callout
    cx = float(np.mean([xy[b][0] for b in SEL if b in xy]))
    cy = float(np.mean([xy[b][1] for b in SEL if b in xy]))
    ax.annotate("D-STATCOM buses\n735, 740, 741",
                xy=(cx, cy), xycoords="data",
                xytext=(0.60, 0.26), textcoords="axes fraction",
                fontsize=10.5, color="#1e3d2b", fontweight="bold",
                ha="left", va="center", linespacing=1.35,
                bbox=dict(boxstyle="round,pad=0.35", fc="#EAF5EE", ec=C3, lw=1.4),
                arrowprops=dict(arrowstyle="-|>", color=C3, lw=1.8,
                                connectionstyle="arc3,rad=-0.2"), zorder=7)
    ax.set_xticks([]); ax.set_yticks([])
    ax.margins(x=0.30, y=0.10)
    for s in ax.spines.values():
        s.set_visible(False)


def panel_screening(ax):
    title_bar(ax, "②  Voltage screening", C2)
    ranked = screening_topN(10)
    buses = [b for b, _ in ranked][::-1]
    vals = [v for _, v in ranked][::-1]
    ypos = np.arange(len(buses))
    for y, b, v in zip(ypos, buses, vals):
        sel = b in SEL
        ax.barh(y, v, color=("#C0392B" if sel else "#B9C0C9"),
                edgecolor=("#7d1d13" if sel else "#7a828b"),
                hatch=("///" if sel else ""), linewidth=0.8, zorder=3)
    ax.axvline(0.95, color="#C0392B", ls="--", lw=1.6, zorder=4)
    ax.text(0.9505, 1.0, "0.95 pu limit", color="#C0392B", fontsize=11,
            rotation=90, va="bottom", ha="right")
    ax.set_yticks(ypos); ax.set_yticklabels(buses, fontsize=11)
    ax.set_xlim(0.86, 0.965)
    ax.set_xticks([0.88, 0.90, 0.92, 0.94, 0.96])
    ax.set_xlabel("Worst-case min. line-to-line voltage (pu)")
    ax.set_ylabel("Candidate bus")
    handles = [Patch(fc="#C0392B", ec="#7d1d13", hatch="///", label="Selected (3)"),
               Patch(fc="#B9C0C9", ec="#7a828b", label="Other candidates")]
    ax.legend(handles=handles, loc="lower right", fontsize=10.5,
              frameon=True, framealpha=0.92)
    ax.grid(axis="x", color="#d5d5d5", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def panel_sizing(ax):
    # Canonical method = full enumeration of all 120 three-device supports, each
    # sized to minimum kvar; the lowest-capacity feasible support is adopted.
    title_bar(ax, "③  Enumerate 120 supports", C3)
    d = json.load(open(REP / "dstatcom_canonical.json"))
    alls = d["all_supports"]
    kv = np.array([r["total_kvar"] for r in alls])
    feas = np.array([r["feasible"] for r in alls])
    x = np.arange(len(kv))
    if np.any(~feas):
        ax.scatter(x[~feas], kv[~feas], s=10, color="#B9C0C9",
                   label="not achieved under budget", zorder=2)
    ax.scatter(x[feas], kv[feas], s=12, color=C3,
               label=f"feasible supports ({int(feas.sum())})", zorder=3)
    ci = int(np.argmin([r["total_kvar"] if r["feasible"] else 1e9 for r in alls]))
    ax.scatter([ci], [kv[ci]], s=110, marker="*", color="#C0392B",
               edgecolor="#7d1d13", linewidth=0.8, zorder=5,
               label="operational case (1041.3 kvar)")
    ax.set_xlabel("Support (sorted by total kvar)")
    ax.set_ylabel("Total installed kvar")
    ax.legend(loc="lower right", fontsize=10.5, frameon=True, framealpha=0.92)
    ax.grid(color="#d5d5d5", lw=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def panel_dispatch(ax_v, ax_q):
    title_bar(ax_v, "④  Hourly dispatch", C4)
    rows = list(csv.DictReader(open(REP / "dstatcom_operation_24h.csv")))
    h = [int(r["hour"]) for r in rows]
    vmin = [float(r["coord_min"]) for r in rows]
    vmax = [float(r["coord_max"]) for r in rows]
    qk = [float(r["coord_kvar"]) for r in rows]
    ax_v.fill_between(h, vmin, vmax, color=C1, alpha=0.16, zorder=1)
    ax_v.plot(h, vmax, color="#C0392B", lw=2.0, label=r"$v_{\max}(t)$")
    ax_v.plot(h, vmin, color="#2E5E9E", lw=2.0, label=r"$v_{\min}(t)$")
    ax_v.axhline(1.05, color="#C0392B", ls="--", lw=1.4)
    ax_v.axhline(0.95, color="#C0392B", ls="--", lw=1.4)
    ax_v.text(0.6, 1.053, "1.05 pu", color="#C0392B", fontsize=10, va="bottom")
    ax_v.text(0.6, 0.947, "0.95 pu", color="#C0392B", fontsize=10, va="top")
    ax_v.set_ylim(0.93, 1.075)
    ax_v.set_xlim(0, 23)
    ax_v.set_ylabel("Voltage (pu)")
    ax_v.set_xticklabels([])
    ax_v.legend(loc="center left", fontsize=10.5, ncol=2, frameon=True,
                framealpha=0.92, columnspacing=1.0, handlelength=1.3)
    ax_v.grid(color="#d5d5d5", lw=0.6)
    for s in ("top", "right"):
        ax_v.spines[s].set_visible(False)
    ax_q.bar(h, np.array(qk) / 1000.0, color=C4, alpha=0.78,
             edgecolor="#4a3163", linewidth=0.6)
    ax_q.set_xlim(0, 23)
    ax_q.set_xlabel("Time (hour)")
    ax_q.set_ylabel(r"$\sum_i Q_i(t)$" "\n(Mvar)")
    ax_q.grid(axis="y", color="#d5d5d5", lw=0.6)
    for s in ("top", "right"):
        ax_q.spines[s].set_visible(False)


def main():
    fig = plt.figure(figsize=(15.0, 7.8))
    fw, y0, fh = 0.227, 0.10, 0.74
    fx = [0.018, 0.263, 0.508, 0.753]
    for x0, c in zip(fx, [C1, C2, C3, C4]):
        fig.add_artist(FancyBboxPatch((x0, y0), fw, fh,
                       boxstyle="round,pad=0.004,rounding_size=0.012",
                       transform=fig.transFigure, fc=TINT[c], ec=c, lw=2.0, zorder=0))
    fig.text(0.5, 0.955, "Voltage-security-oriented planning & operation",
             ha="center", fontsize=19, fontweight="bold")
    fig.text(0.5, 0.905,
             r"Primary planning target:  $\min\,|S|$,  then  $\min\,\sum_i Q_i^{\max}$,"
             r"  s.t.  $0.9562 \leq v_m \leq 1.0438$ pu at $\lambda=1.34$",
             ha="center", fontsize=15)
    # panel-1 caption (two lines; panel 1 has no x-axis label, so there is room)
    fig.text(fx[0] + fw / 2, y0 + 0.018,
             "IEEE 37-node radial feeder\nconstant-$Q$,  $0\\leq Q_i\\leq Q_i^{\\max}$",
             ha="center", va="bottom", fontsize=11, style="italic",
             color="#1a1a1a", linespacing=1.3)
    # panels 3 and 4 captions (single line; sit just below the x-axis label)
    fig.text(fx[2] + fw / 2, y0 + 0.006,
             "verified-feasible $\\to$ operational case",
             ha="center", fontsize=10.0, style="italic", color="#1a1a1a")
    fig.text(fx[3] + fw / 2, y0 + 0.006, "0.95–1.05 pu band",
             ha="center", fontsize=10.0, style="italic", color=C4, fontweight="bold")
    fig.text(0.5, 0.028,
             "Unlike a fixed capacitor ($Q\\propto V^2$), the constant-$Q$ converter "
             "output is set by control and is validated by\nhourly dispatch against "
             "the 0.95–1.05 pu band.", ha="center", fontsize=13, style="italic")

    ax1 = fig.add_axes([fx[0] + 0.020, y0 + 0.085, fw - 0.036, fh - 0.20])
    ax2 = fig.add_axes([fx[1] + 0.052, y0 + 0.120, fw - 0.072, fh - 0.245])
    ax3 = fig.add_axes([fx[2] + 0.054, y0 + 0.120, fw - 0.074, fh - 0.245])
    ax4v = fig.add_axes([fx[3] + 0.052, y0 + 0.380, fw - 0.072, fh - 0.505])
    ax4q = fig.add_axes([fx[3] + 0.052, y0 + 0.110, fw - 0.072, fh - 0.560])

    panel_system(ax1)
    panel_screening(ax2)
    panel_sizing(ax3)
    panel_dispatch(ax4v, ax4q)

    fig.savefig(OUT / "fig1_overall.pdf")
    fig.savefig(OUT / "fig1_overall.png")
    fig.savefig(OUT / "fig1_overall.svg")   # fully editable vector (PowerPoint/Illustrator/Inkscape)
    print("wrote fig1_overall.pdf/png/svg")


if __name__ == "__main__":
    main()
