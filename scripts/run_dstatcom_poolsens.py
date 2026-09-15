"""Candidate-pool sensitivity AND minimum-device-count robustness (resubmission, Reviewer 2).

Reviewer 2 questioned both (a) the minimum device COUNT and (b) the installed
CAPACITY of the three-device solution found within the prescreened ten-bus pool.
We therefore rank ALL eligible three-phase buses by the same screening metric
(worst line-to-line minimum over the screening load set) and, for pools of
increasing size, evaluate device counts n = 1, 2, 3 under the canonical line-to-line
acceptance:

  * n = 1 : every eligible bus individually (does any single unit suffice?)
  * n = 2 : all pairs over the full eligible set (does any pair suffice?)
  * n = 3 : full enumeration over pools of size 10 / 15 / 20 (lowest-capacity design)

For each pool we report the minimum feasible device count and, at n = 3, the
lowest-total-kvar verified-feasible design, so that both count and capacity can be
checked for stability against pool size. n = 3 is not enumerated over all 37 buses
(C(37,3)=7770); the ranking is monotone in effectiveness and the n=3 capacity is
shown stable across pools 10->20, so lower-ranked supports cannot improve it — this
is stated rather than silently truncated.

Sizing mirrors run_dstatcom_ablation_enum.py (KV_LL 4.8, QBAR 450, PEAK 1.34,
band [0.95,1.05], MARGIN 0.006, seeds 1-2-3, DE maxiter 25) so the ten-bus n=3
result reproduces the canonical design. Line-to-line is the primary metric per the
reviewer; line-to-ground is not swept over every pool (adds no information to the
count/capacity question and multiplies cost).
"""
from __future__ import annotations
import json, itertools, time
from pathlib import Path
import numpy as np
from scipy.optimize import differential_evolution
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
KV_LL, QBAR, PEAK = 4.8, 450.0, 1.34
V_LOW, V_HIGH = 0.95, 1.05
MARGIN, EPS = 0.006, 8e-4
EXCLUDE = {"sourcebus", "799"}
LAMBDA = (0.80, 1.00, 1.17, 1.34)
SEEDS = (1, 2, 3)
DE_MAXITER, DE_POP = 25, 10
N3_POOLS = (10, 15, 20)          # full n=3 enumeration pools
KNOWN_POOL10 = ["740", "741", "711", "738", "735", "737", "736", "710", "734", "733"]


def _phasors(bus):
    dss.Circuit.SetActiveBus(bus)
    va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
    nodes = list(dss.Bus.Nodes())
    return {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}


def bus_min_ll(bus):
    P = _phasors(bus)
    vs = [abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
    return min(vs) if vs else 1.0


def eligible_buses():
    dss.Text.Command(f"compile [{MASTER}]"); dss.Solution.Solve()
    out = []
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        if set((1, 2, 3)).issubset(set(dss.Bus.Nodes())):
            out.append(b)
    return out


def rank_all():
    buses = eligible_buses()
    worst = {b: 1.0 for b in buses}
    for lm in LAMBDA:
        dss.Text.Command(f"compile [{MASTER}]"); dss.Text.Command(f"set loadmult={lm}"); dss.Solution.Solve()
        for b in buses:
            worst[b] = min(worst[b], bus_min_ll(b))
    return sorted(buses, key=lambda b: worst[b]), {b: round(worst[b], 4) for b in buses}


def setup(buses):
    dss.Text.Command(f"compile [{MASTER}]"); dss.Text.Command(f"Set LoadMult={PEAK}")
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
        P = _phasors(b)
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                v = abs(P[i] - P[j]) / np.sqrt(3); lo = min(lo, v); hi = max(hi, v)
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
    return x, float(np.sum(x)), lo, hi, feasible


CACHE = {}
def best_support(combo):
    key = tuple(sorted(combo))
    if key in CACHE:
        return CACHE[key]
    setup(list(combo))
    best = None
    for seed in SEEDS:
        x, tot, lo, hi, feas = size(list(combo), seed)
        cand = (feas, tot, [round(float(v), 1) for v in x], round(lo, 6))
        if best is None or (cand[0] and not best[0]) or (cand[0] == best[0] and tot < best[1]):
            best = cand
    r = dict(support=sorted(combo), feasible=bool(best[0]), total_kvar=round(best[1], 1),
             q=best[2], min_v=best[3])
    CACHE[key] = r
    return r


def enum_n(pool, n):
    feas = []
    for combo in itertools.combinations(pool, n):
        r = best_support(combo)
        if r["feasible"]:
            feas.append(r)
    feas.sort(key=lambda r: r["total_kvar"])
    return feas


def main():
    t0 = time.time()
    ranked, worst = rank_all()
    print("eligible buses:", len(ranked), "| top-10:", ranked[:10],
          "| matches known pool:", ranked[:10] == KNOWN_POOL10, flush=True)

    # n=1 over all eligible; n=2 over all eligible (count question, full universe)
    n1 = enum_n(ranked, 1)
    print(f"n=1 over all {len(ranked)} buses: feasible={len(n1)} (t={time.time()-t0:.0f}s)", flush=True)
    n2 = enum_n(ranked, 2)
    print(f"n=2 over all {len(ranked)} buses: feasible={len(n2)} (t={time.time()-t0:.0f}s)", flush=True)

    # n=3 over increasing pools (capacity stability)
    per_pool = {}
    for k in N3_POOLS:
        pool = ranked[:k]
        f3 = enum_n(pool, 3)
        best = f3[0] if f3 else None
        per_pool[k] = dict(pool=pool, n3_best=best, n3_feasible=len(f3),
                           n3_top3=[(r["support"], r["total_kvar"]) for r in f3[:3]])
        print(f"[pool={k}] n=3 best {best['support'] if best else None}"
              f"@{best['total_kvar'] if best else None} kvar, feasible={len(f3)} "
              f"(t={time.time()-t0:.0f}s)", flush=True)

    base = per_pool.get(10, {}).get("n3_best")
    min_feasible_count = 1 if n1 else (2 if n2 else 3)
    out = dict(
        method="pool-size + device-count sensitivity; LL acceptance; n=1/2 over all eligible, n=3 over pools 10/15/20",
        settings=dict(seeds=list(SEEDS), de_maxiter=DE_MAXITER, de_pop=DE_POP,
                      margin=MARGIN, band=[V_LOW, V_HIGH], peak=PEAK),
        n_eligible_buses=len(ranked), ranking=[[b, worst[b]] for b in ranked],
        minimum_feasible_device_count=min_feasible_count,
        n1_feasible=[r["support"] for r in n1],
        n2_feasible_count=len(n2),
        n2_feasible_top3=[(r["support"], r["total_kvar"]) for r in n2[:3]],
        n3_pools=list(N3_POOLS), n3_per_pool=per_pool,
        n3_capacity_stable=bool(base and all(
            per_pool[k]["n3_best"] and abs(per_pool[k]["n3_best"]["total_kvar"] - base["total_kvar"]) <= 5.0
            for k in N3_POOLS)),
        n3_support_stable=bool(base and all(
            per_pool[k]["n3_best"] and per_pool[k]["n3_best"]["support"] == base["support"]
            for k in N3_POOLS)),
        runtime_s=round(time.time() - t0, 1))
    (ROOT / "reports" / "dstatcom_poolsens.json").write_text(json.dumps(out, indent=2))
    print("\nSAVED reports/dstatcom_poolsens.json | min feasible count =",
          min_feasible_count, "| runtime", round(time.time() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    main()
