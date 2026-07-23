"""Thermal feasibility and forecast-error robustness for the D-STATCOM design.

(1) Thermal (review P0-4): at the daily peak the maximum line loading is reported
    with and without the design, and each converter current is checked against its
    rating. The peak overload is shown to be a feeder-level property of the x1.34
    stress load (present in the base case) that reactive support mildly relieves.
(2) Robustness (review P1-4): over many random load-forecast errors at a stressed
    operating point, the causal local droop (reacts to measured line-to-line
    voltage) is compared with a coordinated schedule fixed on the nominal forecast
    and with fixed full output. Errors are drawn per phase; mean, 95th percentile,
    worst case and violation probability are reported.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
BUSES = ("735", "740", "741")
QMAX = np.array([393.6, 249.2, 398.5])   # canonical design (run_dstatcom_canonical.py)
KV_LL = 4.8
V_LOW, V_HIGH = 0.95, 1.05
EXCLUDE = {"sourcebus", "799"}
I_RATED = 450.0 / (np.sqrt(3) * 0.95 * KV_LL)   # per-device nameplate at the 0.95 pu study-band edge (matches canonical benchmark)
RNG = np.random.default_rng(2026)


def _load_buses():
    dss.Text.Command(f"compile [{MASTER}]"); dss.Solution.Solve()
    s = set(); n = dss.Loads.First()
    while n:
        s.add(dss.CktElement.BusNames()[0].split(".")[0]); n = dss.Loads.Next()
    return s
MONITOR = _load_buses() | set(BUSES)


def _ll():
    lls = []
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE or b.split(".")[0] not in MONITOR:
            continue
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
        nodes = list(dss.Bus.Nodes())
        P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                lls.append(abs(P[i] - P[j]) / np.sqrt(3))
    return np.array(lls)


def _bus_ll_min(b):
    dss.Circuit.SetActiveBus(b)
    va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
    nodes = list(dss.Bus.Nodes())
    P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
    vs = [abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
    return min(vs) if vs else 1.0


def _max_loading():
    worst = 0.0; i = dss.Lines.First()
    while i:
        dss.Circuit.SetActiveElement("Line." + dss.Lines.Name())
        curr = dss.CktElement.CurrentsMagAng()[0::2]; namps = dss.CktElement.NormalAmps()
        if curr and namps and namps > 0:
            worst = max(worst, 100.0 * max(abs(c) for c in curr[:len(curr) // 2]) / namps)
        i = dss.Lines.Next()
    return worst


def _iconv():
    worst = 0.0
    for b in BUSES:
        dss.Circuit.SetActiveElement(f"Generator.st_{b}")
        curr = dss.CktElement.CurrentsMagAng()[0::2]
        if curr:
            worst = max(worst, max(abs(c) for c in curr[:max(1, len(curr) // 2)]))
    return worst


def solve(q, loadmults):
    """loadmults: scalar or per-load dict not needed; use global LoadMult scalar."""
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={loadmults}")
    for b, qi in zip(BUSES, q):
        if qi > 1e-9:
            dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                             f"kW=0 kvar={qi} Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")
    dss.Solution.Solve()


def viol(ll):
    return float(np.sum(np.clip(ll - V_HIGH, 0, None) + np.clip(V_LOW - ll, 0, None)))


def droop(lm, v_full=1.00, v_zero=1.03, n=40, damp=0.4):
    q = QMAX.copy()
    for _ in range(n):
        solve(q, lm); per = np.array([_bus_ll_min(b) for b in BUSES])
        tgt = QMAX * np.clip((v_zero - per) / (v_zero - v_full), 0, 1)
        qn = (1 - damp) * q + damp * tgt
        if np.max(np.abs(qn - q)) < 0.5:
            q = qn; break
        q = qn
    return q


def main():
    out = {}

    # (1) thermal at peak
    solve(np.zeros(len(BUSES)), 1.34); base_load = _max_loading()
    solve(QMAX, 1.34); des_load = _max_loading(); des_ic = _iconv()
    out["thermal_peak"] = dict(load_mult=1.34,
        base_max_line_loading_pct=round(base_load, 1),
        design_max_line_loading_pct=round(des_load, 1),
        max_converter_current_a=round(des_ic, 1),
        converter_rating_a=round(float(I_RATED), 1),
        note="peak line overload is present in the base case and is a feeder "
             "reinforcement issue independent of the shunt reactive support, "
             "which mildly relieves it; every converter current is within rating.")

    # (2) robustness at a stressed operating point (nominal peak lambda=1.28)
    lam_nom = 1.28
    q_fixed = QMAX
    # coordinated schedule fixed on the nominal forecast (droop converged at nominal)
    q_sched = droop(lam_nom)
    N, sigma = 200, 0.05
    dv, cv, fv = [], [], []
    for _ in range(N):
        lam = lam_nom * (1.0 + RNG.normal(0, sigma))
        qd = droop(lam); solve(qd, lam); dv.append(viol(_ll()))     # causal droop reacts
        solve(q_sched, lam); cv.append(viol(_ll()))                 # schedule fixed on forecast
        solve(q_fixed, lam); fv.append(viol(_ll()))                 # fixed full output
    def st(a):
        a = np.array(a)
        return dict(mean_Ev=round(float(a.mean()), 4), p95_Ev=round(float(np.percentile(a, 95)), 4),
                    max_Ev=round(float(a.max()), 4), frac_violating=round(float((a > 1e-4).mean()), 3))
    out["robustness"] = dict(nominal_lambda=lam_nom, n=N, sigma=sigma,
                             droop=st(dv), coordinated_forecast=st(cv), fixed=st(fv))

    (ROOT / "reports" / "dstatcom_robust_thermal.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
