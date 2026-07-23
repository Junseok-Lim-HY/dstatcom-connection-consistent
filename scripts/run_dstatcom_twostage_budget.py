"""Two-stage per-support sizing + budget-convergence study (14th review P0-1).

The single-stage penalized DE occasionally converges below the acceptance, so the
verified-feasible success rate is only 8-13/16 (Supplement Table S3). This script
replaces it with a robust TWO-STAGE procedure and shows the best feasible total
stabilizes as the numerical budget grows:

  Stage A: maximize the worst monitored line-to-line minimum to obtain a
           verified-feasible starting point (DE on -min_m v_m).
  Stage B: from that point, minimize total installed kvar subject to the
           0.9562-1.0438 pu acceptance (DE with a large feasibility penalty,
           warm-started at the Stage-A vector).

For the leading LL support, the LL runner-up, and the LG ablation winner, it reports
the best/median feasible total and the verified-feasible run rate at three budgets.
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
ACC_LO, ACC_HI = V_LOW + MARGIN, V_HIGH - MARGIN          # 0.956 / 1.044 (pre-eps)
EXCLUDE = {"sourcebus", "799"}
SUPPORTS = {"LL_leading": ["711", "735", "740"],
            "LL_runnerup": ["735", "740", "741"],
            "LG_winner": ["711", "737", "740"]}
BUDGETS = [("10/25/3", 10, 25, 3), ("20/40/8", 20, 40, 8), ("30/60/12", 30, 60, 12)]


def setup(buses):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b in buses:
        dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                         f"kW=0 kvar=0.001 Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")


def evalq(buses, q, metric="ll"):
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
        if metric == "lg":
            for v in P.values():
                m = abs(v); lo = min(lo, m); hi = max(hi, m)
        else:
            for i, j in ((1, 2), (2, 3), (3, 1)):
                if i in P and j in P:
                    v = abs(P[i] - P[j]) / np.sqrt(3); lo = min(lo, v); hi = max(hi, v)
    return lo, hi, bool(dss.Solution.Converged())


def two_stage(buses, metric, seed, pop, gen):
    # Stage A: feasible start by maximizing worst minimum
    def fa(x):
        lo, hi, _ = evalq(buses, x, metric)
        return -(lo - max(0.0, hi - (ACC_HI - EPS)))
    ra = differential_evolution(fa, [(0.0, QBAR)] * len(buses), maxiter=max(10, gen // 2),
                                popsize=pop, tol=1e-2, seed=seed, polish=True, init="sobol")
    x0 = np.clip(ra.x, 0, QBAR)
    # Stage B: minimize total kvar with feasibility penalty, warm-started at x0
    def fb(x):
        lo, hi, _ = evalq(buses, x, metric)
        s = max(0.0, (ACC_LO + EPS) - lo) + max(0.0, hi - (ACC_HI - EPS))
        return 1.0e5 * s + float(np.sum(x))
    init = np.clip(x0 + np.zeros((pop * len(buses), len(buses))), 0, QBAR)
    rb = differential_evolution(fb, [(0.0, QBAR)] * len(buses), maxiter=gen,
                                popsize=pop, tol=1e-2, seed=seed, polish=True,
                                x0=x0)
    x = np.round(np.clip(rb.x, 0, QBAR), 1)
    lo, hi, conv = evalq(buses, x, metric)
    feas = (lo >= ACC_LO) and (hi <= ACC_HI) and conv
    return float(np.sum(x)), round(lo, 4), feas, [round(float(v), 1) for v in x]


def main():
    out = {}
    for name, buses in SUPPORTS.items():
        metric = "lg" if name.startswith("LG") else "ll"
        setup(buses)
        rows = []
        for label, pop, gen, nseed in BUDGETS:
            tots, feas_ct, best = [], 0, None
            for s in range(1, nseed + 1):
                tot, lo, feas, x = two_stage(buses, metric, s, pop, gen)
                if feas:
                    feas_ct += 1; tots.append(tot)
                    if best is None or tot < best[0]:
                        best = (tot, lo, x)
            rows.append(dict(budget=label, pop=pop, gen=gen, seeds=nseed,
                             feasible_runs=feas_ct,
                             best_total=round(best[0], 1) if best else None,
                             best_vmin=best[1] if best else None,
                             best_vector=best[2] if best else None,
                             median_total=round(float(np.median(tots)), 1) if tots else None))
            print(f"{name} {buses} [{label}] feas {feas_ct}/{nseed} "
                  f"best {rows[-1]['best_total']} median {rows[-1]['median_total']}", flush=True)
        out[name] = dict(support=buses, metric=metric, budgets=rows)
    (ROOT / "reports" / "dstatcom_twostage_budget.json").write_text(json.dumps(out, indent=2))
    print("\n" + json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
