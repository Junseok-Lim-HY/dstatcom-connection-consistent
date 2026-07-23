"""Canonical three-device design by full enumeration (7th review P0-1, P0-5).

The seed-1 design {740,711,737} (1037 kvar) is not the lowest-capacity feasible
three-device design. This script evaluates ALL C(10,3)=120 three-device supports
under a common continuous sizing with multiple seeds, verifies feasibility at
pre-rounding precision, and selects the lowest-total-kvar verified-feasible support
as the canonical design.

Feasibility (planning margin, P0-5): min_m v_m >= 0.956 and max_m v_m <= 1.044 at
lambda=1.34 with the native regulator active, on line-to-line terminal voltages to
six digits (m_v = 0.006). A strictness tolerance eps keeps the boundary firm.

Speed: the feeder is compiled once per support; each objective evaluation only edits
the three generator kvar values and re-solves (no per-eval disk recompile).
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
EPS = 8e-4          # buffer so the design still clears the band edge AFTER 0.1-kvar rounding
V_RATE = 0.95
EXCLUDE = {"sourcebus", "799"}
SEEDS = (1, 2, 3)
DE_MAXITER, DE_POP = 25, 10


def setup(buses):
    """Compile once and create the three generators at a tiny floor."""
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
        # size to clear the feasibility check (band edge + strictness tolerance)
        s = max(0.0, (V_LOW + MARGIN + EPS) - lo) + max(0.0, hi - (V_HIGH - MARGIN - EPS))
        return 1.0e5 * s + float(np.sum(x))
    res = differential_evolution(f, [(0.0, QBAR)] * 3, maxiter=DE_MAXITER,
                                 popsize=DE_POP, tol=1e-2, seed=seed, polish=True, init="sobol")
    # feasibility is checked on the INSTALLED (0.1-kvar-rounded) design, so the
    # reported design clears the band edge at pre-rounding precision (P0-5)
    x = np.round(np.clip(res.x, 0, QBAR), 1)
    lo, hi, conv = evalq(buses, x)
    feasible = (lo >= V_LOW + MARGIN) and (hi <= V_HIGH - MARGIN) and conv
    return x, float(np.sum(x)), lo, hi, conv, feasible


def best_for(buses):
    best = None
    for seed in SEEDS:
        x, tot, lo, hi, conv, feas = size(buses, seed)
        cand = (feas, tot, x, lo, hi, conv)
        if best is None or (cand[0] and not best[0]) or (cand[0] == best[0] and tot < best[1]):
            best = cand
    return best


def device_currents(buses, q):
    evalq(buses, q)
    out = []
    for b in buses:
        dss.Circuit.SetActiveElement(f"Generator.st_{b}")
        curr = dss.CktElement.CurrentsMagAng()[0::2]
        out.append(max(abs(c) for c in curr[:3]) if curr else 0.0)
    return out


def main():
    combos = list(itertools.combinations(POOL, 3))
    results = []
    for k, combo in enumerate(combos):
        setup(list(combo))
        feas, tot, x, lo, hi, conv = best_for(list(combo))
        results.append(dict(support=sorted(combo), total_kvar=round(tot, 1),
                            min_v=round(lo, 6), max_v=round(hi, 6),
                            converged=conv, feasible=bool(feas),
                            q=[round(float(v), 1) for v in x]))
        if feas:
            print(f"[{k+1}/120] {sorted(combo)} FEAS tot {tot:.1f} minv {lo:.6f} maxv {hi:.6f}", flush=True)
        elif (k + 1) % 20 == 0:
            print(f"[{k+1}/120] scanned", flush=True)

    feas = sorted((r for r in results if r["feasible"]), key=lambda r: r["total_kvar"])
    canonical = feas[0] if feas else None
    out = dict(n_supports=len(combos), n_feasible=len(feas),
               margin=MARGIN, band_edges=[V_LOW + MARGIN, V_HIGH - MARGIN],
               feasible_ranked=feas[:15], canonical=None,
               # all supports' total kvar and feasibility (sorted) for Fig 1 panel 3
               all_supports=sorted(({"support": r["support"], "total_kvar": r["total_kvar"],
                                     "feasible": r["feasible"], "min_v": r["min_v"]}
                                    for r in results), key=lambda r: r["total_kvar"]),
               seed1_design=dict(support=["711", "737", "740"], total_kvar=1037.0))
    if canonical:
        buses = canonical["support"]; q = canonical["q"]
        setup(buses)
        ic = device_currents(buses, q)
        rated = [float(qi) / (np.sqrt(3) * V_RATE * KV_LL) for qi in q]
        out["canonical"] = dict(
            support=buses, q_kvar=q, total_kvar=canonical["total_kvar"],
            min_v=canonical["min_v"], max_v=canonical["max_v"],
            margin_above_0p95=round(canonical["min_v"] - V_LOW, 4),
            dev_current_a=[round(float(v), 1) for v in ic],
            dev_benchmark_a=[round(float(v), 1) for v in rated],
            current_ok=bool(all(a <= r + 1e-6 for a, r in zip(ic, rated))))
    (ROOT / "reports" / "dstatcom_canonical.json").write_text(json.dumps(out, indent=2))
    print("\n== CANONICAL ==\n" + json.dumps(out["canonical"], indent=2), flush=True)
    print(f"feasible {len(feas)}/120; top5:",
          [(r["support"], r["total_kvar"], r["min_v"]) for r in feas[:5]], flush=True)


if __name__ == "__main__":
    main()
