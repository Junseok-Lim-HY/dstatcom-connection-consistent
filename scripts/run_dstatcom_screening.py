"""Candidate-bus screening report for the ten-bus pool (single source for Fig 2).

Computes the worst-case line-to-line minimum over the screening load set for each
of the ten candidate-pool buses and writes reports/dstatcom_screening.csv, so the
figure and the paper draw the candidate list from one canonical CSV.
"""
from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
import opendssdirect as dss

ROOT = Path(__file__).resolve().parents[1]
MASTER = (ROOT / "data" / "raw" / "ieee37_dss" / "Master.DSS").resolve()
POOL = ["740", "741", "711", "738", "735", "737", "736", "710", "734", "733"]
LAMBDA = (0.80, 1.00, 1.17, 1.34)


def bus_min_ll(bus):
    dss.Circuit.SetActiveBus(bus)
    va = np.array(dss.Bus.puVmagAngle()); mags = va[0::2]; angs = va[1::2] * np.pi / 180.0
    nodes = list(dss.Bus.Nodes())
    P = {n: m * np.exp(1j * a) for m, a, n in zip(mags, angs, nodes) if n in (1, 2, 3)}
    vs = [abs(P[i] - P[j]) / np.sqrt(3) for i, j in ((1, 2), (2, 3), (3, 1)) if i in P and j in P]
    return min(vs) if vs else 1.0


def main():
    worst = {b: 1.0 for b in POOL}
    for lm in LAMBDA:
        dss.Text.Command(f"compile [{MASTER}]")
        dss.Text.Command(f"set loadmult={lm}")
        dss.Solution.Solve()
        for b in POOL:
            worst[b] = min(worst[b], bus_min_ll(b))
    rows = [dict(bus=b, worst_min=round(worst[b], 4)) for b in POOL]  # keep pool order
    with (ROOT / "reports" / "dstatcom_screening.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["bus", "worst_min"]); w.writeheader(); w.writerows(rows)
    for r in rows:
        print(r["bus"], r["worst_min"])


if __name__ == "__main__":
    main()
