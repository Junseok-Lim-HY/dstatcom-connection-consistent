"""Figures for the resubmission new analyses (R2 pool/count, R1-6&R3-3 MC, R3-1 VSC loss)."""
import json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = ROOT / "figs"; OUT.mkdir(exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.axisbelow": True})
C = {"fixed": "#C0392B", "droop": "#2E74B5", "coord": "#2E7D32", "schedule": "#B8860B"}
MK = {"fixed": "o", "droop": "s", "coord": "^", "schedule": "D"}


def fig_vscloss():
    d = json.loads((REP / "dstatcom_vscloss.json").read_text())
    lt = [float(x) for x in d["loss_model"]["L_tot_sweep"]]
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    for ctrl in ("fixed", "droop", "coord"):
        c = d["controls"][ctrl]
        net = [c["by_L_tot"][f"L_tot={l}"]["net_daily_energy_kWh"] for l in lt]
        ax.plot([x * 100 for x in lt], net, marker=MK[ctrl], color=C[ctrl],
                label=f"{ctrl} (BE {c['breakeven_L_tot_frac']*100:.1f}%)", lw=1.8, ms=5)
    ax.axhline(0, color="k", lw=0.9, ls="--")
    ax.set_xlabel("Converter loss at rating $L_{tot}$ (%)")
    ax.set_ylabel("Net daily energy (kWh/day)")
    ax.set_title("Net daily energy vs converter loss")
    ax.legend(fontsize=8, title="control (break-even)")
    fig.tight_layout(); fig.savefig(OUT / "fig_rev_vscloss.png", dpi=220); plt.close(fig)
    print("saved fig_rev_vscloss.png")


def fig_poolsens():
    p = REP / "dstatcom_poolsens.json"
    if not p.exists():
        print("poolsens json not ready"); return
    d = json.loads(p.read_text())
    ks = d["n3_pools"]; nb = d["n_eligible_buses"]
    caps = [d["n3_per_pool"][str(k)]["n3_best"]["total_kvar"] for k in ks]
    nfeas = [d["n3_per_pool"][str(k)]["n3_feasible"] for k in ks]
    n1 = len(d["n1_feasible"]); n2 = d["n2_feasible_count"]; n3_full = nfeas[-1]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.6, 3.2))
    # (a) minimum device count: feasible supports at n=1,2,3 (over the full/largest pool)
    cnts = [n1, n2, n3_full]
    bars = a1.bar([1, 2, 3], cnts, 0.6, color=["#C0392B", "#C0392B", "#2E7D32"], edgecolor="white")
    for x, v in zip([1, 2, 3], cnts):
        a1.annotate(f"{v}" + ("  (infeasible)" if v == 0 else ""), (x, v),
                    textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8,
                    color=("#C0392B" if v == 0 else "#2E7D32"))
    a1.set_xticks([1, 2, 3]); a1.set_xticklabels(["n=1", "n=2", "n=3"])
    a1.set_ylabel("feasible supports"); a1.set_ylim(0, max(cnts) * 1.18)
    a1.set_title(f"Minimum device count = 3\n(n=1,2 empty over all {nb} buses)", fontsize=9.5)
    # (b) capacity stable while feasible set grows with pool size
    a2b = a2.twinx()
    a2b.bar(ks, nfeas, 1.6, color="#C9D6EA", edgecolor="#9DB4D4", label="# feasible 3-device")
    a2.plot(ks, caps, "o-", color="#2E74B5", lw=2.0, ms=7, label="min-capacity design", zorder=5)
    for k, c in zip(ks, caps):
        a2.annotate(f"{c:.1f}", (k, c), textcoords="offset points", xytext=(0, 8), ha="center",
                    fontsize=8, color="#2E74B5", zorder=6)
    a2.set_zorder(a2b.get_zorder() + 1); a2.patch.set_visible(False)
    lo = min(caps); a2.set_ylim(lo - 18, lo + 22)
    a2.set_xlabel("candidate-pool size (top-$k$)"); a2.set_ylabel("min-capacity (kvar)", color="#2E74B5")
    a2b.set_ylabel("# feasible 3-device combos", color="#6B86AD")
    a2.set_xticks(ks); a2.set_title("Capacity unchanged as pool grows\n(feasible set expands, optimum does not)", fontsize=9.5)
    fig.tight_layout(); fig.savefig(OUT / "fig_rev_poolsens.png", dpi=220); plt.close(fig)
    print("saved fig_rev_poolsens.png")


def fig_montecarlo():
    d = json.loads((REP / "dstatcom_montecarlo.json").read_text())
    cases = list(d["cases"].keys()); ctrls = ("fixed", "schedule", "droop")
    cs = cases[-1]  # stress case
    rawkey = next((k for k in d if k.startswith("raw_droop")), None)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.1))
    # (a) distribution of minimum line-to-line voltage under phase-independent error
    if rawkey:
        mv = np.array(d[rawkey]["minv"])
        a1.hist(mv, bins=40, color="#2E74B5", edgecolor="white", alpha=0.85)
        a1.axvline(0.95, color="#C0392B", lw=1.6, ls="--")
        pv = 100.0 * np.mean(mv < 0.95)
        a1.text(0.951, a1.get_ylim()[1] * 0.52, f"0.95 pu\nP(viol)={pv:.1f}%",
                color="#C0392B", fontsize=8, va="center", ha="left")
        a1.text(0.03, 0.97, f"worst {mv.min():.4f}\nmean {mv.mean():.4f}",
                transform=a1.transAxes, fontsize=8, va="top", ha="left")
    a1.set_xlabel("min line-to-line voltage (pu)"); a1.set_ylabel("MC samples")
    a1.set_title("Robustness margin (droop, σ stress)")
    # (b) control efficiency: mean injected Q (bars) and mean feeder loss (line)
    q = [d["cases"][cs][ct]["mean_total_kvar"] for ct in ctrls]
    ls = [d["cases"][cs][ct]["mean_feeder_loss_kW"] for ct in ctrls]
    xx = np.arange(len(ctrls)); a2b = a2.twinx()
    a2.bar(xx, q, 0.55, color="#7C6BAE", edgecolor="white", label="mean $\\Sigma Q$")
    a2b.plot(xx, ls, "o-", color="#C0392B", lw=1.8, label="mean feeder loss")
    a2.set_xticks(xx); a2.set_xticklabels(ctrls); a2.set_ylabel("mean $\\Sigma Q$ (kvar)")
    a2b.set_ylabel("mean feeder loss (kW)"); a2.set_title("Control efficiency (σ stress)")
    a2.set_ylim(min(q) - 40, max(q) + 20)
    fig.tight_layout(); fig.savefig(OUT / "fig_rev_montecarlo.png", dpi=220); plt.close(fig)
    print("saved fig_rev_montecarlo.png")


if __name__ == "__main__":
    fig_vscloss(); fig_montecarlo(); fig_poolsens()
