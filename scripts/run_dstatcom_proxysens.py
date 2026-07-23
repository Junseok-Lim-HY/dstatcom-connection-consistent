"""Local Volt/VAR proxy parameter sensitivity (7th review P1-7).

Sweeps the droop knee (V_down, V_up) and damping beta over a small grid on the
24-hour profile for the canonical design, reporting daily band violation E_v,
daily energy loss, mean iterations to converge, and the share of the coordinated
loss reduction captured. Establishes whether the reported loss-capture percentage
is tuning-robust or tuning-specific.
"""
from __future__ import annotations
import json, itertools
from pathlib import Path
import numpy as np
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
KV_LL, V_LOW, V_HIGH = 4.8, 0.95, 1.05
EXCLUDE = {"sourcebus", "799"}
DAILY = (0.62, 0.58, 0.55, 0.54, 0.57, 0.65, 0.78, 0.88, 0.95, 1.00, 1.04, 1.08,
         1.10, 1.08, 1.03, 1.00, 1.05, 1.16, 1.28, 1.34, 1.26, 1.08, 0.88, 0.72)

_c = json.load(open(ROOT / "reports" / "dstatcom_canonical.json"))["canonical"]
BUSES = tuple(_c["support"])
QMAX = np.array(_c["q_kvar"])
_op = json.load(open(ROOT / "reports" / "dstatcom_operation_summary.json"))
BASE_LOSS = _op["fixed"]["energy_loss_kwh"]          # fixed full output daily loss
COORD_LOSS = _op["coord"]["energy_loss_kwh"]          # coordinated reference daily loss


def solve(q, lm):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={lm}")
    for b, qi in zip(BUSES, q):
        if qi > 1e-9:
            dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                             f"kW=0 kvar={qi} Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")
    dss.Solution.Solve()
    lls, per = [], []
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
        nodes = list(dss.Bus.Nodes())
        P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                lls.append(abs(P[i] - P[j]) / np.sqrt(3))
    lo = np.array(lls)
    loss = abs(float(dss.Circuit.Losses()[0])) / 1000.0
    for b in BUSES:
        dss.Circuit.SetActiveBus(b)
        va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
        nodes = list(dss.Bus.Nodes())
        Pp = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
        vv = [abs(Pp[i] - Pp[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in Pp and j in Pp]
        per.append(min(vv) if vv else 1.0)
    return lo, loss, np.array(per)


def viol(ll):
    return float(np.sum(np.clip(ll - V_HIGH, 0, None) + np.clip(V_LOW - ll, 0, None)))


def droop(lm, v_full, v_zero, damp, n=400, epsQ=0.05):
    q = QMAX.copy(); it = 0
    for it in range(1, n + 1):
        _, _, per = solve(q, lm)
        tgt = QMAX * np.clip((v_zero - per) / (v_zero - v_full), 0, 1)
        qn = (1 - damp) * q + damp * tgt
        if np.max(np.abs(qn - q)) < epsQ:
            q = qn; break
        q = qn
    ll, loss, _ = solve(q, lm)
    return ll, loss, it


def run(v_full, v_zero, damp):
    Ev, loss, iters = 0.0, 0.0, []
    for lm in DAILY:
        ll, ls, it = droop(lm, v_full, v_zero, damp)
        Ev += viol(ll); loss += ls; iters.append(it)
    cap = 100.0 * (BASE_LOSS - loss) / (BASE_LOSS - COORD_LOSS) if BASE_LOSS > COORD_LOSS else float("nan")
    return dict(v_down=v_full, v_up=v_zero, beta=damp, Ev=round(Ev, 4),
                loss_kwh=round(loss, 1), mean_iters=round(float(np.mean(iters)), 1),
                pct_coord_capture=round(cap, 1))


def main():
    rows = []
    base = (1.00, 1.03, 0.4)
    grid = [base]
    for vd in (0.99, 1.00, 1.01):
        for vu in (1.02, 1.03, 1.04):
            for be in (0.2, 0.4, 0.6):
                if (vd, vu, be) != base and vu > vd:
                    grid.append((vd, vu, be))
    for vd, vu, be in grid:
        r = run(vd, vu, be); rows.append(r)
        print(json.dumps(r), flush=True)
    caps = [r["pct_coord_capture"] for r in rows if r["Ev"] < 1e-6]
    out = dict(base_setting=dict(v_down=base[0], v_up=base[1], beta=base[2]),
               base_row=rows[0], n_settings=len(rows),
               all_feasible=all(r["Ev"] < 1e-6 for r in rows),
               capture_pct_min=round(min(caps), 1) if caps else None,
               capture_pct_max=round(max(caps), 1) if caps else None,
               rows=rows)
    (ROOT / "reports" / "dstatcom_proxysens.json").write_text(json.dumps(out, indent=2))
    print("\ncapture range over feasible settings:",
          out["capture_pct_min"], "-", out["capture_pct_max"], flush=True)


if __name__ == "__main__":
    main()
