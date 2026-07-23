"""Build the canonical + ablation reports from the single-evaluator full-recompile
enumeration. Reads reports/dstatcom_twostage_fullrecompile.json (one evaluator for all
120 LL + 120 LG supports) and fresh-computes device currents, benchmarks, and
cross-metric minima with a full recompile. This is the only script that writes the
adopted canonical design/ablation JSONs; run_dstatcom_ablation_enum.py is a legacy
stand-alone enumerator kept for cross-checking and is not the numerical source of
record.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
REP = ROOT / "reports"
KV_LL, PEAK, V_LOW, V_HIGH, MARGIN, V_RATE = 4.8, 1.34, 0.95, 1.05, 0.006, 0.95
EXCLUDE = {"sourcebus", "799"}

full = json.load(open(REP / "dstatcom_twostage_fullrecompile.json"))


def build(buses, q):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={PEAK}")
    for b, qi in zip(buses, q):
        if qi > 1e-6:
            dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                             f"kW=0 kvar={qi} Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")
    dss.Solution.Solve()


def mins():
    llo, lhi, glo, ghi = 2.0, 0.0, 2.0, 0.0
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); m = va[0::2]; a = va[1::2] * np.pi / 180.0
        nd = list(dss.Bus.Nodes())
        P = {n: mm * np.exp(1j * aa) for mm, aa, n in zip(m, a, nd) if n in (1, 2, 3)}
        for v in P.values():
            glo = min(glo, abs(v)); ghi = max(ghi, abs(v))
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                v = abs(P[i] - P[j]) / np.sqrt(3); llo = min(llo, v); lhi = max(lhi, v)
    return round(llo, 4), round(lhi, 4), round(glo, 4), round(ghi, 4)


def currents(buses):
    out = []
    for b in buses:
        dss.Circuit.SetActiveElement(f"Generator.st_{b}")
        curr = dss.CktElement.CurrentsMagAng()[0::2]
        out.append(max(abs(c) for c in curr[:3]) if curr else 0.0)
    return out


ll = full["ll_best"]; lb, lq = ll["support"], ll["q"]
build(lb, lq)
llo, lhi, lg_cross_min, lg_cross_max = mins()
ic = currents(lb)
rated = [float(qi) / (np.sqrt(3) * V_RATE * KV_LL) for qi in lq]

lg = full["lg_best"]; gb, gq = lg["support"], lg["q"]
build(gb, gq)
g_llo, g_lhi, glo, ghi = mins()

ll_ranked = full["ll_ranked"]
all_supports = sorted(
    ({"support": r["support"], "total_kvar": r["total_kvar"], "feasible": True,
      "min_v": r["min_v"]} for r in ll_ranked), key=lambda r: r["total_kvar"])

canonical = dict(
    method="single-evaluator two-stage full enumeration of 120 supports, full feeder "
           "recompilation at every objective evaluation",
    n_supports=120, n_feasible=full["n_feasible_ll"],
    margin=MARGIN, band_edges=[V_LOW + MARGIN, V_HIGH - MARGIN],
    feasible_ranked=ll_ranked[:15],
    canonical=dict(
        support=lb, q_kvar=lq, total_kvar=ll["total_kvar"], min_v=llo, max_v=lhi,
        margin_above_0p95=round(llo - V_LOW, 4),
        dev_current_a=[round(float(v), 1) for v in ic],
        dev_benchmark_a=[round(float(v), 1) for v in rated],
        current_ok=bool(all(a <= r + 1e-6 for a, r in zip(ic, rated)))),
    all_supports=all_supports,
    seed1_design=dict(support=["711", "737", "740"], total_kvar=1037.0))
(REP / "dstatcom_canonical.json").write_text(json.dumps(canonical, indent=2))

ablation = dict(
    method="single-evaluator two-stage full enumeration under each metric; full "
           "feeder recompilation at every objective evaluation",
    seeds=[1, 2], margin=MARGIN,
    base_worst=dict(line_to_ground=0.8803, line_to_line=0.8986, overstatement_pu=0.0183),
    lg_design=dict(support=gb, total_kvar=lg["total_kvar"], q_kvar=gq, min_v_lg=glo),
    ll_design=dict(support=lb, total_kvar=ll["total_kvar"], q_kvar=lq, min_v_ll=llo),
    lg_design_cross=dict(lg_min=glo, ll_min=g_llo),
    ll_design_cross=dict(lg_min=lg_cross_min, ll_min=llo),
    relative_increase_pct=full["relative_increase_pct"],
    n_feasible_lg=full["n_feasible_lg"], n_feasible_ll=full["n_feasible_ll"],
    lg_top5=full["lg_top5"], ll_top5=full["ll_top5"],
    design_minmax=dict(ll_min=llo, ll_max=lhi, lg_min=glo, lg_max=ghi))
(REP / "dstatcom_ablation_enum.json").write_text(json.dumps(ablation, indent=2))

print("== CANONICAL (LL, single evaluator) ==")
print(" support", lb, "q", lq, "total", ll["total_kvar"], "min/max", llo, lhi, "| lg cross", lg_cross_min)
print(" currents", [round(v, 1) for v in ic], "benchmark", [round(v, 1) for v in rated],
      "ok", bool(all(a <= r + 1e-6 for a, r in zip(ic, rated))))
print("== LG ==", gb, lg["total_kvar"], "min/max", glo, ghi, "| ll cross", g_llo,
      "| rel", full["relative_increase_pct"])
print("n_feasible LL/LG", full["n_feasible_ll"], full["n_feasible_lg"])
print("LL top5", full["ll_top5"])
print("LG top5", full["lg_top5"])
import numpy as _np
tot = _np.array([r["total_kvar"] for r in ll_ranked])
print("LL median %.1f p95 %.1f max %.1f  adopted %.1f%% below median"
      % (_np.median(tot), _np.percentile(tot, 95), tot.max(),
         100 * (_np.median(tot) - ll["total_kvar"]) / _np.median(tot)))
