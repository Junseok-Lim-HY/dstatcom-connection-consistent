"""Full two-stage re-enumeration of all 120 three-device supports (15th review, Version B).

Runs the robust TWO-STAGE per-support sizing (Stage A: feasible-point search that
handles BOTH voltage bounds; Stage B: minimize total kvar) over ALL 120 supports
under BOTH the line-to-line and line-to-ground metrics, so the canonical design and
the metric-ablation ratio come from a single consistent two-stage source. Produces
reports/dstatcom_twostage_enum.json with the ranked feasible supports for each metric.
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
ACC_LO, ACC_HI, EPS = 0.9562, 1.0438, 0.0        # acceptance edges (post-margin)
EXCLUDE = {"sourcebus", "799"}
SEEDS = (1, 2, 3)
STAGEA_GEN, STAGEB_GEN, POP = 15, 30, 10


def setup(buses):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b in buses:
        dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                         f"kW=0 kvar=0.001 Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")


def evalq(buses, q, metric):
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


def two_stage(buses, metric, seed):
    # Stage A: feasible point handling BOTH bounds: Phi = sum[(0.9562-v)_+^2 + (v-1.0438)_+^2]
    def fa(x):
        lo, hi, _ = evalq(buses, x, metric)
        return max(0.0, ACC_LO - lo) ** 2 + max(0.0, hi - ACC_HI) ** 2
    ra = differential_evolution(fa, [(0.0, QBAR)] * len(buses), maxiter=STAGEA_GEN,
                                popsize=POP, tol=1e-3, seed=seed, polish=True, init="sobol")
    x0 = np.clip(ra.x, 0, QBAR)
    # Stage B: minimize total kvar with feasibility penalty, warm-started at x0
    def fb(x):
        lo, hi, _ = evalq(buses, x, metric)
        s = max(0.0, ACC_LO - lo) + max(0.0, hi - ACC_HI)
        return 1.0e5 * s + float(np.sum(x))
    rb = differential_evolution(fb, [(0.0, QBAR)] * len(buses), maxiter=STAGEB_GEN,
                                popsize=POP, tol=1e-2, seed=seed, polish=True, x0=x0)
    x = np.round(np.clip(rb.x, 0, QBAR), 1)
    lo, hi, conv = evalq(buses, x, metric)
    feas = (lo >= ACC_LO) and (hi <= ACC_HI) and conv
    return x, float(np.sum(x)), round(lo, 4), round(hi, 4), feas


def best_for(buses, metric):
    best = None
    for s in SEEDS:
        x, tot, lo, hi, feas = two_stage(buses, metric, s)
        if feas and (best is None or tot < best[1]):
            best = (x, tot, lo, hi)
    return best


def enumerate_metric(metric):
    combos = list(itertools.combinations(POOL, 3))
    results = []
    for k, combo in enumerate(combos):
        setup(list(combo))
        b = best_for(list(combo), metric)
        if b is not None:
            x, tot, lo, hi = b
            results.append(dict(support=sorted(combo), total_kvar=round(tot, 1),
                                q=[round(float(v), 1) for v in x], min_v=lo, max_v=hi,
                                feasible=True))
        else:
            results.append(dict(support=sorted(combo), total_kvar=None, feasible=False))
        if (k + 1) % 20 == 0:
            print(f"[{metric}] {k+1}/120 scanned", flush=True)
    feas = sorted((r for r in results if r["feasible"]), key=lambda r: r["total_kvar"])
    return feas, len(feas)


def main():
    ll_feas, n_ll = enumerate_metric("ll")
    lg_feas, n_lg = enumerate_metric("lg")
    ll_best = ll_feas[0] if ll_feas else None
    lg_best = lg_feas[0] if lg_feas else None
    rel = round(100.0 * (lg_best["total_kvar"] - ll_best["total_kvar"]) / ll_best["total_kvar"], 1) \
        if (ll_best and lg_best) else None
    out = dict(
        method="two-stage (feasible-point then kvar-min) full enumeration, seeds 1-3, pop 10",
        n_feasible_ll=n_ll, n_feasible_lg=n_lg,
        ll_best=ll_best, lg_best=lg_best, relative_increase_pct=rel,
        ll_top5=[(r["support"], r["total_kvar"]) for r in ll_feas[:5]],
        lg_top5=[(r["support"], r["total_kvar"]) for r in lg_feas[:5]],
        ll_ranked=ll_feas, lg_ranked=lg_feas)
    (ROOT / "reports" / "dstatcom_twostage_enum.json").write_text(json.dumps(out, indent=2))
    print("\n== TWO-STAGE ENUMERATION ==", flush=True)
    print("LL best:", ll_best["support"] if ll_best else None,
          ll_best["total_kvar"] if ll_best else None, "| feasible", n_ll, flush=True)
    print("LG best:", lg_best["support"] if lg_best else None,
          lg_best["total_kvar"] if lg_best else None, "| feasible", n_lg, flush=True)
    print("relative increase %:", rel, flush=True)
    print("LL top5:", out["ll_top5"], flush=True)


if __name__ == "__main__":
    main()
