# -*- coding: utf-8 -*-
"""Fig. 10 and Fig. 11 of the revised manuscript.

Fig. 10: load-object Monte-Carlo with group-shared and idiosyncratic components
         (reports/dstatcom_montecarlo.json, stressed spread): (a) histogram of the per-draw
         minimum line-to-line voltage under the reactive local proxy; (b) mean injected
         reactive power and mean feeder loss of the three controls.
Fig. 11: net daily energy (feeder-loss saving minus converter loss) versus the converter
         loss at the assumed rating (reports/dstatcom_vscloss.json).
Writes figs/Fig10.pdf and figs/Fig11.pdf.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = ROOT / "figs"

plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True, "pdf.fonttype": 42,
                     "ps.fonttype": 42})
C = {"fixed": "#C0392B", "droop": "#2E74B5", "coord": "#2E7D32", "schedule": "#B8860B"}
MK = {"fixed": "o", "droop": "s", "coord": "^", "schedule": "D"}


def fig10():
    d = json.loads((REP / "dstatcom_montecarlo.json").read_text())
    ctrls = ("fixed", "schedule", "droop")
    cs = list(d["cases"].keys())[-1]                       # stressed spread
    rawkey = [k for k in d if k.startswith("raw_droop")][-1]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.0))
    mv = np.array(d[rawkey]["minv"])
    a1.hist(mv, bins=40, color="#2E74B5", edgecolor="white", alpha=0.85)
    a1.axvline(0.95, color="#C0392B", lw=1.6, ls="--")
    pv = 100.0 * np.mean(mv < 0.95)
    a1.text(0.951, a1.get_ylim()[1] * 0.55, f"0.95 pu\nP(viol)={pv:.1f}%",
            color="#C0392B", fontsize=8, va="center", ha="left", linespacing=2.1)
    a1.text(0.42, 0.97, f"worst {mv.min():.4f}\nmean {mv.mean():.4f}",
            transform=a1.transAxes, fontsize=8, va="top", ha="left")
    a1.set_xlabel("Min line-to-line voltage (pu)")
    a1.set_ylabel("MC samples")
    q = [d["cases"][cs][ct]["mean_total_kvar"] for ct in ctrls]
    ls = [d["cases"][cs][ct]["mean_feeder_loss_kW"] for ct in ctrls]
    xx = np.arange(len(ctrls))
    a2b = a2.twinx()
    a2.bar(xx, q, 0.55, color="#7C6BAE", edgecolor="white")
    a2b.plot(xx, ls, "o-", color="#C0392B", lw=1.8)
    a2.set_xticks(xx)
    a2.set_xticklabels(ctrls)
    a2.set_ylabel("Mean $\\Sigma Q$ (kvar)")
    a2b.set_ylabel("Mean feeder loss (kW)")
    a2.set_ylim(min(q) - 40, max(q) + 20)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    for ax, lab in ((a1, "(a)"), (a2, "(b)")):
        pos = ax.get_position()
        fig.text((pos.x0 + pos.x1) / 2, 0.015, lab, ha="center", va="bottom", fontsize=12)
    fig.savefig(OUT / "Fig10.pdf")
    plt.close(fig)


def fig11():
    d = json.loads((REP / "dstatcom_vscloss.json").read_text())
    lt = [float(x) for x in d["loss_model"]["L_tot_sweep"]]
    fig, ax = plt.subplots(figsize=(3.5, 2.9))
    for ctrl in ("fixed", "droop", "coord"):
        c = d["controls"][ctrl]
        net = [c["by_L_tot"][f"L_tot={v}"]["net_daily_energy_kWh"] for v in lt]
        ax.plot([x * 100 for x in lt], net, marker=MK[ctrl], color=C[ctrl],
                label=f"{ctrl} (BE {c['breakeven_L_tot_frac'] * 100:.1f}%)", lw=1.8, ms=5)
    ax.axhline(0, color="k", lw=0.9, ls="--")
    ax.set_xlabel("Converter loss at rating $L_{tot}$ (%)")
    ax.set_ylabel("Net daily energy (kWh/day)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3, fontsize=6.8,
              columnspacing=0.9, handlelength=1.4, handletextpad=0.4, frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "Fig11.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig10()
    fig11()
    print("saved", OUT / "Fig10.pdf", "and", OUT / "Fig11.pdf")
