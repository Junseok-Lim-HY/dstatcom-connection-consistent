# -*- coding: utf-8 -*-
"""Fig. 4 of the revised manuscript: candidate-pool and device-count sensitivity.

Reads reports/dstatcom_poolsens.json (written by run_dstatcom_poolsens.py) and writes
figs/Fig4.pdf in the layout used in the IEEE Access revision:

  (a) supports for which a feasible vector was found, for n = 1 and 2 over all eligible
      three-phase buses and n = 3 over the 20-bus pool;
  (b) best known capacity per pool size (the canonical 1041.3-kvar design, re-verified
      feasible in the pool-sensitivity evaluator by check_baseline_in_poolsens.py) versus
      the pool study's own three-seed result, with "found / tried" bar labels.

Bar labels are search successes under a fixed per-support budget, not feasibility counts.
"""
import json
from math import comb
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "dstatcom_poolsens.json"
OUT = ROOT / "figs"

# canonical design re-verified in the pool evaluator (reports/check_baseline_in_poolsens.log)
CANON_KVAR = 1041.3

plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True, "pdf.fonttype": 42,
                     "ps.fonttype": 42})
C_CANON, C_POOL, C_BAR, C_BARLAB = "#2E74B5", "#B8860B", "#C9D6EA", "#4A6FA5"


def main():
    d = json.loads(REPORT.read_text())
    ks = d["n3_pools"]
    nfeas = [d["n3_per_pool"][str(k)]["n3_feasible"] for k in ks]
    tried = [comb(k, 3) for k in ks]
    pool_best = d["n3_per_pool"][str(ks[-1])]["n3_best"]["total_kvar"]
    nb = d["n_eligible_buses"]
    n1, n2 = len(d.get("n1_feasible", [])), d["n2_feasible_count"]

    fig = plt.figure(figsize=(3.5, 6.3))
    left, right_b, right_a = 0.25, 0.76, 0.96
    a1 = fig.add_axes([left, 0.64, right_a - left, 0.335])
    a2 = fig.add_axes([left, 0.10, right_b - left, 0.32])

    # (a) device count over all eligible buses
    cnts = [n1, n2, nfeas[-1]]
    a1.bar([1, 2, 3], cnts, 0.6, color=["#C0392B", "#C0392B", "#2E7D32"], edgecolor="white")
    for x, v in zip([1, 2, 3], cnts):
        a1.annotate(f"{v}", (x, v), textcoords="offset points", xytext=(0, 4), ha="center",
                    fontsize=9, color=("#C0392B" if v == 0 else "#2E7D32"),
                    fontweight=("bold" if v == 0 else "normal"), annotation_clip=True)
    a1.text(1.5, max(cnts) * 0.10, "none found", ha="center", va="bottom", fontsize=8.5,
            color="#C0392B")
    a1.set_xlim(0.4, 3.6)
    a1.set_xticks([1, 2, 3])
    a1.set_xticklabels(["$n$=1", "$n$=2", "$n$=3"])
    a1.set_ylabel("Supports with a feasible\nvector found")
    a1.set_ylim(0, max(cnts) * 1.18)
    a1.text(0.5, -0.185, f"$n$=1,2 over all {nb} eligible buses;  $n$=3 over the 20-bus pool",
            transform=a1.transAxes, ha="center", fontsize=7.6, color="#555555")
    a1.text(0.5, -0.30, "(a)", transform=a1.transAxes, ha="center", fontsize=10)

    # (b) pool size
    a2b = a2.twinx()
    a2b.bar(ks, nfeas, 1.6, color=C_BAR, edgecolor="#9DB4D4")
    for k, v, t in zip(ks, nfeas, tried):
        a2b.annotate(f"{v}/{t}", (k, v), textcoords="offset points", xytext=(0, 3),
                     ha="center", fontsize=8, color=C_BARLAB, annotation_clip=True)
    a2.plot(ks, [CANON_KVAR] * len(ks), "o-", color=C_CANON, lw=2.0, ms=7, zorder=5,
            label="best known (verified)")
    a2.plot(ks, [pool_best] * len(ks), "s--", color=C_POOL, lw=1.6, ms=5.5, zorder=4,
            label="this pool search")
    mid = (ks[0] + ks[1]) / 2
    a2.annotate(f"{CANON_KVAR:.1f}", (mid, CANON_KVAR), textcoords="offset points",
                xytext=(0, -12), ha="center", fontsize=9, color=C_CANON)
    a2.annotate(f"{pool_best:.1f}", (mid, pool_best), textcoords="offset points",
                xytext=(0, 5), ha="center", fontsize=9, color=C_POOL)
    a2.set_xlim(ks[0] - 2.6, ks[-1] + 2.6)
    a2.set_xticks(ks)
    a2.set_xlabel("Candidate-pool size (top-$k$)")
    a2.set_ylabel("Capacity (kvar)", color=C_CANON)
    a2.tick_params(axis="y", labelcolor=C_CANON)
    a2b.set_ylabel("Supports with a feasible\nvector found", color=C_BARLAB)
    a2b.tick_params(axis="y", labelcolor=C_BARLAB)
    a2b.grid(False)
    a2.set_ylim(CANON_KVAR - 7, pool_best + 7)
    a2b.set_ylim(0, max(nfeas) * 1.62)
    a2.set_zorder(a2b.get_zorder() + 1)
    a2.patch.set_visible(False)
    a2.legend(loc="lower center", bbox_to_anchor=(0.62, 1.03), ncol=2, fontsize=8,
              frameon=False, handlelength=2.0, columnspacing=1.0)
    a2.text(0.5, -0.30, "(b)", transform=a2.transAxes, ha="center", fontsize=10)

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "Fig4.pdf", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    print("saved", OUT / "Fig4.pdf")


if __name__ == "__main__":
    main()
