"""VSC converter-loss quantitative post-processing (resubmission, Reviewer 3-1).

No new power flow is run. From the 24-hour operation report (per-hour dispatched Q
and feeder losses already computed) we (i) estimate the converter switching+conduction
loss with a standard three-term VSC model, (ii) net it against the feeder-loss change,
and (iii) report the daily net energy effect, its sensitivity to the assumed converter
efficiency, and the break-even efficiency. This makes the R3-1 answer quantitative and,
crucially, shows that because the local/coordinated controls REDUCE converter output at
light load, they also reduce converter loss — so the naive statement "losses uniformly
erode the benefit" is inaccurate; the fixed-full-output mode is the energy-costly one.

Converter loss model (per device, S in kvar, rated S_r = 450 kvar):
    P_loss(S) = L_tot * S_r * ( f_sw + f_a*(S/S_r) + f_b*(S/S_r)^2 ),
    f_sw:f_a:f_b = 0.4:0.2:0.4  (switching-dominated no-load + linear + ohmic conduction),
so P_loss(S_r) = L_tot * S_r  (L_tot = total loss at rated, swept 1.0-2.5%).
Per-device Q for the dispatch controls is apportioned to the nameplate split
QMAX=[393.6,249.2,398.5] (stated approximation; fixed uses the exact nameplate).
Assumptions are declared; results are reported as-is.
"""
from __future__ import annotations
import csv, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
QMAX = np.array([393.6, 249.2, 398.5])         # per-device kvar
S_R = 450.0                                     # per-device rating (kvar)
F_SW, F_A, F_B = 0.4, 0.2, 0.4                  # loss split (sum=1 at rated)
L_TOT_SWEEP = (0.010, 0.015, 0.020, 0.025)      # total converter loss at rated (fraction)


def ploss_device(S, l_tot):
    s = np.clip(S, 0, None) / S_R
    return l_tot * S_R * (F_SW + F_A * s + F_B * s * s)   # kW per device


def per_device_Q(control, total_kvar):
    if control == "fixed":
        return QMAX.copy()
    frac = QMAX / QMAX.sum()
    return total_kvar * frac


def main():
    rows = list(csv.DictReader((ROOT / "reports" / "dstatcom_operation_24h.csv").open()))
    hours = len(rows)
    base_loss = np.array([float(r["base_loss"]) for r in rows])           # kW feeder loss, no device
    control_kvar = {
        "fixed": np.full(hours, float(QMAX.sum())),
        "droop": np.array([float(r["droop_kvar"]) for r in rows]),
        "coord": np.array([float(r["coord_kvar"]) for r in rows]),
    }
    control_feeder_loss = {
        "fixed": np.array([float(r["fixed_loss"]) for r in rows]),
        "droop": np.array([float(r["droop_loss"]) for r in rows]),
        "coord": np.array([float(r["coord_loss"]) for r in rows]),
    }
    out = dict(method="VSC converter-loss post-processing over the 24-hour operation profile",
               loss_model=dict(split_sw_a_b=[F_SW, F_A, F_B], S_rated_kvar=S_R,
                               per_device_split="proportional to nameplate QMAX",
                               L_tot_sweep=list(L_TOT_SWEEP)),
               hours=hours, controls={})
    for ctrl in ("fixed", "droop", "coord"):
        # feeder-loss reduction vs base (positive = the design lowers feeder loss); kWh over the day
        feeder_reduction_kWh = float(np.sum(base_loss - control_feeder_loss[ctrl]))
        mean_total_Q = float(np.mean(control_kvar[ctrl]))
        by_ltot = {}
        for l_tot in L_TOT_SWEEP:
            conv_loss_kWh = 0.0
            for h in range(hours):
                qd = per_device_Q(ctrl, control_kvar[ctrl][h])
                conv_loss_kWh += float(np.sum(ploss_device(qd, l_tot)))   # kW*1h = kWh
            net = feeder_reduction_kWh - conv_loss_kWh
            by_ltot[f"L_tot={l_tot}"] = dict(
                converter_energy_loss_kWh=round(conv_loss_kWh, 1),
                net_daily_energy_kWh=round(net, 1))
        # break-even L_tot where net = 0  (net = feeder_red - k*L_tot, linear in L_tot)
        k = by_ltot["L_tot=0.015"]["converter_energy_loss_kWh"] / 0.015   # kWh per unit L_tot
        be = feeder_reduction_kWh / k if k > 0 else None
        out["controls"][ctrl] = dict(
            mean_total_kvar=round(mean_total_Q, 1),
            feeder_loss_reduction_kWh=round(feeder_reduction_kWh, 1),
            by_L_tot=by_ltot,
            breakeven_L_tot_frac=round(be, 4) if be is not None else None,
            breakeven_converter_efficiency_pct=round(100 * (1 - be), 3) if be is not None else None)
        print(f"{ctrl:6s} meanQ={mean_total_Q:7.1f} feeder_red={feeder_reduction_kWh:8.1f}kWh "
              f"| net@1.5%={by_ltot['L_tot=0.015']['net_daily_energy_kWh']:8.1f}kWh "
              f"break-even L_tot={('%.3f'%be) if be else 'n/a'}", flush=True)
    (ROOT / "reports" / "dstatcom_vscloss.json").write_text(json.dumps(out, indent=2))
    print("\nSAVED reports/dstatcom_vscloss.json", flush=True)


if __name__ == "__main__":
    main()
