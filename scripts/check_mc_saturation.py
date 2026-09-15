# -*- coding: utf-8 -*-
"""Professor's review item 5: the three controllers report IDENTICAL violation rates,
worst voltages, VUF and LVUR, while their mean kvar differs by ~4 %.

The manuscript explains this by saying every controller saturates at full output in the
stressed samples. This script tests that claim directly: for each Monte-Carlo draw it
records the hour, the actually applied per-device Q of each controller, and whether the
sample violates, so the saturated fraction can be reported instead of asserted.

It re-uses the Monte-Carlo module unchanged (import, not copy) so the sampling is identical.
"""
import io
import json
import sys
from pathlib import Path

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_dstatcom_montecarlo as mc   # noqa: E402

V_LOW, V_HIGH = mc.V_LOW, mc.V_HIGH
N_CHECK = 400          # enough to characterise the violating tail without a full re-run


def main():
    # reproduce main()'s setup exactly
    mc.compile_base(); mc.dss.Solution.Solve()
    loads = mc.read_loads()
    mon = set(mc.BUSES)
    n = mc.dss.Loads.First()
    while n:
        mon.add(mc.dss.CktElement.BusNames()[0].split(".")[0])
        n = mc.dss.Loads.Next()
    monitor = sorted(mon)
    mc.add_gens()
    daily = mc.load_daily()
    qsched = []
    for lam in daily:
        mc.set_loads(loads, np.ones(len(loads)), lam)
        qsched.append([round(x, 1) for x in mc.droop_local(monitor).tolist()])
    QMAX = mc.QMAX
    print("QMAX per device:", list(QMAX), "sum=%.1f" % float(np.sum(QMAX)))
    print("monitored buses:", len(monitor))
    print()

    for sigma_phase, sigma_load in mc.SIGMA_CASES:
        rng = np.random.default_rng(mc.SEED)
        rows = []
        for _ in range(N_CHECK):
            h = int(rng.integers(0, len(daily)))
            lam = daily[h]
            e_phase = rng.normal(0, sigma_phase, 3)
            e_load = rng.normal(0, sigma_load, len(loads))
            mults = np.array([max(0.05, 1.0 + e_phase[ph - 1] + el)
                              for (_, _, _, ph), el in zip(loads, e_load)])
            rec = dict(hour=h, lam=float(lam))
            for mode in ("fixed", "schedule", "droop"):
                mc.set_loads(loads, mults, lam)
                if mode == "droop":
                    q = mc.droop_local(monitor)
                else:
                    q = QMAX if mode == "fixed" else np.array(qsched[h])
                    mc.install_gen(q)
                    mc.dss.Solution.Solve()
                mn, mx, lv, vf = mc.metrics(monitor)
                rec[mode] = dict(q=[round(float(v), 1) for v in np.atleast_1d(q)],
                                 qtot=round(float(np.sum(q)), 1),
                                 minv=round(mn, 5), viol=bool(mn < V_LOW or mx > V_HIGH))
            rows.append(rec)

        viol = [r for r in rows if r["fixed"]["viol"]]
        print("=== sigma_phase=%.2f sigma_load=%.2f  (%d draws) ===" % (sigma_phase, sigma_load, N_CHECK))
        print("  violating draws: %d (%.2f%%)" % (len(viol), 100 * len(viol) / len(rows)))
        same_viol = sum(1 for r in rows
                        if r["fixed"]["viol"] == r["schedule"]["viol"] == r["droop"]["viol"])
        print("  draws where all three controllers agree on violate/not: %d / %d" % (same_viol, len(rows)))
        if viol:
            full = sum(1 for r in viol
                       if abs(r["droop"]["qtot"] - float(np.sum(QMAX))) < 1.0)
            fulls = sum(1 for r in viol
                        if abs(r["schedule"]["qtot"] - float(np.sum(QMAX))) < 1.0)
            print("  in violating draws: droop at full output %d/%d, schedule at full output %d/%d"
                  % (full, len(viol), fulls, len(viol)))
            print("  sample of violating draws:")
            for r in viol[:5]:
                print("    hour %2d lam=%.3f | fixed %.1f (minv %.5f) | sched %.1f (minv %.5f) | droop %.1f (minv %.5f)"
                      % (r["hour"], r["lam"], r["fixed"]["qtot"], r["fixed"]["minv"],
                         r["schedule"]["qtot"], r["schedule"]["minv"],
                         r["droop"]["qtot"], r["droop"]["minv"]))
        if viol:
            hours = {}
            for r in viol:
                hours[r["hour"]] = hours.get(r["hour"], 0) + 1
            print("  hours of ALL violating draws (hour: count): %s" % dict(sorted(hours.items())))
            print("  load multipliers of ALL violating draws: %s" % sorted(set(round(r["lam"], 3) for r in viol)))
        # how often do the controllers differ at all? (tolerance 1e-6 pu on the minimum line-to-line voltage)
        diff = sum(1 for r in rows if abs(r["fixed"]["minv"] - r["droop"]["minv"]) > 1e-6)
        print("  draws where fixed and droop give a different min voltage: %d / %d" % (diff, len(rows)))
        print()


if __name__ == "__main__":
    main()
