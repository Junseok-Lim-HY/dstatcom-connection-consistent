"""Fresh-compile re-verification of the top two-stage supports (Version B finalization).

The full two-stage enumeration used fast edit-in-place evaluation, which is ~0.0005 pu
optimistic versus a fresh feeder recompile (the setting used by the 24-hour operation
script). This re-optimizes the top line-to-line and line-to-ground candidates with a
FRESH compile at every objective evaluation and a rounding buffer, so the adopted
canonical vector clears the 0.9562 pu acceptance after 0.1-kvar rounding on a fresh
solve. Writes reports/dstatcom_twostage_fresh.json.
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
ACC_LO, ACC_HI, BUF = 0.9562, 1.0438, 5e-4      # rounding buffer so fresh solve clears
EXCLUDE = {"sourcebus", "799"}
SEEDS = (1, 2, 3, 4)
POP, GA, GB = 10, 18, 30

LL_CANDS = [["711","735","741"], ["735","738","740"], ["735","740","741"],
            ["735","738","741"], ["736","740","741"], ["711","735","740"]]
LG_CANDS = [["711","737","740"], ["737","740","741"], ["711","737","741"]]


def solve_fresh(buses, q, metric):
    """FRESH compile every call (matches the operation script)."""
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
    ra = differential_evolution(fa, [(0.0, QBAR)] * len(buses), maxiter=GA,
                                popsize=POP, tol=1e-3, seed=seed, polish=True, init="sobol")
    x0 = np.clip(ra.x, 0, QBAR)
    def fb(x):
        lo, hi, _ = solve_fresh(buses, x, metric)
        s = max(0.0, (ACC_LO + BUF) - lo) + max(0.0, hi - (ACC_HI - BUF))
        return 1.0e5 * s + float(np.sum(x))
    rb = differential_evolution(fb, [(0.0, QBAR)] * len(buses), maxiter=GB,
                                popsize=POP, tol=1e-2, seed=seed, polish=True, x0=x0)
    x = np.round(np.clip(rb.x, 0, QBAR), 1)
    lo, hi, conv = solve_fresh(buses, x, metric)
    feas = (lo >= ACC_LO) and (hi <= ACC_HI) and conv           # fresh acceptance
    return [round(float(v), 1) for v in x], round(float(np.sum(x)), 1), lo, hi, feas


def best(cands, metric):
    out = None
    for buses in cands:
        for s in SEEDS:
            x, tot, lo, hi, feas = two_stage(list(buses), metric, s)
            if feas and (out is None or tot < out["total_kvar"]):
                out = dict(support=sorted(buses), q_kvar=x, total_kvar=tot, min_v=lo, max_v=hi)
        if out:
            print(f"[{metric}] {buses} -> best so far {out['support']} {out['total_kvar']} "
                  f"(min {out['min_v']})", flush=True)
    return out


def main():
    ll = best(LL_CANDS, "ll")
    lg = best(LG_CANDS, "lg")
    rel = round(100.0 * (lg["total_kvar"] - ll["total_kvar"]) / ll["total_kvar"], 1)
    out = dict(ll_best=ll, lg_best=lg, relative_increase_pct=rel,
               note="fresh-compile-verified two-stage; acceptance clears on a fresh solve")
    (ROOT / "reports" / "dstatcom_twostage_fresh.json").write_text(json.dumps(out, indent=2))
    print("\nLL:", ll["support"], ll["total_kvar"], ll["q_kvar"], "min", ll["min_v"], "max", ll["max_v"])
    print("LG:", lg["support"], lg["total_kvar"], "min", lg["min_v"])
    print("rel %", rel, flush=True)


if __name__ == "__main__":
    main()
