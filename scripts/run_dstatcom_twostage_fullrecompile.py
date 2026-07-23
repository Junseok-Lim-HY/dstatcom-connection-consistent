"""Single-evaluator two-stage full enumeration (16th review P0-1/P0-4).

Re-runs the two-stage per-support sizing over ALL 120 three-device supports under
BOTH the line-to-line and line-to-ground metrics using a FULL feeder recompilation
at every objective evaluation (the same evaluator used by the 24-hour operation).
This removes the fast edit-in-place vs. fresh-recompile discrepancy so the feasible
counts, the selected support, and the metric-ablation ratio all come from one
consistent evaluator. Writes reports/dstatcom_twostage_fullrecompile.json
incrementally so partial progress is never lost.
"""
from __future__ import annotations
import json, itertools
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
OUT = ROOT / "reports" / "dstatcom_twostage_fullrecompile.json"
POOL = ["740", "741", "711", "738", "735", "737", "736", "710", "734", "733"]
KV_LL, QBAR, PEAK = 4.8, 450.0, 1.34
ACC_LO, ACC_HI, BUF = 0.9562, 1.0438, 5e-4     # buffer so the design clears on a fresh solve after rounding
EXCLUDE = {"sourcebus", "799"}
SEEDS = (1, 2)
STAGEA_GEN, STAGEB_GEN, POP = 10, 18, 8


def solve_fresh(buses, q, metric):
    """FULL recompile every call -> identical circuit state as the operation script."""
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b, qi in zip(buses, q):
        if qi > 1e-6:
            dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                             f"kW=0 kvar={qi} Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")
    dss.Solution.Solve()
    lo, hi = 2.0, 0.0
    for bb in dss.Circuit.AllBusNames():
        if bb.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(bb)
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
    return round(lo, 4), round(hi, 4), bool(dss.Solution.Converged())


def two_stage(buses, metric, seed):
    def fa(x):
        lo, hi, _ = solve_fresh(buses, x, metric)
        return max(0.0, (ACC_LO + BUF) - lo) ** 2 + max(0.0, hi - (ACC_HI - BUF)) ** 2
    ra = differential_evolution(fa, [(0.0, QBAR)] * len(buses), maxiter=STAGEA_GEN,
                                popsize=POP, tol=1e-3, seed=seed, polish=True, init="sobol")
    x0 = np.clip(ra.x, 0, QBAR)

    def fb(x):
        lo, hi, _ = solve_fresh(buses, x, metric)
        s = max(0.0, (ACC_LO + BUF) - lo) + max(0.0, hi - (ACC_HI - BUF))
        return 1.0e5 * s + float(np.sum(x))
    rb = differential_evolution(fb, [(0.0, QBAR)] * len(buses), maxiter=STAGEB_GEN,
                                popsize=POP, tol=1e-2, seed=seed, polish=True, x0=x0)
    x = np.round(np.clip(rb.x, 0, QBAR), 1)
    lo, hi, conv = solve_fresh(buses, x, metric)
    feas = (lo >= ACC_LO) and (hi <= ACC_HI) and conv          # acceptance on the full-recompile solve
    return [round(float(v), 1) for v in x], round(float(np.sum(x)), 1), lo, hi, feas


def best_for(buses, metric):
    best = None
    for s in SEEDS:
        x, tot, lo, hi, feas = two_stage(buses, metric, s)
        if feas and (best is None or tot < best["total_kvar"]):
            best = dict(support=sorted(buses), total_kvar=tot, q=x, min_v=lo, max_v=hi, feasible=True)
    return best


def enumerate_metric(metric, results):
    combos = list(itertools.combinations(POOL, 3))
    out = []
    for k, combo in enumerate(combos):
        b = best_for(list(combo), metric)
        out.append(b if b is not None else
                   dict(support=sorted(combo), total_kvar=None, feasible=False))
        if (k + 1) % 10 == 0:
            feas_so_far = sum(1 for r in out if r["feasible"])
            print(f"[{metric}] {k+1}/120 ({feas_so_far} feasible)", flush=True)
            results[metric] = out
            OUT.write_text(json.dumps(results, indent=2))     # incremental save
    feas = sorted((r for r in out if r["feasible"]), key=lambda r: r["total_kvar"])
    return out, feas, len(feas)


def main():
    results = {"method": "two-stage full enumeration, FULL recompile at every evaluation, seeds 1-2, pop 8",
               "acceptance": [ACC_LO, ACC_HI], "buffer": BUF}
    ll_all, ll_feas, n_ll = enumerate_metric("ll", results)
    lg_all, lg_feas, n_lg = enumerate_metric("lg", results)
    ll_best = ll_feas[0] if ll_feas else None
    lg_best = lg_feas[0] if lg_feas else None
    rel = round(100.0 * (lg_best["total_kvar"] - ll_best["total_kvar"]) / ll_best["total_kvar"], 1) \
        if (ll_best and lg_best) else None
    results.update(dict(
        n_feasible_ll=n_ll, n_feasible_lg=n_lg, ll_best=ll_best, lg_best=lg_best,
        relative_increase_pct=rel,
        ll_top5=[(r["support"], r["total_kvar"]) for r in ll_feas[:5]],
        lg_top5=[(r["support"], r["total_kvar"]) for r in lg_feas[:5]],
        ll_ranked=ll_feas, lg_ranked=lg_feas))
    OUT.write_text(json.dumps(results, indent=2))
    print("\n== FULL-RECOMPILE TWO-STAGE ENUMERATION ==", flush=True)
    print("LL best:", ll_best["support"], ll_best["total_kvar"], ll_best["q"], "| feasible", n_ll, flush=True)
    print("LG best:", lg_best["support"], lg_best["total_kvar"], "| feasible", n_lg, flush=True)
    print("relative increase %:", rel, flush=True)
    print("LL top5:", results["ll_top5"], flush=True)


if __name__ == "__main__":
    main()
