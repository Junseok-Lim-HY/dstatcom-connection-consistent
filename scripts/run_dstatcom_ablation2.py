"""Matched-seed metric ablation: line-to-ground vs line-to-line (7th review P0-4).

Runs the greedy-support + continuous-sizing pipeline under BOTH metrics over the
SAME seed set, so the only difference is the evaluation metric. Reports:
  * exact base worst voltages (line-to-ground and line-to-line, canonical values);
  * per-seed total capacity under each metric, with median and IQR;
  * the median relative capacity increase 100*(Q_LG-Q_LL)/Q_LL;
  * cross-evaluation: each metric's design assessed on BOTH metrics, separating
    over-provisioning from genuine line-to-line feasibility.
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
V_LOW, V_HIGH, MARGIN, EPS = 0.95, 1.05, 0.006, 2e-4   # unified acceptance 0.9562 (9th review P0-3)
EXCLUDE = {"sourcebus", "799"}
SEEDS = tuple(range(1, 9))


def solve(buses, q):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b, qi in zip(buses, q):
        if qi > 1e-6:
            dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                             f"kW=0 kvar={qi} Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")
    dss.Solution.Solve()


def _vals(metric):
    out = []
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
        nodes = list(dss.Bus.Nodes())
        P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
        if metric == "lg":
            out.extend(abs(v) for v in P.values())
        else:
            out.extend(abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P)
    return out


def worst(metric):
    return min(_vals(metric))


def viol_margin(metric):
    # size to clear the unified acceptance 0.95 + MARGIN + EPS (= 0.9562)
    return float(sum(max(0.0, (V_LOW + MARGIN + EPS) - v) + max(0.0, v - (V_HIGH - MARGIN - EPS)) for v in _vals(metric)))


def size(buses, metric, seed, maxiter=15, pop=8):
    def f(x):
        solve(buses, x); return 1.0e5 * viol_margin(metric) + float(np.sum(x))
    res = differential_evolution(f, [(0.0, QBAR)] * len(buses), maxiter=maxiter,
                                 popsize=pop, tol=1e-2, seed=seed, polish=True, init="sobol")
    x = np.round(np.clip(res.x, 0, QBAR), 1)   # round to 0.1 kvar (installed unit) before check
    solve(buses, x)
    return x, viol_margin(metric)


def greedy(metric, seed):
    # minimum count is established as three; the ablation compares the min-kvar
    # three-device design under each metric at the unified acceptance.
    selected, remaining = [], list(POOL)
    x = None
    for _ in range(3):
        best = None
        for b in remaining:
            cand = selected + [b]
            xc, v = size(cand, metric, seed)
            if best is None or v < best[0]:
                best = (v, b, xc)
        v, b, x = best
        selected.append(b); remaining.remove(b)
        if v <= 1e-6:
            break
    return sorted(selected), float(np.sum(x)), x


def cross_eval(buses, x):
    solve(buses, x)
    return round(worst("lg"), 4), round(worst("ll"), 4)


def main():
    solve([], [])
    base_lg, base_ll = round(worst("lg"), 4), round(worst("ll"), 4)

    lg_kvar, ll_kvar, rel = [], [], []
    lg_sup, ll_sup = {}, {}
    lg_cross, ll_cross = [], []
    for seed in SEEDS:
        sL, qL, xL = greedy("lg", seed)
        sR, qR, xR = greedy("ll", seed)
        lg_kvar.append(qL); ll_kvar.append(qR); rel.append(100.0 * (qL - qR) / qR)
        lg_sup[",".join(sL)] = lg_sup.get(",".join(sL), 0) + 1
        ll_sup[",".join(sR)] = ll_sup.get(",".join(sR), 0) + 1
        lg_cross.append(cross_eval(sL, xL))   # (lg_min, ll_min) of LG design
        ll_cross.append(cross_eval(sR, xR))   # (lg_min, ll_min) of LL design
        print(f"seed {seed}: LG {sL} {qL:.1f} kvar | LL {sR} {qR:.1f} kvar | rel {rel[-1]:.1f}%", flush=True)

    def stats(a):
        return dict(median=round(float(np.median(a)), 1),
                    iqr=[round(float(np.percentile(a, 25)), 1), round(float(np.percentile(a, 75)), 1)],
                    min=round(float(min(a)), 1), max=round(float(max(a)), 1))

    out = dict(
        seeds=list(SEEDS),
        base_worst=dict(line_to_ground=base_lg, line_to_line=base_ll,
                        overstatement_pu=round(base_ll - base_lg, 4)),
        lg_total_kvar=stats(lg_kvar), ll_total_kvar=stats(ll_kvar),
        median_relative_increase_pct=round(float(np.median(rel)), 1),
        lg_support_freq=lg_sup, ll_support_freq=ll_sup,
        lg_design_cross=dict(lg_min=round(float(np.median([c[0] for c in lg_cross])), 4),
                             ll_min=round(float(np.median([c[1] for c in lg_cross])), 4)),
        ll_design_cross=dict(lg_min=round(float(np.median([c[0] for c in ll_cross])), 4),
                             ll_min=round(float(np.median([c[1] for c in ll_cross])), 4)),
    )
    (ROOT / "reports" / "dstatcom_ablation2.json").write_text(json.dumps(out, indent=2))
    print("\n" + json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
