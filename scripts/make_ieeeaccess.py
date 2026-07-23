"""Generate main_ieeeaccess.tex (official IEEE Access format) from main.tex.

main.tex is the IEEEtran version; this script transforms it into a file that
compiles against the OFFICIAL ieeeaccess.cls (dropped into paper/ieee_access/ from
the IEEE Access author kit). The transform:
  * \\documentclass{ieeeaccess};
  * IEEE Access title block -- \\history, \\doi, \\title, \\author with
    \\authorrefmark, \\address, \\tfootnote (funding), \\markboth, \\corresp,
    with a single \\maketitle issued AFTER the keywords (official ordering);
  * drops our manual hyperref (the cls loads it; double-load breaks bookmarks);
  * loads the caption package + IEEE Access \\captionsetup (the cls's own
    \\@makecaption references an undefined \\xfigwd with standard floats);
  * declares the `biography' counter and \\if@biographyTOCentrynotmade that the
    cls uses but never allocates (so the no-photo biographies compile);
  * replaces siunitx (which clashes with the cls's number/font handling) with
    lightweight text macros rendering numbers/units in text and math mode;
  * appends \\EOD before \\end{document}.
Verified to compile clean (0 errors, 0 undefined refs) with the official cls.
Run after editing main.tex to keep the two sources in sync.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "paper" / "ieee_access" / "main.tex"
DST = ROOT / "paper" / "ieee_access" / "main_ieeeaccess.tex"

s = SRC.read_text()

# ieeeaccess.cls loads hyperref itself (hidelinks, bookmarks=false); loading it
# again here with colorlinks re-enables bookmarks and breaks the biography-counter
# bookmark generation. Drop our manual hyperref line (no \href remains in main.tex).
s = s.replace(
    "\\usepackage[colorlinks=true,allcolors=blue]{hyperref}\n", "")

# The ieeeaccess.cls \@makecaption references \xfigwd, which is only set inside the
# cls's own float mechanism; with standard figure/table floats it is undefined and
# every caption errors (cascading into the biography environments). The official
# IEEE Access template avoids this by loading the caption package, which replaces
# \@makecaption. Inject the template's caption setup (matches manuscript_clean.tex).
CAPSETUP = r"""\usepackage{caption}
\definecolor{ieeecaptionblue}{RGB}{18,52,153}
\DeclareCaptionFont{ieeecapfont}{\fontsize{7}{8}\selectfont\sffamily\bfseries}
\DeclareCaptionFont{ieeecaplabelcolor}{\color{ieeecaptionblue}}
\captionsetup[figure]{font=ieeecapfont,labelfont=ieeecaplabelcolor,labelsep=period,justification=raggedright,singlelinecheck=false}
\captionsetup[table]{font=ieeecapfont,labelfont=ieeecaplabelcolor,labelsep=period,justification=raggedright,singlelinecheck=false}
% ieeeaccess.cls's biography environments reference a `biography' counter and a
% \if@biographyTOCentrynotmade conditional that the class never declares (IEEEtran
% uses different internal names). Declare both if missing so the no-photo
% biographies compile.
\makeatletter
\@ifundefined{c@biography}{\newcounter{biography}}{}
\expandafter\ifx\csname if@biographyTOCentrynotmade\endcsname\relax
  \newif\if@biographyTOCentrynotmade\@biographyTOCentrynotmadetrue\fi
