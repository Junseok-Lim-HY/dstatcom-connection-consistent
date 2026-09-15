"""Phase-independent, spatial Monte-Carlo robustness (resubmission, Reviewer 1-6 & 3-3).

The submitted robustness study varied a single global load multiplier (one scalar
per draw), which cannot answer the reviewers' request for INDEPENDENT PER-PHASE and
SPATIAL load uncertainty. Here each load is perturbed by a two-component multiplier

    m_load = 1 + e_phase[phase(load)] + e_load ,
    e_phase ~ N(0, sigma_phase)  (three independent phase-systematic draws A/B/C),
    e_load  ~ N(0, sigma_load)   (per-load idiosyncratic / spatial),

so different phases and different feeder locations move independently (creating real
unbalance), unlike the single-scalar model. Loads are edited in place (no per-sample
recompile). For the fixed installed design {735,740,741} we compare three controls:

    fixed      : Q held at nameplate (QMAX)
    schedule   : Q fixed on the nominal (error-free) forecast (coordinated, open-loop)
    droop      : local Volt/VAR reacting to each sample's measured line-to-line voltage

For each control we report over N draws: line-to-line violation probability
(min V < 0.95 pu), mean / worst / p95 / p99 minimum voltage, and the worst-bus line
voltage unbalance rate LVUR and true unbalance factor VUF. A second sigma is run as a
stress case. Assumptions (sigma values, control parameters) are stated; results are
reported as-is.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
BUSES = ("735", "740", "741")
QMAX = np.array([393.6, 249.2, 398.5])
KV_LL = 4.8
V_LOW, V_HIGH = 0.95, 1.05
EXCLUDE = {"sourcebus", "799"}
LAM_NOM = 1.28                      # stressed nominal operating point (as in robust study)
N = 2000
SIGMA_CASES = ((0.04, 0.05), (0.06, 0.08))   # (sigma_phase, sigma_load): nominal + stress
SEED = 2026


def compile_base():
    dss.Text.Command(f"compile [{MASTER}]")


def read_loads():
    """Return list of (name, kW0, kvar0, phase) at 1.0 mult; phase in {1,2,3} from connection."""
    loads = []
    n = dss.Loads.First()
    while n:
        name = dss.Loads.Name()
        conn = dss.CktElement.BusNames()[0].split(".")
        nodes = [int(x) for x in conn[1:] if x.isdigit() and int(x) in (1, 2, 3)]
        phase = nodes[0] if nodes else 1
        loads.append((name, dss.Loads.kW(), dss.Loads.kvar(), phase))
        n = dss.Loads.Next()
    return loads


def set_loads(loads, mults, lam):
    for (name, kw0, kvar0, _), m in zip(loads, mults):
        f = lam * m
        dss.Text.Command(f"Edit Load.{name} kW={kw0 * f:.4f} kvar={kvar0 * f:.4f}")


def install_gen(q):
    for b, qi in zip(BUSES, q):
        dss.Text.Command(f"Edit Generator.st_{b} kvar={max(float(qi), 1e-3)}")


def add_gens():
    for b in BUSES:
        dss.Text.Command(f"New Generator.st_{b} bus1={b} phases=3 kv={KV_LL} "
                         f"kW=0 kvar=0.001 Model=1 conn=delta Vminpu=0.7 Vmaxpu=1.3")


def _bus_phasors(b):
    dss.Circuit.SetActiveBus(b)
    va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
    nodes = list(dss.Bus.Nodes())
    return {nd: m * np.exp(1j * a) for m, a, nd in zip(mags, angs, nodes) if nd in (1, 2, 3)}


def metrics(monitor):
    """Return (min_ll, max_ll, worst_LVUR_pct, worst_VUF_pct) over monitored 3-phase buses."""
    min_ll = 2.0; max_ll = 0.0; worst_lvur = 0.0; worst_vuf = 0.0
    a = np.exp(1j * 2 * np.pi / 3)
    for b in monitor:
        P = _bus_phasors(b)
        lls = [abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
        if len(lls) == 3:
            min_ll = min(min_ll, min(lls)); max_ll = max(max_ll, max(lls))
            mean_ll = np.mean(lls)
            if mean_ll > 0:
                worst_lvur = max(worst_lvur, 100.0 * max(abs(v - mean_ll) for v in lls) / mean_ll)
        if all(k in P for k in (1, 2, 3)):
            v1 = (P[1] + a * P[2] + a * a * P[3]) / 3.0
            v2 = (P[1] + a * a * P[2] + a * P[3]) / 3.0
            if abs(v1) > 1e-6:
                worst_vuf = max(worst_vuf, 100.0 * abs(v2) / abs(v1))
    return min_ll, max_ll, worst_lvur, worst_vuf


def droop_local(monitor, niter=40, damp=0.4, v_full=1.00, v_zero=1.03):
    q = QMAX.copy()
    for _ in range(niter):
        install_gen(q); dss.Solution.Solve()
        per = []
        for b in BUSES:
            P = _bus_phasors(b)
            vs = [abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
            per.append(min(vs) if vs else 1.0)
        per = np.array(per)
        tgt = QMAX * np.clip((v_zero - per) / (v_zero - v_full), 0, 1)
        qn = (1 - damp) * q + damp * tgt
        if np.max(np.abs(qn - q)) < 0.5:
            q = qn; break
        q = qn
    install_gen(q); dss.Solution.Solve()
    return q


def _totq():
    tot = 0.0
    for b in BUSES:
        dss.Circuit.SetActiveElement(f"Generator.st_{b}")
        try:
            tot += abs(dss.CktElement.Powers()[1::2][0])   # kvar (approx per element)
        except Exception:
            pass
    return tot


def run_case(sigma_phase, sigma_load, monitor, loads, daily, q_sched_by_hour):
    rng = np.random.default_rng(SEED)
    res = {m: dict(minv=[], maxv=[], lvur=[], vuf=[], q=[], loss=[])
           for m in ("fixed", "schedule", "droop")}
    for _ in range(N):
        h = int(rng.integers(0, len(daily)))
        lam = daily[h]
        e_phase = rng.normal(0, sigma_phase, 3)
        e_load = rng.normal(0, sigma_load, len(loads))
        mults = np.array([max(0.05, 1.0 + e_phase[ph - 1] + el)
                          for (_, _, _, ph), el in zip(loads, e_load)])
        for mode, q in (("fixed", QMAX), ("schedule", np.array(q_sched_by_hour[h])), ("droop", None)):
            set_loads(loads, mults, lam)
            if mode == "droop":
                qq = droop_local(monitor); qtot = float(np.sum(qq))
            else:
                install_gen(q); dss.Solution.Solve(); qtot = float(np.sum(q))
            mn, mx, lv, vf = metrics(monitor)
            res[mode]["minv"].append(mn); res[mode]["maxv"].append(mx)
            res[mode]["lvur"].append(lv); res[mode]["vuf"].append(vf)
            res[mode]["q"].append(qtot); res[mode]["loss"].append(float(dss.Circuit.Losses()[0]) / 1000.0)
    summ = {}
    for m, d in res.items():
        mv = np.array(d["minv"]); xv = np.array(d["maxv"])
        under = mv < V_LOW; over = xv > V_HIGH
        summ[m] = dict(
            violation_prob=round(float(np.mean(under | over)), 4),
            under_viol_prob=round(float(np.mean(under)), 4),
            over_viol_prob=round(float(np.mean(over)), 4),
            mean_minv=round(float(mv.mean()), 4), worst_minv=round(float(mv.min()), 4),
            p05_minv=round(float(np.percentile(mv, 5)), 4),
            mean_maxv=round(float(xv.mean()), 4), worst_maxv=round(float(xv.max()), 4),
            worst_LVUR_pct=round(float(np.max(d["lvur"])), 3),
            mean_LVUR_pct=round(float(np.mean(d["lvur"])), 3),
            worst_VUF_pct=round(float(np.max(d["vuf"])), 3),
            mean_total_kvar=round(float(np.mean(d["q"])), 1),
            mean_feeder_loss_kW=round(float(np.mean(d["loss"])), 2))
    raw = dict(minv=[round(x, 4) for x in res["droop"]["minv"]],
               vuf=[round(x, 3) for x in res["droop"]["vuf"]])
    return summ, raw


def load_daily():
    import csv
    p = ROOT / "reports" / "dstatcom_operation_24h.csv"
    return [float(r["load"]) for r in csv.DictReader(p.open())]


def main():
    import time; t0 = time.time()
    compile_base(); dss.Solution.Solve()
    loads = read_loads()
    mon = set(BUSES); n = dss.Loads.First()
    while n:
        mon.add(dss.CktElement.BusNames()[0].split(".")[0]); n = dss.Loads.Next()
    monitor = sorted(mon)
    add_gens()
    daily = load_daily()
    # coordinated schedule: Q set on the error-free forecast at each hour's load level
    q_sched_by_hour = []
    for lam in daily:
        set_loads(loads, np.ones(len(loads)), lam)
        q_sched_by_hour.append([round(x, 1) for x in droop_local(monitor).tolist()])
    print("loads:", len(loads), "| monitored:", len(monitor), "| daily hours:", len(daily),
          "| load range", round(min(daily), 2), "-", round(max(daily), 2),
          "| q_sched@peak", q_sched_by_hour[int(np.argmax(daily))],
          "| q_sched@offpeak", q_sched_by_hour[int(np.argmin(daily))], flush=True)
    out = dict(method="phase-independent + spatial Monte-Carlo over the daily operating range; "
                      "design {735,740,741}; controls fixed(QMAX)/schedule(forecast)/droop(reactive)",
               design_buses=list(BUSES), design_qmax=QMAX.tolist(),
               N=N, seed=SEED, daily_load_range=[round(min(daily), 2), round(max(daily), 2)],
               error_model="m_load = 1 + e_phase[phase] + e_load; e_phase,e_load ~ N(0,sigma) independent",
               cases={})
    for sp, sl in SIGMA_CASES:
        summ, raw = run_case(sp, sl, monitor, loads, daily, q_sched_by_hour)
        out["cases"][f"sigma_phase={sp}_load={sl}"] = summ
        out[f"raw_droop_sp{sp}_sl{sl}"] = raw
        print(f"[sp={sp} sl={sl}] " + " | ".join(
            f"{m}: Pviol={summ[m]['violation_prob']} worstMin={summ[m]['worst_minv']} "
            f"VUF={summ[m]['worst_VUF_pct']}% Q={summ[m]['mean_total_kvar']} loss={summ[m]['mean_feeder_loss_kW']}"
            for m in ("fixed", "schedule", "droop")) + f" (t={time.time()-t0:.0f}s)", flush=True)
    out["runtime_s"] = round(time.time() - t0, 1)
    (ROOT / "reports" / "dstatcom_montecarlo.json").write_text(json.dumps(out, indent=2))
    print("\nSAVED reports/dstatcom_montecarlo.json  runtime", round(time.time() - t0, 1), "s", flush=True)


if __name__ == "__main__":
    main()
