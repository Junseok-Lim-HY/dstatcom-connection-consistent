# Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs in Unbalanced Delta Feeders

Reproducibility package for the IEEE Access manuscript
*"Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs in Unbalanced
Delta Feeders"* (J. Lim and S. Bae).

The source code, the OpenDSS feeder models, the input data, and representative output
files required to reproduce the reported results are provided here. An automated
consistency test cross-checks every headline number in the manuscript against the
stored report files.

## Layout

```
dstatcom-connection-consistent/
├── README.md
├── LICENSE                     # MIT
├── CITATION.cff
├── requirements.txt            # pinned Python dependencies (verified on Python 3.9)
├── environment.yml             # conda environment (installs requirements.txt)
├── scripts/                    # experiment, figure, and consistency scripts
├── data/raw/                   # IEEE 37- and 123-node OpenDSS feeder models
│   ├── ieee37_dss/
│   └── ieee123_dss/
├── reports/                    # canonical JSON/CSV outputs (single source of truth)
└── paper/ieee_access/          # manuscript sources (main.tex, supplementary.tex)
```

## Canonical result

* Design: three D-STATCOMs at buses **735, 740, 741**, total **1041.3 kvar**
  (393.6 / 249.2 / 398.5 kvar) — the lowest-capacity verified-feasible three-device
  support found by the single-evaluator two-stage enumeration over all
  C(10,3) = 120 three-device supports in the prescreened ten-bus pool.
* Peak line-to-line minimum raised from 0.899 pu to **0.9565 pu**
  (acceptance 0.9562 pu = 0.95 + margin 0.006 + tolerance 2e-4).
* Metric ablation (same 120-support enumeration under each metric): the
  line-to-ground metric selects {711,737,740} at 1287.4 kvar versus {735,740,741}
  at 1041.3 kvar under the connection-consistent line-to-line metric — a **23.6%**
  capacity increase.

## Environment

Verified on Python 3.9. Install the pinned dependencies with either:

```bash
pip install -r requirements.txt
# or:
conda env create -f environment.yml && conda activate dstatcom-connection-consistent
```

## Reproduce

Run from the repository root. The scripts resolve their data and report paths
relative to this directory, so they can be launched as `python scripts/<name>.py`.

```bash
python scripts/run_dstatcom_canonical.py             # canonical 120-support enumeration -> reports/dstatcom_canonical.json
python scripts/run_dstatcom_twostage_fullrecompile.py# LL/LG two-stage enumeration (full recompile per eval; long run)
python scripts/build_canonical_reports.py            # assemble adopted canonical/ablation reports (design table, LL/LG gap)
python scripts/run_dstatcom_certsweep.py             # minimum device-count search -> reports/dstatcom_certsweep.json
python scripts/run_dstatcom_operation.py             # 24-hour operating comparison -> operation summary + 24h CSV
python scripts/run_dstatcom_robust_thermal.py        # near-peak scalar-load sensitivity + head-line thermal screen
python scripts/run_dstatcom_proxysens.py             # local-proxy knee/damping sensitivity (27 settings)
python scripts/run_ieee123_connsec.py                # IEEE 123-node connection audit -> reports/ieee123_connsec.json
```

Note: `run_dstatcom_twostage_fullrecompile.py` recompiles the feeder from source at
every objective evaluation (order of 10^5–10^6 power-flow solves per metric) and is
the long-running step; the other scripts complete in seconds to a few minutes.

**Reproducibility of the support selection.** The per-support capacity is sized by
stochastic differential evolution, and — as stated in the article — the top
three-device supports are numerically near-equivalent (within about 2 kvar) and their
exact ranking is not numerically resolved. A fresh run under a different SciPy/NumPy
build may therefore select a near-equivalent support (e.g. {711, 735, 740} at
~1043 kvar instead of the reported {735, 740, 741} at 1041.3 kvar) and report the
line-to-ground/line-to-line capacity gap as ~23.5–23.6 %. The `reports/` files shipped
here are the specific canonical outputs behind the article, and the design-fixed
downstream results (24-hour operation, sensitivity, thermal screen, and the IEEE 123
audit) reproduce exactly. Run `scripts/check_consistency.py` against the shipped
`reports/` to verify the manuscript numbers.

Rebuild the figures:

```bash
python scripts/make_fig1_overall.py
python scripts/make_dstatcom_figures.py
```

## Consistency test

`scripts/check_consistency.py` cross-checks every headline number cited in the
manuscript (`paper/ieee_access/main.tex` and `supplementary.tex`) against the
canonical `reports/*.json` (design buses, total and per-bus kvar, operation
minima/losses, sequence VUF, NEMA LVUR, minimum-count sweep, the 23.6% enumeration
ablation, the IEEE 123 audit, robustness, and proxy settings) and exits non-zero on
any mismatch:

```bash
python scripts/check_consistency.py
```

## Data-availability manifest

| Analysis step | Report artifact(s) |
|---|---|
| LL/LG two-stage enumeration (single numerical source) | `reports/dstatcom_twostage_fullrecompile.json` |
| Canonical/ablation report assembly | `reports/dstatcom_canonical.json`, `reports/dstatcom_ablation_enum.json` |
| Minimum device-count search | `reports/dstatcom_certsweep.json` |
| 24-hour operating comparison | `reports/dstatcom_operation_summary.json`, `reports/dstatcom_operation_24h.csv` |
| Near-peak sensitivity and thermal screen | `reports/dstatcom_robust_thermal.json` |
| Proxy knee/damping sensitivity | `reports/dstatcom_proxysens.json` |
| IEEE 123 connection audit | `reports/ieee123_connsec.json`, `reports/ieee123_terminal_audit.csv`, `reports/ieee123_control_state.csv` |
| Automated consistency test | `scripts/check_consistency.py` (checks stored outputs only) |

The consistency test verifies cross-file numerical identities against the stored
outputs and is *not* a substitute for rerunning the optimization. Only transient
solver logs and large intermediate power-flow dumps are withheld and are not required
to reproduce any reported result.

## Feeder models

The IEEE 37- and 123-node OpenDSS models under `data/raw/` are the IEEE PES
distribution test feeders as distributed with OpenDSS.

## License and citation

Released under the MIT License (see `LICENSE`). If you use this package, please cite
the associated IEEE Access article; citation metadata is in `CITATION.cff`.
