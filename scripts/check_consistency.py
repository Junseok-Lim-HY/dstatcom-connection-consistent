"""Automated manuscript/report consistency test (8th review, submission checklist).

Cross-checks the key numbers cited in main.tex against the canonical report JSON/CSV
files (single source), so a stale or mistyped value is caught before submission.
Exits non-zero if any check fails.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = (ROOT / "paper" / "ieee_access" / "main.tex").read_text()
SUPP = (ROOT / "paper" / "ieee_access" / "supplementary.tex").read_text()
REP = ROOT / "reports"


def J(name):
    return json.load(open(REP / name))


def has(s):
    return s in TEX


def approx_in(value, digits=4):
    return f"{value:.{digits}f}" in TEX or f"{value:.3f}" in TEX or f"{value:.2f}" in TEX


fails = []


def check(cond, msg):
    (print if cond else fails.append)(("OK  " if cond else "FAIL") + " " + msg)
    if cond:
        pass


op = J("dstatcom_operation_summary.json")
can = J("dstatcom_canonical.json")["canonical"]
cs = J("dstatcom_certsweep.json")
ab = J("dstatcom_ablation2.json")
abe = J("dstatcom_ablation_enum.json")
cn = J("ieee123_connsec.json")
rb = J("dstatcom_robust_thermal.json")
px = J("dstatcom_proxysens.json")

# --- canonical design ---
check(can["support"] == ["735", "740", "741"], f"canonical support {can['support']}")
check(has("735, 740, 741") or has("735, 740, and 741"), "design buses in text")
check(has(f"{can['total_kvar']:.1f}"), f"total kvar {can['total_kvar']}")
check(all(has(f"{q}") for q in can["q_kvar"]), "per-bus kvar in Table V")
# --- operation numbers ---
check(has(f"{op['fixed']['worst_min']:.4f}"), f"fixed min {op['fixed']['worst_min']}")
check(has(f"{op['cap']['worst_min']:.4f}"), f"cap min {op['cap']['worst_min']}")
check(has(f"{op['coord']['worst_min']:.4f}"), f"coord min {op['coord']['worst_min']}")
check(has(f"{op['fixed']['max_v']:.3f}"), f"fixed max {op['fixed']['max_v']}")
check(has(f"{op['base']['Ev']:.3f}") or has(f"{op['base']['Ev']:.2f}"), f"base Ev {op['base']['Ev']}")
# loss reductions
f, dr, co = op["fixed"]["energy_loss_kwh"], op["droop"]["energy_loss_kwh"], op["coord"]["energy_loss_kwh"]
dl, cl = round(100 * (f - dr) / f, 1), round(100 * (f - co) / f, 1)
check(has(f"{dl:.1f}") and has(f"{cl:.1f}"), f"loss reductions {dl}%/{cl}%")
cap_share = round(100 * (f - dr) / (f - co))
check(has(str(cap_share)), f"proxy capture ~{cap_share}%")
# VUF
for k in ("base", "fixed", "cap", "coord"):
    check(has(f"{op[k]['max_vuf_pct']:.2f}"), f"VUF {k} {op[k]['max_vuf_pct']}")
# --- min-count ---
check(has(f"{cs['one_device']['max_v_best']:.4f}"), f"1-dev vbest {cs['one_device']['max_v_best']}")
check(has(f"{cs['two_device']['max_v_best']:.4f}"), f"2-dev vbest {cs['two_device']['max_v_best']}")
check(cs["min_count_verified_3"], "min-count 3 verified in report")
check(not has("global minimum capacity is\ntherefore attained") and "attains the global\nminimum" not in TEX,
      "no global-minimum claim")
check(TEX.count("global minimum") <= 4, f"global-minimum mentions bounded ({TEX.count('global minimum')})")
# --- ablation via full enumeration (10th review P0-3) ---
check(has(f"{abe['relative_increase_pct']:.1f}"), f"enum ablation increase {abe['relative_increase_pct']}%")
check(has(f"{abe['lg_design']['total_kvar']:.1f}"), f"LG enum kvar {abe['lg_design']['total_kvar']}")
check(has(f"{abe['ll_design']['total_kvar']:.1f}"), f"LL enum kvar {abe['ll_design']['total_kvar']}")
check(abe['ll_design']['support'] == can['support'], "LL enumeration selects the canonical design")
check(has(f"{abe['base_worst']['line_to_ground']:.3f}"), f"LG base {abe['base_worst']['line_to_ground']}")
check(abe['ll_design_cross']['ll_min'] >= 0.956, f"enum LL design clears 0.9562 (LL min {abe['ll_design_cross']['ll_min']})")
# --- method framing (9th/10th review P0-1) ---
check("greedy support selection" not in TEX, "no residual 'greedy support selection' as primary method")
check(has("full enumeration") or has("enumerating all 120"), "enumeration named as primary method")
# --- 10th review: residual over-claim strings absent (report section 9 checklist) ---
contrib = re.search(r"\\subsection\{Contributions\}(.*?)\\end\{enumerate\}", TEX, re.S)
check(contrib is not None and "greedy forward selection" not in contrib.group(1),
      "no 'greedy forward selection' as primary method in Contributions")
check("minimum-capacity} design" not in TEX and "\\emph{minimum-capacity} design" not in TEX,
      "no 'minimum-capacity design' claim")
check("service limit" not in TEX, "no 'service limit' phrasing (use study-band lower limit)")
check("by either definition" not in TEX, "no 'by either definition' VUF/NEMA claim")
check(not any(p in TEX for p in ("[DOI]", "[TAG]", "[HASH]", "zenodo.0000000")),
      "no DOI/TAG/HASH placeholders")
check(has("publicly available") and has("GitHub"), "Data Availability states public GitHub availability")
check(has("NEMA LVUR") and has("LVUR(t)") or has("\\mathrm{LVUR}"), "NEMA LVUR computed and reported")
check(has("study-band lower limit"), "study-band lower limit phrasing present")
check("infeasible for the planning problem" in SUPP or "infeasible for planning" in SUPP,
      "optimizer feasibility caveat present (supplement S-I)")
check("eq:objective" not in TEX and "five-optimizer sensitivity study" not in TEX,
      "composite objective + optimizer study moved out of main body")
# --- 11th review ---
check("tab:gap" not in TEX and "Feature Comparison" not in TEX,
      "feature-comparison Table I removed (prose comparison)")
check(has("\\hat v_{\\mathrm{best}}") or has("largest value found"),
      "v_best reported as largest value found (not global)")
check(has("near-equivalent") and has("not numerically resolved"),
      "top-support ranking softened (P0-5)")
check(has("near-peak"), "lambda=1.28 relabelled as near-peak sensitivity (P0-7)")
check(has(str(abe["n_feasible_lg"])) and has(str(abe["n_feasible_ll"])),
      f"ablation feasible counts {abe['n_feasible_lg']}/{abe['n_feasible_ll']} in Table VIII")
check(has("no-action transfer case"), "IEEE 123 no-action transfer framing (P1-6)")
check(not has("not a meaningful security"), "line-to-ground 'meaningless' claim removed (P0-2)")
# --- 12th review ---
check("stated enumeration budget" in TEX, "canonical scoped to stated enumeration budget (P0-1)")
# --- 16th review P0-1/P0-2/P0-3/P0-9 ---
check(has("full feeder recompilation at every") or has("full feeder recompilation at each"),
      "single full-recompile evaluator stated (16th P0-1)")
check(has("operating currents") and has("nameplate-rating"),
      "current benchmark reframed as operating-only (16th P0-2)")
check(has("\\Phi_A(\\mathbf Q") and has("label{eq:stageA}") and has("label{eq:stageB}"),
      "two-stage Stage A/B equations given (16th P0-3)")
check(has("\\SI{5}{\\percent} standard deviation"),
      "robustness stated as 5% standard deviation (16th P1-9)")
# --- 17th review consistency fixes ---
check(not has("\\SI{0.5}{\\kvar}, at most"),
      "stale proxy 0.5 kvar/40 iterations removed (17th P0-1)")
check(has("varepsilon_Q=\\SI{0.05}{\\kvar}$, up to") or has("converged within 40 sweeps"),
      "proxy tolerance unified to 0.05 kvar/400 sweeps in IV-J (17th P0-1)")
check(has("\\sum_{i\\in\\mathcal S}\\Qmax_i"),
      "Stage B sizing uses installed rating Q^max over support S (17th P0-2)")
check(has("numerically approximated") and has("\\rho_V=10^{5}"),
      "penalty coefficient/buffer defined for two-stage (17th P0-3)")
check(has("idealized device-model") and has("equal nominal"),
      "capacitor comparison reframed to equal nominal kvar / idealized (17th P0-4)")
check(not has("not achieved under budget"),
      "Fig. 1 caption stale legend text removed (17th P0-5)")
check(has("recompilation and connection-voltage"),
      "one-/two-device search uses same evaluator (17th P1-3)")
check("statistically stable" not in TEX and "statistically separated" not in TEX,
      "no unsupported 'statistically' claim (P0-2)")
check(has("numerically resolved"), "ranking described as numerically resolved (P0-2)")
check(has("Evaluation and Planning (KETEP)") and has("(MCEE)"),
      "funding statement present (verbatim per author)")
check(has("V_{LN,i}") and has("mathcal M_Y") or has("mathcal M_\\Delta"),
      "wye line-to-neutral metric added (P0-4)")
check(has("grid-and-local-search protocol") and "no feasible support with fewer than three" not in TEX,
      "conclusion min-count softened to protocol (P0-7)")
check(has("substitute for rerunning the optimization"),
      "data-availability consistency-test vs rerun separation (P0-8)")
check(has("U_{\\mathrm{avg}}"), "LVUR magnitude notation (P1-1)")
# --- 13th review ---
check("unnecessarily large" not in TEX, "ablation 'unnecessarily large' softened (P1-3)")
check("wasted margin" not in TEX, "ablation 'wasted margin' softened (P1-3)")
check(has("Supplementary Section~S-I") or has("Supplementary Section"),
      "optimizer study moved to supplement (P1-1)")
check("tab:optcompare" not in TEX and "tab:benchmarks" not in TEX,
      "optimizer tables no longer in main body (P1-1)")
check(has("within about\n\\SI{2}{\\kvar}") or has("about \\SI{2}{\\kvar}") or has("2}{\\kvar}"),
      "near-equivalent top supports within ~2 kvar reported")
check(has("reserve-preserving"), "reserve-preserving coordinated reference (18th P0-4)")
check(has("smallest feasible count found under that protocol") or
      has("smallest feasible count found under the stated"),
      "min-count phrased as protocol-limited (P0-3)")
# --- 14th/15th review: two-stage is the primary design source (Version B) ---
check(has("two-stage procedure") and (has("feasible point") or has("feasible-point")),
      "two-stage procedure is the design-sizing method (Version B)")
check(has("production setting $\\varepsilon_Q=\\SI{0.05}") or has("\\varepsilon_Q=\\SI{0.05}{\\kvar}$ with up to 400"),
      "production eps_Q=0.05/400 stated explicitly (16th P0-6)")
check(has("initialization-independent"), "proxy initialization-independence reported (16th P0-6)")
check("An exploratory optimizer comparison" not in TEX and
      "\\item \\textbf{An exploratory optimizer comparison}" not in TEX,
      "optimizer Contribution removed (P0-2)")
check(has("three gaps") and "four gaps" not in TEX, "research gap (iv) removed (P0-2)")
check(has("Canonical planning set $\\Lambda_{\\mathrm{plan}}$") or has("Canonical planning set"),
      "Table 1 canonical/auxiliary load sets split (P0-5)")
check(has("Representative D-STATCOM Design") or has("Found Under the Stated Enumeration Budget"),
      "design table title budget-specific (P0-4)")
check(has("$10^5$--$10^6$") or has("10^5$--$10^6$"), "canonical enumeration cost reported (P0-3)")
check(has("$\\beta$-invariant") or has("beta-invariant") or has("0.1}{\\percent}$ of the daily total"),
      "beta-invariance quantified (P0-6)")
check("forecast-fixed schedule" not in TEX, "undefined forecast-fixed schedule removed (P1-5)")
# --- 123 ---
check(has(f"{cn['connsec_worst_min']:.4f}"), f"123 connsec min {cn['connsec_worst_min']}")
check(has("bus~63") or has("bus 63"), "123 binding bus 63")
# --- robustness ---
fr = int(round(100 * rb["robustness"]["droop"]["frac_violating"]))
check(has(f"\\SI{{{fr}}}"), f"robust {fr}% of realizations")
# --- proxy sensitivity ---
check(px["n_settings"] == 27 and has("\\num{27}"), f"proxy 27 settings (report {px['n_settings']})")
# --- abstract word count ---
abm = re.search(r"\\begin{abstract}(.*?)\\end{abstract}", TEX, re.S).group(1)
t = re.sub(r"\\SIrange\{([^}]*)\}\{([^}]*)\}\{[^}]*\}", r"\1 \2", abm)
t = re.sub(r"\\SI\{([^}]*)\}\{[^}]*\}", r"\1", t)
t = re.sub(r"\\num\{([^}]*)\}", r"\1", t)
t = re.sub(r"\\[a-zA-Z]+", " ", t); t = re.sub(r"[{}\\~%]", " ", t)
wc = len([w for w in t.split() if any(c.isalnum() for c in w)])
check(wc <= 250, f"abstract <=250 words (got ~{wc})")

# --- 19th review: two coordinated references, traceable and labeled ---
check(has("sec:coordrefs") or has("Two coordinated references"),
      "coordinated-references subsection labeled (19th P0-3)")
check(has("Coordinated (band-only)"), "band-only coordinated row/label present (19th P0-4)")
check(has("Coordinated (reserve-pres") or has("reserve-preserving coordinated"),
      "reserve-preserving coordinated row/label present (19th P0-4)")
# reserve-band feasibility: reserve-preserving reference holds the acceptance band
check(op["coordrp"]["Ev"] == 0.0, f"reserve-preserving Ev==0 (got {op['coordrp']['Ev']})")
check(abs(op["coordrp"]["worst_min"] - 0.9562) < 5e-4,
      f"reserve-preserving worst min ~0.9562 (got {op['coordrp']['worst_min']})")
check(has(f"{op['coordrp']['worst_min']:.4f}"),
      f"reserve-preserving min {op['coordrp']['worst_min']} in text")
# six-strategy table entries (v_min / v_max / loss / head-line loading)
for k in ("fixed", "cap", "droop", "coord", "coordrp"):
    row = op[k]
    check(has(f"{row['worst_min']:.4f}"), f"{k} worst_min {row['worst_min']} in text")
    if "max_line_loading_pct" in row:
        check(approx_in(row["max_line_loading_pct"], 1) or has(f"{round(row['max_line_loading_pct'])}"),
              f"{k} head-line loading {row['max_line_loading_pct']}% in text")
# capture ratio computed against the reserve-preserving (constraint-matched) reference
cap_rp = op.get("proxy_capture_vs_reserve_preserving_pct")
check(cap_rp is not None and has(f"\\SI{{{cap_rp}"),
      f"reserve-preserving capture ratio ~{cap_rp}% in text")
# unrounded coordinated losses agree within 0.01 kWh (band-only vs reserve-preserving)
check(has("2843.47") and has("2843.48"),
      "unrounded coordinated losses (band-only/reserve-preserving) cited (19th P0-2)")
# --- 19th review: Main Table III currents match Supplement S-III ---
SUPP = (ROOT / "paper" / "ieee_access" / "supplementary.tex")
if SUPP.exists():
    supp = SUPP.read_text()
    op_curr = can["dev_current_a"]
    bn_curr = can["dev_benchmark_a"]
    for v in op_curr + bn_curr:
        check(f"{v}" in TEX, f"current {v} A in main")
    # supplement must cite the same max operating/benchmark currents (not the stale 48.7/57.0)
    check(f"{max(op_curr)}" in supp and f"{max(bn_curr)}" in supp,
          f"supplement S-III max currents {max(op_curr)}/{max(bn_curr)} A match main")
    check("48.7" not in supp and "57.0" not in supp,
          "supplement S-III stale currents (48.7/57.0 A) removed (19th P0-1)")
    supp_nb = supp.replace("\\_", "_")
    check("rebuild_16th" not in supp_nb,
          "no stale manifest name (rebuild_16th) in supplement (19th P0-6)")

print(f"\n{'PASS' if not fails else 'FAIL'}: {len(fails)} failing checks")
for m in fails:
    print(m)
sys.exit(1 if fails else 0)
