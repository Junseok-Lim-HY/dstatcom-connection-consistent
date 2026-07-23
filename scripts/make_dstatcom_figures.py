"""Regenerate the manuscript figures from the connection-aware (D-STATCOM) results.

Reads the new report files and writes Fig2/Fig5-Fig12 (pdf+png) into
paper/ieee_access/figs/, matching the manuscript's data. Fig3/Fig4 (optimizer)
are produced by make_dstatcom_optfigs.py once the sizing-optimizer run completes.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = ROOT / "paper" / "ieee_access" / "figs"
OUT.mkdir(parents=True, exist_ok=True)

mpl.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9.5, "axes.titlesize": 10,
    "axes.labelsize": 9.5, "xtick.labelsize": 8.8, "ytick.labelsize": 8.8,
    "legend.fontsize": 8.3, "axes.linewidth": 0.9, "axes.edgecolor": "#2b2b2b",
    "axes.axisbelow": True, "axes.grid": True, "grid.color": "#c9c9c9",
    "grid.linewidth": 0.6, "grid.alpha": 0.7, "figure.dpi": 400, "savefig.dpi": 400,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.03, "hatch.linewidth": 0.6,
})
BLUE, ORANGE, GREEN, RED, PURPLE = "#3B6FB0", "#E08214", "#4A9E5C", "#C0392B", "#7D5BA6"
SC, DC = (3.5, 2.55), (7.0, 3.0)


def rd(name):
    with (REP / name).open(encoding="utf-8") as h:
        return list(csv.DictReader(h))


def save(fig, stem):
    fig.savefig(OUT / (stem + ".pdf"))
    fig.savefig(OUT / (stem + ".png"))
    plt.close(fig)
    print("wrote", stem)


def style_ax(ax):
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)


def leg_top(ax, ncol=2, handles=None, labels=None):
    kw = dict(loc="lower center", bbox_to_anchor=(0.5, 1.005), ncol=ncol,
              frameon=False, fontsize=8.2, columnspacing=1.3, handletextpad=0.5,
              borderaxespad=0.15)
    if handles is not None:
        if labels is None:
            labels = [h.get_label() for h in handles]
        ax.legend(handles, labels, **kw)
    else:
        ax.legend(**kw)


def fig2_screening():
    r = rd("dstatcom_screening.csv")
    buses = [x["bus"] for x in r]
    vv = [float(x["worst_min"]) for x in r]
    sel = {"735", "740", "741"}
    fig, ax = plt.subplots(figsize=DC)
    for i, (b, v) in enumerate(zip(buses, vv)):
        chosen = b in sel
        ax.bar(i, v, width=0.72, color=BLUE if chosen else "#B9C6D6",
               edgecolor="#1d2d44", linewidth=0.8, hatch="////" if chosen else "", zorder=3)
    ax.axhline(0.95, color=RED, lw=1.3, ls="--", zorder=4)
    ax.set_xticks(range(len(buses))); ax.set_xticklabels(buses)
    ax.set_ylim(0.88, 0.96)
    ax.set_xlabel("Candidate bus"); ax.set_ylabel("Worst-case min. line-to-line voltage (pu)")
    leg_top(ax, ncol=3, handles=[
        Patch(facecolor=BLUE, hatch="////", edgecolor="#1d2d44", label="Selected (3)"),
        Patch(facecolor="#B9C6D6", edgecolor="#1d2d44", label="Not selected"),
        plt.Line2D([], [], color=RED, ls="--", label="0.95 pu limit")])
    style_ax(ax); save(fig, "Fig2")


def fig5_design():
    c = json.loads((REP / "dstatcom_canonical.json").read_text())["canonical"]
    buses = c["support"]; q = c["q_kvar"]
    fig, ax = plt.subplots(figsize=SC)
    for i, v in enumerate(q):
        ax.bar(i, v, width=0.6, color=GREEN, edgecolor="#1e3d2b", linewidth=0.8,
               hatch="xxxx", zorder=3)
        ax.text(i, v + 6, f"{v:.0f}", ha="center", va="bottom", fontsize=7.6)
    ax.axhline(450, color=RED, lw=1.1, ls="--", label="Per-bus bound (450 kvar)")
    ax.set_xticks(range(len(buses))); ax.set_xticklabels(buses)
    ax.set_ylim(0, 500)
    ax.set_xlabel("Selected bus"); ax.set_ylabel("Installed $Q^{max}$ (kvar)")
    leg_top(ax, ncol=1); style_ax(ax); save(fig, "Fig5")


def fig6_count():
    cs = json.loads((REP / "dstatcom_certsweep.json").read_text())
    # n=1,2 are v_best (best achievable min); n=3 is the canonical operating point,
    # shown with a DISTINCT marker so the two quantities are not mixed on one curve.
    mv = [cs["one_device"]["max_v_best"], cs["two_device"]["max_v_best"]]
    fig, ax = plt.subplots(figsize=SC)
    ax.bar([0, 1], mv, width=0.5, color=ORANGE, edgecolor="#7a4a12", linewidth=0.8,
           hatch="\\\\\\\\", zorder=3, label=r"$v_{\mathrm{best}}$ (1--2 devices)")
    ax.scatter([2], [0.9563], marker="D", s=70, color=GREEN, edgecolor="#1e3d2b",
               zorder=5, label="Canonical witness (op. min., 3 dev.)")
    ax.axhline(0.9562, color=RED, lw=1.1, ls="--", zorder=4, label="0.9562 pu acceptance")
    ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["1", "2", "3"])
    ax.set_xlabel("Device count $n$")
    ax.set_ylabel("Worst min. line-to-line $v$ (pu)")
    ax.set_ylim(0.90, 0.962)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    leg_top(ax, ncol=1)
    save(fig, "Fig6")


def fig7_current():
    c = json.loads((REP / "dstatcom_canonical.json").read_text())["canonical"]
    buses = c["support"]; ic = c["dev_current_a"]; rated = c["dev_benchmark_a"]
    x = np.arange(len(buses)); w = 0.36
    fig, ax = plt.subplots(figsize=SC)
    ax.bar(x - w / 2, ic, width=w, color=BLUE, edgecolor="#1d2d44", linewidth=0.8,
           hatch="////", zorder=3, label="Peak $|I_i|$")
    ax.bar(x + w / 2, rated, width=w, color="#B9C6D6", edgecolor="#1d2d44",
           linewidth=0.8, zorder=3, label=r"Derived benchmark $I_i^{\mathrm{ben}}$")
    ax.set_xticks(x); ax.set_xticklabels([f"bus {b}" for b in buses])
    ax.set_ylim(0, max(max(rated), max(ic)) * 1.25)
    ax.set_ylabel("Per-phase current (A)")
    leg_top(ax, ncol=2); style_ax(ax); save(fig, "Fig7")


def _op():
    return rd("dstatcom_operation_24h.csv")


def fig8_envelope():
    r = _op()
    h = [int(x["hour"]) for x in r]
    mn = [float(x["coord_min"]) for x in r]
    mx = [float(x["coord_max"]) for x in r]
    kv = [float(x["coord_kvar"]) for x in r]
    fig, ax = plt.subplots(figsize=DC)
    ax.fill_between(h, mn, mx, color=BLUE, alpha=0.14, zorder=1, label="Voltage envelope")
    ax.plot(h, mx, color=RED, lw=1.6, marker="^", ms=3.5, label="Max voltage", zorder=3)
    ax.plot(h, mn, color=BLUE, lw=1.6, marker="v", ms=3.5, label="Min voltage", zorder=3)
    ax.axhline(0.95, color="#555", lw=1.0, ls="--", zorder=2)
    ax.axhline(1.05, color="#555", lw=1.0, ls="--", zorder=2)
    ax.set_ylim(0.94, 1.06); ax.set_xlim(0, 23)
    ax.set_xlabel("Hour"); ax.set_ylabel("Line-to-line voltage (pu)")
    ax2 = ax.twinx(); ax2.grid(False)
    ax2.bar(h, kv, width=0.7, color=GREEN, alpha=0.30, edgecolor="#1e3d2b",
            linewidth=0.4, hatch="....", zorder=0, label="Dispatched kvar")
    ax2.set_ylabel("Dispatched reactive power (kvar)", color="#1e3d2b")
    ax2.set_ylim(0, 1200); ax2.tick_params(axis="y", colors="#1e3d2b")
    ax.spines["top"].set_visible(False); ax2.spines["top"].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    leg_top(ax, ncol=4, handles=h1 + h2, labels=l1 + l2)
    save(fig, "Fig8")


def fig9_maxv():
    r = _op()
    h = [int(x["hour"]) for x in r]
    fmax = [float(x["fixed_max"]) for x in r]
    cmax = [float(x["cap_max"]) for x in r]
    omax = [float(x["coord_max"]) for x in r]
    fig, ax = plt.subplots(figsize=DC)
    ax.plot(h, fmax, color=RED, lw=1.7, marker="s", ms=3.5, label="Fixed full output")
    ax.plot(h, cmax, color=ORANGE, lw=1.7, marker="d", ms=3.5, label="Fixed capacitor")
    ax.plot(h, omax, color=GREEN, lw=1.7, marker="o", ms=3.5, label="Coordinated (band-only)")
    ax.axhline(1.05, color="#555", lw=1.1, ls="--", label="1.05 pu limit")
    ax.set_ylim(1.00, 1.06); ax.set_xlim(0, 23)
    ax.set_xlabel("Hour"); ax.set_ylabel("Maximum line-to-line voltage (pu)")
    leg_top(ax, ncol=2); style_ax(ax); save(fig, "Fig9")


def fig10_minv():
    r = _op()
    h = [int(x["hour"]) for x in r]
    b = [float(x["base_min"]) for x in r]
    a = [float(x["coord_min"]) for x in r]
    fig, ax = plt.subplots(figsize=DC)
    ax.fill_between(h, b, a, color=GREEN, alpha=0.18, zorder=1, label="Improvement")
    ax.plot(h, b, color="#555", lw=1.7, marker="o", ms=3.5, label="Base case (no device)")
    ax.plot(h, a, color=BLUE, lw=1.8, marker="v", ms=3.5, label="Coordinated (band-only)")
    ax.axhline(0.95, color=RED, lw=1.1, ls="--", label="0.95 pu limit")
    ax.set_ylim(0.88, 1.01); ax.set_xlim(0, 23)
    ax.set_xlabel("Hour"); ax.set_ylabel("Minimum line-to-line voltage (pu)")
    leg_top(ax, ncol=3); style_ax(ax); save(fig, "Fig10")


def fig11_cap():
    r = _op()
    h = [int(x["hour"]) for x in r]
    cap = [float(x["cap_max"]) for x in r]
    est = [float(x["fixed_max"]) for x in r]
    fig, ax = plt.subplots(figsize=SC)
    ax.plot(h, cap, color=ORANGE, lw=1.8, marker="s", ms=3.5, label="Fixed capacitor")
    ax.plot(h, est, color=BLUE, lw=1.8, marker="o", ms=3.5, label="Constant-$Q$ converter")
    ax.axhline(1.05, color=RED, lw=1.0, ls="--", label="1.05 pu limit")
    ax.set_ylim(1.00, 1.06); ax.set_xlim(0, 23)
    ax.set_xlabel("Hour"); ax.set_ylabel("Max. line-to-line voltage (pu)")
    leg_top(ax, ncol=1); style_ax(ax); save(fig, "Fig11")


def fig12_droop():
    r = _op()
    h = [int(x["hour"]) for x in r]
    fixed = [1067.0 for _ in r]
    droop = [float(x["droop_kvar"]) for x in r]
    coord = [float(x["coord_kvar"]) for x in r]
    fig, ax = plt.subplots(figsize=SC)
    ax.plot(h, fixed, color=RED, lw=1.6, ls="--", label="Fixed full output")
    ax.plot(h, droop, color=BLUE, lw=1.8, marker="v", ms=3.3, label="Local Volt/VAR proxy")
    ax.plot(h, coord, color=GREEN, lw=1.8, marker="o", ms=3.3, label="Coordinated (band-only)")
    ax.set_ylim(0, 1150); ax.set_xlim(0, 23)
    ax.set_xlabel("Hour"); ax.set_ylabel("Dispatched reactive power (kvar)")
    leg_top(ax, ncol=1); style_ax(ax); save(fig, "Fig12")


if __name__ == "__main__":
    fig2_screening(); fig5_design(); fig6_count(); fig7_current()
    fig8_envelope(); fig9_maxv(); fig10_minv(); fig11_cap(); fig12_droop()
    print("done")
