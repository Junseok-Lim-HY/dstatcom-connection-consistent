# -*- coding: utf-8 -*-
"""Professor's review item 2: put the CANONICAL design straight into the POOL-SENSITIVITY
evaluator and see whether it is feasible there.

The pool-sensitivity study reports {711,735,740} at 1043.1 kvar as the best three-device
design for pools of 10/15/20, while the canonical design is {735,740,741} at 1041.3 kvar.
Every enlarged pool contains {735,740,741}, so a smaller verified design cannot be missing
from the "best" unless (a) the two studies evaluate differently, or (b) the pool-sensitivity
search simply failed to find it.

This script settles which, by evaluating the canonical q-vector with the pool-sensitivity
evalq() and by re-running its own DE search on that support.
"""
import sys
from pathlib import Path

import numpy as np
import opendssdirect as dss
from scipy.optimize import differential_evolution

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = HERE.parents[0]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
KV_LL, QBAR, PEAK = 4.8, 450.0, 1.34
V_LOW, V_HIGH = 0.95, 1.05
MARGIN, EPS = 0.006, 8e-4
EXCLUDE = {"sourcebus", "799"}
SEEDS = (1, 2, 3)
DE_MAXITER, DE_POP = 25, 10


def _phasors(bus):
    dss.Circuit.SetActiveBus(bus)
    v = dss.Bus.PuVoltage()
    nodes = dss.Bus.Nodes()
    out = {}
    for k, n in enumerate(nodes):
        if 2 * k + 1 < len(v):
            out[n] = complex(v[2 * k], v[2 * k + 1])
    return out


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
        P = _phasors(b)
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                v = abs(P[i] - P[j]) / np.sqrt(3)
                lo = min(lo, v)
                hi = max(hi, v)
    return lo, hi, bool(dss.Solution.Converged())


def de_size(buses, seed):
    def f(x):
        lo, hi, _ = evalq(buses, x)
        s = max(0.0, (V_LOW + MARGIN + EPS) - lo) + max(0.0, hi - (V_HIGH - MARGIN - EPS))
        return 1.0e5 * s + float(np.sum(x))
    res = differential_evolution(f, [(0.0, QBAR)] * len(buses), maxiter=DE_MAXITER,
                                 popsize=DE_POP, tol=1e-2, seed=seed, polish=True,
                                 init="sobol")
    x = np.round(np.clip(res.x, 0, QBAR), 1)
    lo, hi, conv = evalq(buses, x)
    feas = (lo >= V_LOW + MARGIN) and (hi <= V_HIGH - MARGIN) and conv
    return x, float(np.sum(x)), lo, hi, feas


def verdict(lo, hi, conv):
    return ("FEASIBLE" if (lo >= V_LOW + MARGIN and hi <= V_HIGH - MARGIN and conv)
            else "infeasible")


print("acceptance: min_LL >= %.3f, max_LL <= %.3f, converged" % (V_LOW + MARGIN, V_HIGH - MARGIN))
print()

# 1) canonical design evaluated verbatim in the pool-sensitivity evaluator
CANON_BUS = ["735", "740", "741"]
CANON_Q = [393.6, 249.2, 398.5]
setup(CANON_BUS)
lo, hi, conv = evalq(CANON_BUS, CANON_Q)
print("[1] canonical design in the pool-sensitivity evaluator")
print("    support %s  q=%s  total=%.1f kvar" % (CANON_BUS, CANON_Q, sum(CANON_Q)))
print("    min_LL=%.6f  max_LL=%.6f  converged=%s  -> %s"
      % (lo, hi, conv, verdict(lo, hi, conv)))
print()

# 2) what the pool-sensitivity search itself returns for that same support
print("[2] pool-sensitivity DE search re-run on the canonical support")
best = None
for s in SEEDS:
    x, tot, lo2, hi2, feas = de_size(CANON_BUS, s)
    print("    seed %d -> q=%s total=%.1f min_LL=%.6f %s"
          % (s, list(x), tot, lo2, "FEASIBLE" if feas else "infeasible"))
    if best is None or (feas and not best[0]) or (feas == best[0] and tot < best[1]):
        best = (feas, tot, list(x), lo2)
print("    best over seeds: total=%.1f kvar %s" % (best[1], "FEASIBLE" if best[0] else "infeasible"))
print()

# 3) the reported pool winner, for reference
WIN_BUS = ["711", "735", "740"]
WIN_Q = [249.0, 416.5, 377.6]
setup(WIN_BUS)
lo3, hi3, conv3 = evalq(WIN_BUS, WIN_Q)
print("[3] reported pool winner re-evaluated")
print("    support %s  total=%.1f kvar  min_LL=%.6f  max_LL=%.6f -> %s"
      % (WIN_BUS, sum(WIN_Q), lo3, hi3, verdict(lo3, hi3, conv3)))
