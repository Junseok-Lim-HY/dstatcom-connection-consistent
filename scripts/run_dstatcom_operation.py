"""Connection-aware 24-h control comparison for the IEEE 37-node D-STATCOM design.

Single canonical evaluator (review P0-1/2/3/8, P1-2/3): every strategy
(base / fixed full output / equivalent capacitor / local voltage-droop /
centrally coordinated benchmark) is solved on the same model and scored on ONE
connection-aware metric -- the line-to-line band aggregate over all monitored
buses (source and regulator-input 799 excluded):

    E_v = sum_t sum_{ll} [ (v_ll - 1.05)_+ + (0.95 - v_ll)_+ ],   dt = 1 h.

The local droop reacts to the device's own line-to-line terminal minimum; the
knee (V_down, V_up) is reconciled here and validated out-of-sample. VUF is taken
from symmetrical-component (sequence) voltages, valid for the delta feeder.
Design: canonical three-device support (run_dstatcom_canonical.py).
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
BUSES = ("735", "740", "741")
QMAX = np.array([393.6, 249.2, 398.5])   # canonical design: lowest-kvar feasible 3-support
                                         # (run_dstatcom_canonical.py, full 120-support enumeration)
KV_LL = 4.8
V_LOW, V_HIGH = 0.95, 1.05
W1, W2, W3 = 2000.0, 20.0, 0.01
EXCLUDE = {"sourcebus", "799"}
# Unified monitored set M (8th review P0-5): all load and device terminals,
# evaluated by connection type. Computed once at import from the base circuit.
def _load_buses():
    dss.Text.Command(f"compile [{MASTER}]"); dss.Solution.Solve()
    s = set(); n = dss.Loads.First()
    while n:
        s.add(dss.CktElement.BusNames()[0].split(".")[0]); n = dss.Loads.Next()
    return s
MONITOR = _load_buses() | set(BUSES)
DAILY = (0.62,0.58,0.55,0.54,0.57,0.65,0.78,0.88,0.95,1.00,1.04,1.08,
         1.10,1.08,1.03,1.00,1.05,1.16,1.28,1.34,1.26,1.08,0.88,0.72)


def _phasors(b):
    dss.Circuit.SetActiveBus(b)
    va = np.array(dss.Bus.puVmagAngle())
    mags, angs, nodes = va[0::2], va[1::2] * np.pi / 180.0, list(dss.Bus.Nodes())
    return {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}


def _bus_ll_min(b):
    P = _phasors(b)
    vs = [abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
    return min(vs) if vs else 1.0


def _all_ll():
    lls = []
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE or b.split(".")[0] not in MONITOR:
            continue
        P = _phasors(b)
        for i, j in ((1, 2), (2, 3), (3, 1)):
            if i in P and j in P:
                lls.append(abs(P[i] - P[j]) / np.sqrt(3))
    return np.array(lls)


def _max_vuf():
    """Max negative-sequence unbalance factor |V2|/|V1| (%) over monitored buses."""
    worst = 0.0
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE:
            continue
        dss.Circuit.SetActiveBus(b)
        seq = dss.Bus.SeqVoltages()
        if len(seq) >= 3 and seq[1] > 1e-6:
            worst = max(worst, 100.0 * seq[2] / seq[1])
    return worst


def _max_lvur():
    """Max NEMA MG-1 line-voltage-unbalance rate (%) over monitored three-phase buses:
    LVUR = max|V_ll - mean(V_ll)| / mean(V_ll) * 100, on line-to-line magnitudes."""
    worst = 0.0
    for b in dss.Circuit.AllBusNames():
        if b.lower() in EXCLUDE or b.split(".")[0] not in MONITOR:
            continue
        P = _phasors(b)
        vll = [abs(P[i] - P[j]) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
        if len(vll) == 3:
            avg = sum(vll) / 3.0
            if avg > 1e-6:
                worst = max(worst, 100.0 * max(abs(v - avg) for v in vll) / avg)
    return worst


def solve(q, lm, device="statcom"):
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command(f"Set LoadMult={lm}")
    for b, qi in zip(BUSES, q):
        if qi <= 1e-9:
            continue
        if device == "statcom":
            dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                             f"kW=0 kvar={qi} Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")
        else:
            dss.Text.Command(f"New Capacitor.c_{b} bus1={b} phases=3 kvar={qi} kv={KV_LL} conn=delta")
    dss.Solution.Solve()
    ll = _all_ll()
    loss = abs(float(dss.Circuit.Losses()[0])) / 1000.0
    per = np.array([_bus_ll_min(b) for b in BUSES])
    return ll, loss, per


def viol(ll):
    return float(np.sum(np.clip(ll - V_HIGH, 0, None) + np.clip(V_LOW - ll, 0, None)))


def op_obj(ll, loss):
    return W1 * viol(ll) + W2 * float(np.sum((ll - 1.0) ** 2)) + W3 * loss


def droop(lm, v_full=1.00, v_zero=1.03, n=400, damp=0.4, epsQ=0.05, q0=None):
    """Local Volt/VAR proxy fixed point. Production tolerance: epsQ=0.05 kvar,
    up to 400 sweeps (16th review P0-6)."""
    q = QMAX.copy() if q0 is None else np.asarray(q0, float).copy()
    for _ in range(n):
        _, _, per = solve(q, lm)
        tgt = QMAX * np.clip((v_zero - per) / (v_zero - v_full), 0, 1)
        qn = (1 - damp) * q + damp * tgt
        if np.max(np.abs(qn - q)) < epsQ:
            q = qn; break
        q = qn
    return q


ACC_LO, ACC_HI = 0.9562, 1.0438     # planning acceptance band (reserve-preserving)


def viol_rp(ll):
    return float(np.sum(np.clip(ll - ACC_HI, 0, None) + np.clip(ACC_LO - ll, 0, None)))


def _coord(lm, vfun):
    def f(x):
        ll, loss, _ = solve(np.clip(x, 0, QMAX), lm)
        return loss + 1.0e6 * vfun(ll)
    best = None
    for s in (1.0, 0.6, 0.3):
        r = minimize(f, QMAX * s, method="Powell", bounds=[(0, m) for m in QMAX],
                     options={"maxiter": 150, "xtol": 1e-2, "ftol": 1e-3})
        best = r if best is None or r.fun < best.fun else best
    return np.clip(best.x, 0, QMAX)


def coordinated(lm):
    """Band-only offline coordinated reference: minimize loss s.t. 0.95-1.05 pu."""
    return _coord(lm, viol)


def coordinated_rp(lm):
    """Reserve-preserving offline coordinated reference: minimize loss s.t. the
    planning acceptance band 0.9562-1.0438 pu (18th review P0-4), so its worst
    minimum is voltage-matched to the local proxy."""
    return _coord(lm, viol_rp)


def _max_line_loading():
    """Worst line current as a percentage of normal ampacity (head-line thermal)."""
    worst = 0.0; i = dss.Lines.First()
    while i:
        dss.Circuit.SetActiveElement("Line." + dss.Lines.Name())
        curr = dss.CktElement.CurrentsMagAng()[0::2]; namps = dss.CktElement.NormalAmps()
        if curr and namps and namps > 0:
            worst = max(worst, 100.0 * max(abs(c) for c in curr[:len(curr) // 2]) / namps)
        i = dss.Lines.Next()
    return worst


def main():
    rows = []
    for h, lm in enumerate(DAILY):
        vb, lb, _ = solve(np.zeros(len(BUSES)), lm)          # base (no device)
        vf, lf, _ = solve(QMAX, lm)                          # fixed full output
        vc, lc, _ = solve(QMAX, lm, "cap")                   # equal-nominal-kvar capacitor
        qd = droop(lm); vd, ld, _ = solve(qd, lm)            # local droop
        qo = coordinated(lm); vo, lo, _ = solve(qo, lm)      # band-only coordinated
        qorp = coordinated_rp(lm); vorp, lorp, _ = solve(qorp, lm)   # reserve-preserving coordinated
        # VUF, NEMA LVUR, and head-line loading per strategy (resolve to set active state)
        solve(np.zeros(len(BUSES)), lm); vuf_b, lvur_b, load_b = _max_vuf(), _max_lvur(), _max_line_loading()
        solve(QMAX, lm); vuf_f, lvur_f, load_f = _max_vuf(), _max_lvur(), _max_line_loading()
        solve(QMAX, lm, "cap"); vuf_c, lvur_c, load_c = _max_vuf(), _max_lvur(), _max_line_loading()
        solve(qd, lm); vuf_d, lvur_d, load_d = _max_vuf(), _max_lvur(), _max_line_loading()
        solve(qo, lm); vuf_o, lvur_o, load_o = _max_vuf(), _max_lvur(), _max_line_loading()
        solve(qorp, lm); load_orp = _max_line_loading()
        rows.append(dict(hour=h, load=lm,
            base_min=vb.min(), base_max=vb.max(), base_viol=viol(vb), base_loss=lb, base_vuf=vuf_b, base_lvur=lvur_b, base_load=load_b,
            fixed_min=vf.min(), fixed_max=vf.max(), fixed_viol=viol(vf), fixed_loss=lf, fixed_vuf=vuf_f, fixed_lvur=lvur_f, fixed_load=load_f,
            cap_min=vc.min(), cap_max=vc.max(), cap_viol=viol(vc), cap_loss=lc, cap_vuf=vuf_c, cap_lvur=lvur_c, cap_load=load_c,
            droop_min=vd.min(), droop_max=vd.max(), droop_viol=viol(vd), droop_loss=ld,
            droop_kvar=float(qd.sum()), droop_vuf=vuf_d, droop_lvur=lvur_d, droop_load=load_d,
            coord_min=vo.min(), coord_max=vo.max(), coord_viol=viol(vo), coord_loss=lo,
            coord_kvar=float(qo.sum()), coord_vuf=vuf_o, coord_lvur=lvur_o, coord_load=load_o,
            coordrp_min=vorp.min(), coordrp_max=vorp.max(), coordrp_viol=viol(vorp), coordrp_loss=lorp,
            coordrp_kvar=float(qorp.sum()), coordrp_load=load_orp))
        print(f"h{h:02d} lm={lm:.2f} base {vb.min():.4f}/{vb.max():.4f} v{viol(vb):.3f}"
              f" | fixed {vf.min():.4f}/{vf.max():.4f} v{viol(vf):.3f}"
              f" | cap {vc.max():.4f} v{viol(vc):.3f}"
              f" | droop {vd.min():.4f}/{vd.max():.4f} v{viol(vd):.3f}"
              f" | coord {vo.min():.4f}/{vo.max():.4f} v{viol(vo):.3f}", flush=True)

    with (ROOT / "reports" / "dstatcom_operation_24h.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    def agg(p):
        d = dict(worst_min=round(min(r[f"{p}_min"] for r in rows), 4),
                 max_v=round(max(r[f"{p}_max"] for r in rows), 4),
                 Ev=round(sum(r[f"{p}_viol"] for r in rows), 4),
                 energy_loss_kwh=round(sum(r[f"{p}_loss"] for r in rows), 1))
        if f"{p}_vuf" in rows[0]:
            d["max_vuf_pct"] = round(max(r[f"{p}_vuf"] for r in rows), 2)
        if f"{p}_lvur" in rows[0]:
            d["max_lvur_pct"] = round(max(r[f"{p}_lvur"] for r in rows), 2)
        if f"{p}_load" in rows[0]:
            d["max_line_loading_pct"] = round(max(r[f"{p}_load"] for r in rows), 1)
        return d
    # initialization-independence of the proxy fixed point at the peak hour (16th review P0-6)
    lm_pk = max(DAILY)
    inits = {"zero": np.zeros(len(BUSES)), "half": 0.5 * QMAX, "full": QMAX.copy()}
    conv = {k: droop(lm_pk, q0=q0) for k, q0 in inits.items()}
    spread = float(max(np.max(np.abs(conv[a] - conv[b]))
                       for a in conv for b in conv))
    proxy_init = dict(epsQ=0.05, max_sweeps=400,
                      init_spread_kvar=round(spread, 3),
                      init_independent=bool(spread < 0.1))
    print(f"proxy init-independence: max spread {spread:.3f} kvar across "
          f"{list(inits)} inits", flush=True)
    # proxy loss capture measured against the voltage-matched reserve-preserving reference
    f_, dr_, corp_ = (agg("fixed")["energy_loss_kwh"], agg("droop")["energy_loss_kwh"],
                      agg("coordrp")["energy_loss_kwh"])
    capture_rp = round(100.0 * (f_ - dr_) / (f_ - corp_)) if (f_ - corp_) else None
    summary = dict(design_buses=list(BUSES), total_kvar=round(float(QMAX.sum()), 1),
                   proxy_setting=proxy_init,
                   proxy_capture_vs_reserve_preserving_pct=capture_rp,
                   base=agg("base"), fixed=agg("fixed"), cap=agg("cap"),
                   droop=agg("droop"), coord=agg("coord"), coordrp=agg("coordrp"))
    (ROOT / "reports" / "dstatcom_operation_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n== OPERATION SUMMARY ==\n" + json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