\makeatother
"""
# siunitx clashes with ieeeaccess.cls number/font handling (every \num/\SI raises
# "Use of \??? doesn't match its definition"); the official IEEE Access template
# avoids siunitx entirely. Replace the package with lightweight text macros that
# render numbers/units as plain text in text AND math mode. First hand-convert the
# few cases the generic macros can't (digit lists, scientific notation).
for a, b in [
    (r"\SIlist{49.0;31.3;47.5}{A}", r"49.0, 31.3, and 47.5~A"),
    (r"\SIlist{50.7;32.3;49.1}{A}", r"50.7, 32.3, and 49.1~A"),
    (r"\SIlist{41.9;43.1;43.6}{\percent}", r"41.9\%, 43.1\%, and 43.6\%"),
    (r"\SI{2e-4}{pu}", r"\ensuremath{2\times10^{-4}}~pu"),
]:
    s = s.replace(a, b)

SIUNITX_REPL = r"""% --- siunitx-free number/unit macros (ieeeaccess.cls clashes with siunitx) ---
\providecommand{\percent}{\%}
\newcommand{\num}[1]{#1}
\newcommand{\SI}[2]{#1\,\ensuremath{\mathrm{#2}}}
\newcommand{\numrange}[2]{#1\mbox{--}#2}
\newcommand{\SIrange}[3]{#1\mbox{--}#2\,\ensuremath{\mathrm{#3}}}
\makeatletter
% \SIlist renders a semicolon-separated list of exactly three values as
% "a, b, and c <unit>", matching siunitx list-units=single output.
\def\kie@silistiii#1;#2;#3\@nil{#1, #2, and #3}
\newcommand{\SIlist}[2]{\kie@silistiii#1\@nil\,\ensuremath{\mathrm{#2}}}
\makeatother
"""
s = s.replace(
    "\\usepackage{siunitx}\n\\sisetup{detect-weight=true,detect-family=true,list-units=single,list-final-separator={, and }}\n",
    SIUNITX_REPL + "\n" + CAPSETUP)

s = s.replace(
r"""%% ============================================================================
%%  Connection-Consistent Support Selection, Sizing, and Hourly Reactive-Power
%%  Dispatch of D-STATCOMs in an Unbalanced IEEE 37-Node Distribution Feeder
%%
%%  IEEE Access submission version.
%%
%%  This file uses IEEEtran (journal mode), which is the class the official
%%  IEEE Access template (ieeeaccess.cls) is built on and which compiles in any
%%  standard TeX Live installation. To produce the exact IEEE Access page style
%%  for the camera-ready copy, drop the IEEE Access author-kit files
%%  (ieeeaccess.cls, etc.) into this folder and replace the \documentclass line
%%  with:  \documentclass{ieeeaccess}
%% ============================================================================
\documentclass[journal]{IEEEtran}""",
r"""%% ============================================================================
%%  OFFICIAL IEEE Access format (ieeeaccess.cls). Compile on Overleaf's official
%%  "IEEE Access LaTeX template" (ships ieeeaccess.cls + Formata/Giovanni fonts +
%%  header logos). Stock TeX Live lacks those commercial assets. A guaranteed-
%%  locally-compilable IEEEtran version is kept as main.tex.
%%  AUTO-GENERATED from main.tex by scripts/make_ieeeaccess.py -- do not edit here.
%% ============================================================================
\documentclass{ieeeaccess}""")

old = r"""\begin{document}

\title{Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs in
Unbalanced Delta Feeders}

\author{
\IEEEauthorblockN{Junseok Lim and Sungwoo Bae,~\IEEEmembership{Member,~IEEE}}
\thanks{Manuscript submitted July~2026. This work was supported by the Korea
Institute of Energy Technology Evaluation and Planning (KETEP) and the Ministry of
Climate, Energy \& Environment (MCEE) of the Republic of Korea (RS-2023-00234563,
Development of power system modeling \& analysis and interoperability evaluation
technology applied with grid forming based on distributed energy, and
RS-2024-00422103, EV Smart Charging Platform Innovation Research Center).
\emph{(Corresponding author: Sungwoo Bae.)}}
\thanks{The authors are with the Department of Electrical Engineering,
Hanyang University, Seoul 04763, South Korea
(e-mail: swbae@hanyang.ac.kr).}
\thanks{ORCID iDs: Junseok Lim, 0009-0004-8400-6561; Sungwoo Bae, 0000-0001-5252-1455.}
}

\markboth{IEEE Access}%
{Lim and Bae: Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs}

\maketitle"""
# In the official ieeeaccess.cls the title-page macros (\history, \doi, \title,
# \author with \authorrefmark, \address, \tfootnote, \markboth, \corresp) precede
# the abstract/keywords, and a SINGLE \maketitle is issued AFTER the keywords.
new = r"""\begin{document}

\history{}
\doi{}

\title{Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs in
Unbalanced Delta Feeders}

\author{\uppercase{Junseok Lim}\authorrefmark{1}, and
\uppercase{Sungwoo Bae}\authorrefmark{1}, \IEEEmembership{Member, IEEE}}
\address[1]{Department of Electrical Engineering, Hanyang University, Seoul 04763, South Korea (e-mail: swbae@hanyang.ac.kr)}
\tfootnote{This work was supported by the Korea Institute of Energy Technology Evaluation and Planning (KETEP) and the Ministry of Climate, Energy \& Environment (MCEE) of the Republic of Korea (RS-2023-00234563, Development of power system modeling \& analysis and interoperability evaluation technology applied with grid forming based on distributed energy, and RS-2024-00422103, EV Smart Charging Platform Innovation Research Center). ORCID iDs: Junseok Lim, 0009-0004-8400-6561; Sungwoo Bae, 0000-0001-5252-1455.}

\markboth{Lim and Bae: Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs}
{Lim and Bae: Connection-Consistent Planning and Volt/VAR Control of D-STATCOMs}

\corresp{Corresponding author: Sungwoo Bae (e-mail: swbae@hanyang.ac.kr).}"""
assert old in s, "title block mismatch -- update make_ieeeaccess.py"
s = s.replace(old, new)

# single \maketitle, issued after the keywords block (official ieeeaccess order)
s = s.replace(
r"\end{IEEEkeywords}",
"\\end{IEEEkeywords}\n\n\\titlepgskip=-15pt\n\\maketitle", 1)

# main.tex already carries the three IEEEbiographynophoto blocks; the official
# ieeeaccess.cls only needs the \EOD marker appended before \end{document}.
s = s.replace("\n\\end{document}", "\n\\EOD\n\n\\end{document}")

DST.write_text(s)
print("wrote", DST.name,
      "| documentclass ieeeaccess:", "\\documentclass{ieeeaccess}" in s,
      "| bios:", "\\begin{IEEEbiographynophoto}" in s)
