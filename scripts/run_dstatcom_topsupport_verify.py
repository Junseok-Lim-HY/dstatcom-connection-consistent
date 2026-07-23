"""Top-support stability re-verification (11th review P0-5).

The canonical support {711,735,740} (1043.1 kvar) leads the runner-up
{735,740,741} (1043.7 kvar) by only 0.6 kvar (~0.06%), which may be within the
differential-evolution solver variability. This script re-optimizes the top-N
LL-feasible supports under a HIGHER budget (larger population/generations) and
MANY more seeds, reporting per-support best / median / IQR total kvar and the
re-verified worst line-to-line minimum, so the manuscript can state honestly
whether the exact winner is statistically separated or only near-equivalent.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
KV_LL, QBAR, PEAK = 4.8, 450.0, 1.34
V_LOW, V_HIGH, MARGIN, EPS = 0.95, 1.05, 0.006, 8e-4
EXCLUDE = {"sourcebus", "799"}
SEEDS = tuple(range(1, 17))        # 16 seeds (was 3)
DE_MAXITER, DE_POP = 40, 20        # higher budget (was 25/10)
TOPN = 8


def setup(buses):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b in buses:
        dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                         f"kW=0 kvar=0.001 Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")


def evalq(buses, q):
    for b, qi in zip(buses, q):
        dss.Text.Command(f"Edit Generator.st_{b} kvar={max(float(qi), 1e-3)}")
    dss.Solution.Solve()
    lo, hi = 2.0, 0.0
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
        nodes = list(dss.Bus.Nodes())
        P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                v = abs(P[i] - P[j]) / np.sqrt(3)
                lo = min(lo, v); hi = max(hi, v)
    return lo, hi, bool(dss.Solution.Converged())


def size(buses, seed):
    def f(x):
        lo, hi, _ = evalq(buses, x)
        s = max(0.0, (V_LOW + MARGIN + EPS) - lo) + max(0.0, hi - (V_HIGH - MARGIN - EPS))
        return 1.0e5 * s + float(np.sum(x))
    res = differential_evolution(f, [(0.0, QBAR)] * len(buses), maxiter=DE_MAXITER,
                                 popsize=DE_POP, tol=1e-2, seed=seed, polish=True, init="sobol")
    x = np.round(np.clip(res.x, 0, QBAR), 1)
    lo, hi, conv = evalq(buses, x)
    feasible = (lo >= V_LOW + MARGIN) and (hi <= V_HIGH - MARGIN) and conv
    return float(np.sum(x)), lo, feasible


def main():
    can = json.load(open(ROOT / "reports" / "dstatcom_canonical.json"))
    feas = [r["support"] for r in can["all_supports"] if r["feasible"]][:TOPN]
    out = []
    for sup in feas:
        setup(sup)
        totals, minvs = [], []
        for s in SEEDS:
            tot, lo, ok = size(sup, s)
            if ok:
                totals.append(tot); minvs.append(lo)
        totals = np.array(totals)
        out.append(dict(
            support=sup, n_feasible_seeds=int(len(totals)),
            best_kvar=round(float(totals.min()), 1),
            median_kvar=round(float(np.median(totals)), 1),
            iqr_kvar=[round(float(np.percentile(totals, 25)), 1),
                      round(float(np.percentile(totals, 75)), 1)],
            std_kvar=round(float(totals.std(ddof=1)), 2),
            worst_min_v=round(float(min(minvs)), 4)))
        print(f"{sup}: best {out[-1]['best_kvar']} median {out[-1]['median_kvar']} "
              f"IQR {out[-1]['iqr_kvar']} std {out[-1]['std_kvar']} minv {out[-1]['worst_min_v']}",
              flush=True)

    # rank stability: does the best-kvar ordering match the 3-seed enumeration order?
    by_best = sorted(out, key=lambda r: r["best_kvar"])
    spread = max(r["std_kvar"] for r in out)
    gap_1_2 = round(by_best[1]["best_kvar"] - by_best[0]["best_kvar"], 1)
    summary = dict(
        n_seeds=len(SEEDS), budget=dict(population=DE_POP, generations=DE_MAXITER),
        supports=out,
        best_support=by_best[0]["support"], best_kvar=by_best[0]["best_kvar"],
        runner_up=by_best[1]["support"], runner_up_kvar=by_best[1]["best_kvar"],
        gap_best_to_runnerup_kvar=gap_1_2,
        max_seed_std_kvar=round(float(spread), 2),
        separated=bool(gap_1_2 > spread),
        note=("exact winner separated from runner-up by more than the seed spread"
              if gap_1_2 > spread else
              "top supports are numerically near-equivalent (gap < seed spread)"))
    (ROOT / "reports" / "dstatcom_topsupport_verify.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
