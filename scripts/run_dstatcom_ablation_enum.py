"""Enumeration-based metric ablation: line-to-ground vs line-to-line (10th review P0-C).

The 9th-review ablation used the auxiliary greedy pipeline. The 10th reviewer's
preferred fix is to derive the metric-sensitivity claim from the SAME primary
method as the canonical design: full enumeration of all C(10,3)=120 three-device
supports, each sized by differential evolution to the unified acceptance, under
BOTH metrics with identical per-support budget, 0.1-kvar rounding, and the 0.9562
acceptance. The lowest-total-kvar verified-feasible support under each metric is
selected; the capacity ratio 100*(Q_LG-Q_LL)/Q_LL is the reported sensitivity.

This makes the ~20% claim a property of the canonical enumeration, not a heuristic.
"""
from __future__ import annotations
import json, itertools
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
POOL = ["740", "741", "711", "738", "735", "737", "736", "710", "734", "733"]
KV_LL, QBAR, PEAK = 4.8, 450.0, 1.34
V_LOW, V_HIGH = 0.95, 1.05
MARGIN = 0.006
EPS = 8e-4          # buffer so the design clears the band edge AFTER 0.1-kvar rounding
EXCLUDE = {"sourcebus", "799"}
SEEDS = (1, 2, 3)
DE_MAXITER, DE_POP = 25, 10


def setup(buses):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b in buses:
        dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                         f"kW=0 kvar=0.001 Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")


def _bus_phasors():
    out = []
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
        nodes = list(dss.Bus.Nodes())
        P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
        out.append(P)
    return out


def evalq(buses, q, metric):
    for b, qi in zip(buses, q):
        dss.Text.Command(f"Edit Generator.st_{b} kvar={max(float(qi), 1e-3)}")
    dss.Solution.Solve()
    lo, hi = 2.0, 0.0
    for P in _bus_phasors():
        if metric == "lg":
            for v in P.values():
                m = abs(v); lo = min(lo, m); hi = max(hi, m)
        else:
            for i, j in ((1, 2), (2, 3), (3, 1)):
                if i in P and j in P:
                    v = abs(P[i] - P[j]) / np.sqrt(3)
                    lo = min(lo, v); hi = max(hi, v)
    return lo, hi, bool(dss.Solution.Converged())


def size(buses, metric, seed):
    def f(x):
        lo, hi, _ = evalq(buses, x, metric)
        s = max(0.0, (V_LOW + MARGIN + EPS) - lo) + max(0.0, hi - (V_HIGH - MARGIN - EPS))
        return 1.0e5 * s + float(np.sum(x))
    res = differential_evolution(f, [(0.0, QBAR)] * len(buses), maxiter=DE_MAXITER,
                                 popsize=DE_POP, tol=1e-2, seed=seed, polish=True, init="sobol")
    x = np.round(np.clip(res.x, 0, QBAR), 1)
    lo, hi, conv = evalq(buses, x, metric)
    feasible = (lo >= V_LOW + MARGIN) and (hi <= V_HIGH - MARGIN) and conv
    return x, float(np.sum(x)), lo, hi, conv, feasible


def best_for(buses, metric):
    best = None
    for seed in SEEDS:
        x, tot, lo, hi, conv, feas = size(buses, metric, seed)
        cand = (feas, tot, x, lo, hi, conv)
        if best is None or (cand[0] and not best[0]) or (cand[0] == best[0] and tot < best[1]):
            best = cand
    return best


def cross_min(buses, q):
    """Given an installed design, report worst LG and worst LL over the feeder."""
    lo_lg, _, _ = evalq(buses, q, "lg")
    lo_ll, _, _ = evalq(buses, q, "ll")
    return round(lo_lg, 4), round(lo_ll, 4)


def enumerate_metric(metric):
    combos = list(itertools.combinations(POOL, 3))
    results = []
    for k, combo in enumerate(combos):
        setup(list(combo))
        feas, tot, x, lo, hi, conv = best_for(list(combo), metric)
        results.append(dict(support=sorted(combo), total_kvar=round(tot, 1),
                            min_v=round(lo, 6), max_v=round(hi, 6),
                            feasible=bool(feas), q=[round(float(v), 1) for v in x]))
        if (k + 1) % 30 == 0:
            print(f"[{metric}] [{k+1}/120] scanned", flush=True)
    feas = sorted((r for r in results if r["feasible"]), key=lambda r: r["total_kvar"])
    return feas, results


def main():
    setup([]);
    base_lg = round(evalq([], [], "lg")[0], 4)
    base_ll = round(evalq([], [], "ll")[0], 4)

    feas_lg, all_lg = enumerate_metric("lg")
    feas_ll, all_ll = enumerate_metric("ll")
    best_lg = feas_lg[0] if feas_lg else None
    best_ll = feas_ll[0] if feas_ll else None

    # cross-evaluate each metric's selected design on both metrics
    lg_cross = ll_cross = None
    if best_lg:
        setup(best_lg["support"]); lg_cross = cross_min(best_lg["support"], best_lg["q"])
    if best_ll:
        setup(best_ll["support"]); ll_cross = cross_min(best_ll["support"], best_ll["q"])

    rel = round(100.0 * (best_lg["total_kvar"] - best_ll["total_kvar"]) / best_ll["total_kvar"], 1) \
        if (best_lg and best_ll) else None

    out = dict(
        method="full enumeration of 120 three-device supports under each metric",
        seeds=list(SEEDS), margin=MARGIN,
        base_worst=dict(line_to_ground=base_lg, line_to_line=base_ll,
                        overstatement_pu=round(base_ll - base_lg, 4)),
        lg_design=dict(support=best_lg["support"], total_kvar=best_lg["total_kvar"],
                       q_kvar=best_lg["q"], min_v_lg=best_lg["min_v"]) if best_lg else None,
        ll_design=dict(support=best_ll["support"], total_kvar=best_ll["total_kvar"],
                       q_kvar=best_ll["q"], min_v_ll=best_ll["min_v"]) if best_ll else None,
        lg_design_cross=dict(lg_min=lg_cross[0], ll_min=lg_cross[1]) if lg_cross else None,
        ll_design_cross=dict(lg_min=ll_cross[0], ll_min=ll_cross[1]) if ll_cross else None,
        relative_increase_pct=rel,
        n_feasible_lg=len(feas_lg), n_feasible_ll=len(feas_ll),
        lg_top5=[(r["support"], r["total_kvar"]) for r in feas_lg[:5]],
        ll_top5=[(r["support"], r["total_kvar"]) for r in feas_ll[:5]],
    )
    (ROOT / "reports" / "dstatcom_ablation_enum.json").write_text(json.dumps(out, indent=2))
    print("\n" + json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
