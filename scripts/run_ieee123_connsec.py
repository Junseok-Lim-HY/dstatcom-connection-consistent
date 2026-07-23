"""IEEE 123-node connection-consistent security minimum (7th review P0-2, P1-10).

The security metric must use each load terminal's connection-appropriate voltage:
line-to-neutral at grounded-wye loads, line-to-line at delta loads. The previous
table wrongly reported the L-N node value 0.9643 pu at delta bus 65 as the worst
minimum; a delta terminal's connection-consistent value is its line-to-line
magnitude, so the L-N node value must be excluded from the security set.

This script builds the monitored set M_123 = {every load terminal, evaluated on its
own connection type} over the full 24-hour profile with native controls active
(controlmode=static), and reports the true connection-consistent worst minimum with
its binding bus, connection, phase/phase-pair, and hour. The 0.9643-pu L-N node
value at bus 65 is retained separately as an auxiliary node diagnostic.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee123_dss" / "Master.DSS").resolve()
DAILY = (0.62, 0.58, 0.55, 0.54, 0.57, 0.65, 0.78, 0.88, 0.95, 1.00, 1.04, 1.08,
         1.10, 1.08, 1.03, 1.00, 1.05, 1.16, 1.28, 1.34, 1.26, 1.08, 0.88, 0.72)
PAIR = {(1, 2): "ab", (2, 3): "bc", (3, 1): "ca"}


def load_terminals():
    """List of (bus, conn, nodes) for every load, from a base compile."""
    dss.Text.Command(f"compile [{MASTER}]")
    dss.Text.Command("set controlmode=static")
    dss.Solution.Solve()
    terms = []
    n = dss.Loads.First()
    while n:
        conn = "delta" if dss.Loads.IsDelta() else "wye"
        bus_full = dss.CktElement.BusNames()[0]
        bus = bus_full.split(".")[0]
        nodes = [int(x) for x in bus_full.split(".")[1:] if x.isdigit()]
        terms.append((bus, conn, nodes))
        n = dss.Loads.Next()
    return terms


def phasors(bus):
    dss.Circuit.SetActiveBus(bus)
    va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
    nodes = list(dss.Bus.Nodes())
    return {nd: m * np.exp(1j * a) for m, a, nd in zip(mags, angs, nodes) if nd in (1, 2, 3)}


def term_voltages(bus, conn, nodes):
    """Connection-appropriate per-unit voltages at one load terminal."""
    P = phasors(bus)
    out = []
    if conn == "wye":
        ns = nodes if nodes else [k for k in P]
        for k in ns:
            if k in P:
                out.append((abs(P[k]), f"{bus}.{k}", "LN"))
    else:  # delta: phase-pair line-to-line
        if nodes and len(nodes) >= 2:
            pairs = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)] + [(nodes[-1], nodes[0])]
        else:
            pairs = [(1, 2), (2, 3), (3, 1)]
        for i, j in pairs:
            if i in P and j in P:
                out.append((abs(P[i] - P[j]) / np.sqrt(3), f"{bus}.{PAIR.get((i, j), f'{i}{j}')}", "LL"))
    return out


def main():
    terms = load_terminals()
    n_wye = sum(1 for _, c, _ in terms if c == "wye")
    n_delta = sum(1 for _, c, _ in terms if c == "delta")

    worst = None                       # (v, label, conn, hour)
    worst_wye = None
    worst_delta = None
    bus65_ln = None                    # auxiliary node diagnostic
    for h, lm in enumerate(DAILY):
        dss.Text.Command(f"compile [{MASTER}]")
        dss.Text.Command("set controlmode=static")
        dss.Text.Command(f"set loadmult={lm}")
        dss.Solution.Solve()
        for bus, conn, nodes in terms:
            for v, label, kind in term_voltages(bus, conn, nodes):
                if worst is None or v < worst[0]:
                    worst = (v, label, conn, h)
                if conn == "wye" and (worst_wye is None or v < worst_wye[0]):
                    worst_wye = (v, label, h)
                if conn == "delta" and (worst_delta is None or v < worst_delta[0]):
                    worst_delta = (v, label, h)
        # auxiliary: bus 65 line-to-neutral node minimum (diagnostic only)
        P = phasors("65")
        ln = min((abs(x) for x in P.values()), default=float("nan"))
        if bus65_ln is None or ln < bus65_ln[0]:
            bus65_ln = (ln, h)

    out = dict(
        n_load_terminals=len(terms), n_wye=n_wye, n_delta=n_delta,
        connsec_worst_min=round(worst[0], 4),
        connsec_binding=dict(terminal=worst[1], connection=worst[2], hour=worst[3]),
        worst_wye_LN=dict(v=round(worst_wye[0], 4), terminal=worst_wye[1], hour=worst_wye[2]),
        worst_delta_LL=dict(v=round(worst_delta[0], 4), terminal=worst_delta[1], hour=worst_delta[2]),
        aux_bus65_LN_node=dict(v=round(bus65_ln[0], 4), hour=bus65_ln[1]),
    )
    (ROOT / "reports" / "ieee123_connsec.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2), flush=True)


if __name__ == "__main__":
    main()
