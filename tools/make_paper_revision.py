"""Create a revised copy of the manuscript, leaving the original untouched.

Every insertion is wrapped in \\hl{}. Section titles are left unhighlighted
because soul's \\hl is unreliable inside headings in the MDPI class; the
surrounding body text is highlighted instead, which makes the additions
equally obvious without risking the build.
"""
import pathlib, shutil, sys

SRC = pathlib.Path(r"C:/Users/User/Documents/GitHub/Agriculture-4351955/agriculture-4351955.tex")
DST = SRC.with_name("agriculture-4351955-revised.tex")

s = SRC.read_text(encoding="utf-8")
orig_len = len(s)


def replace_once(old, new, what):
    global s
    if old not in s:
        print(f"  !! anchor NOT FOUND: {what}")
        print(f"     {old[:90]!r}")
        sys.exit(1)
    if s.count(old) != 1:
        print(f"  !! anchor appears {s.count(old)} times: {what}")
        sys.exit(1)
    s = s.replace(old, new, 1)
    print(f"  ok  {what}")


# ---------------------------------------------------------------------------
# 1. Update the forward-looking sentence about A and B in Section 4.1
# ---------------------------------------------------------------------------
OLD_PROMISE = (r"\hl{It is important to mention that Laboratory tests for N,P,K properties and "
               r"independent tests for features like temperature and moisture are the main topic "
               r"in the next step of this proposal for a proper calibration, where 2 different "
               r"data point are necessary to recalculate the A and B values by establishing a "
               r"simple system of equations with the laboratory results and the sensor readings "
               r"as the input.}")

NEW_PROMISE = r"""\hl{Laboratory reference values for N, P and K, together with independent references for
temperature and moisture, are required before these factors can be assigned. Two distinct
reference points are sufficient to solve for }$A$\hl{ and }$B$\hl{ in each channel by forming a
simple system of equations from the laboratory results and the corresponding sensor readings.
Before doing so, however, it is worth establishing that each channel carries information of its
own, since a correction factor applied to a channel that is not independent will fit its
reference points without conferring any measurement capability. That question is addressed in
Section}~\ref{sec:charact}\hl{.}"""

replace_once(OLD_PROMISE, NEW_PROMISE, "A/B forward-looking sentence")


# ---------------------------------------------------------------------------
# 2. New methodology subsection, before "Installation and commissioning"
# ---------------------------------------------------------------------------
METHOD = r"""\subsection{Characterisation of the nutrient channels}
\label{sec:charact}

\hl{Before correction factors are assigned, the behaviour of the three nutrient outputs was
examined directly. Two independent sources of evidence were combined.}

\hl{The first is the continuous record produced by the prototype itself. Every payload published
by the module is written to a local database by the Node-RED flow, so the seven-day test reported
in Section}~\ref{sec:results}\hl{ yields a dense log of simultaneous moisture, temperature, pH and
nutrient values. For the analysis reported here the record was restricted to readings taken with
the electrodes in soil, operationally defined as a moisture value between 15 and 60~\%RH, which
excludes the intervals when the probe was in air or in standing water. This leaves }$n=53\,735$
\hl{ readings collected between 1 and 7 September 2026.}

\hl{The second is an independent laboratory database for the SZ-24 field, comprising twelve
georeferenced soil samples analysed for nitrate-nitrogen, }$P_2O_5$\hl{, }$K_2O$\hl{, pH, humus,
carbonate content and further properties. These provide reference values whose between-sample
variation is established independently of the instrument under test.}

\hl{Three questions were posed. First, whether the three nutrient outputs vary independently of
one another. Second, whether a reported value of zero represents a measurement or the lower limit
of the output range. Third, how much of the reported value is attributable to soil water rather
than to nutrient content. Ordinary least squares was used throughout, and all statistics quoted
below are produced by a single script archived alongside the firmware, so that every figure in the
text can be traced back to the raw record.}

"""

ANCHOR_INSTALL = "\\subsection{Installation and commissioning}"
replace_once(ANCHOR_INSTALL, METHOD + ANCHOR_INSTALL, "methodology subsection")


# ---------------------------------------------------------------------------
# 3. New results subsection, at the end of Results
# ---------------------------------------------------------------------------
RESULTS = r"""\subsection{Behaviour of the nutrient channels}
\label{sec:charactres}

\hl{The three nutrient outputs are not independent. Across the }$53\,735$\hl{ in-soil readings,
the phosphorus and potassium values are reproduced from the nitrogen value by fixed linear
relations, as summarised in Table}~\ref{tab:collinearity}\hl{. The largest departure from a
straight line is 1.7~mg/kg over output ranges of 48--262 and 40--256~mg/kg respectively, which is
comparable to the 1~mg/kg resolution of the underlying registers. Fitting each day separately
returns the same coefficients to within approximately 0.5~\%, although all readings originate from
the same instrument and the same experimental arrangement, so this consistency should be read as
evidence of an internal relation rather than as independent replication.}

\begin{table}[H]
\caption{\hl{Relations between the three nutrient outputs, }$n=53{,}735$\hl{ in-soil readings.}\label{tab:collinearity}}
\centering
\begin{tabular}{lccc}
\toprule
\textbf{Relation} & \textbf{$r$} & \textbf{Max. residual [mg/kg]} & \textbf{SD [mg/kg]}\\
\midrule
$P = 2.3086\,N + 46.741$ & $+0.99991$ & $1.67$ & $0.73$\\
$K = 2.3269\,N + 39.037$ & $+0.99991$ & $1.69$ & $0.74$\\
$K = 1.0079\,P - 8.071$ & $+0.99997$ & $0.96$ & $0.42$\\
\bottomrule
\end{tabular}
\end{table}

\hl{A reported nitrogen of zero is a limit of the output range rather than a measurement. The
relation in Table}~\ref{tab:collinearity}\hl{ reaches }$N=0$\hl{ at }$P=46.7$~\hl{mg/kg.}
\hl{Among the }$5\,484$\hl{ in-soil readings for which nitrogen was reported as exactly zero,
the phosphorus value never exceeded that threshold, with no exceptions. The nitrogen channel therefore
saturates at the bottom of its range before the other two, because it carries the smallest offset.
This supersedes the interpretation offered earlier in this manuscript, where a reported zero was
attributed to depletion of nitrates or to insufficient resolution; neither explanation is required,
and the observation is more simply accounted for as the output reaching its lower bound.}

\hl{The readings respond appreciably to soil water. Within a single uninterrupted session
in one pot, where the nutrient content is fixed by construction, moisture rose from 21.7 to
52.1~\%RH following irrigation and the reported nitrogen rose from 26 to 71~mg/kg over the same
interval }($n=2{,}836$, $r=+0.643$, $r^{2}=0.414$)\hl{. A linear fit gives 1.36~mg/kg of apparent
nitrogen per 1~\%RH, with a residual standard deviation of 3.30~mg/kg. Since laboratory values are
reported on a dry-mass basis and are unaffected by irrigation, this variation cannot represent
nutrient content. Water accounts for roughly two-fifths of the variance in this session; the
remainder is not explained by moisture alone, and at matched moisture the readings still differ
between sessions, which indicates that the instrument responds to soil properties beyond water
content.}

\hl{In the reference data, the three nutrients vary independently. Table}
~\ref{tab:labcorr}\hl{ reports the laboratory values for the twelve SZ-24 samples. None of the
three pairwise correlations reaches significance at }$p=0.05$\hl{, for which the critical value at
}$n=12$\hl{ is }$0.576$\hl{. With twelve samples this is not strong evidence that the nutrients are
unrelated in general, and a larger set could resolve modest associations; what it does establish is
that within this field their variation is not so tightly coupled as to be captured by a single
quantity.}

\begin{table}[H]
\caption{\hl{Laboratory values and pairwise correlations, field SZ-24, }$n=12$\hl{ samples.}\label{tab:labcorr}}
\centering
\begin{tabular}{lccc}
\toprule
\textbf{Analyte} & \textbf{Range [mg/kg]} & \textbf{Mean [mg/kg]} & \textbf{CV [\%]}\\
\midrule
$NO_2/NO_3$-$N$ & $12.4-42.8$ & $22.3$ & $34.0$\\
$P_2O_5$ & $119-271$ & $180.0$ & $23.1$\\
$K_2O$ & $171-277$ & $229.3$ & $14.6$\\
\midrule
\multicolumn{4}{l}{\textbf{Pairwise correlation}}\\
\midrule
$r(N,\,P_2O_5)$ & \multicolumn{3}{c}{$+0.433$}\\
$r(N,\,K_2O)$ & \multicolumn{3}{c}{$+0.156$}\\
$r(P_2O_5,\,K_2O)$ & \multicolumn{3}{c}{$+0.382$}\\
\bottomrule
\end{tabular}
\end{table}

\hl{Taken together, these observations indicate that the module reports one measured quantity
through three outputs related by fixed constants, and that the quantity in question is
substantially influenced by soil water. A principal component analysis of the standardised
laboratory values places 55.3~\% of the between-sample variation on the first component, with 28.2
and 16.5~\% on the second and third. An instrument whose outputs are collinear spans at most the
first component, so on this dataset a little under half of the observed variation lies in
directions such an instrument cannot express, irrespective of the correction factors chosen. This
bears on the interpretation of }$A$\hl{ and }$B$\hl{: fitting them separately for each channel
remains arithmetically possible and will reproduce the reference values at the calibration points,
but the three corrected outputs stay collinear, so agreement at other points depends on the
nutrient ratios of the calibration soils continuing to hold elsewhere.}

\hl{Two limitations should be stated plainly. All logged readings come from one unit in one
experimental arrangement, so nothing here establishes how the device behaves across production
units, and the internal relations reported may not be identical in other examples. Second, the
underlying transducer was not identified: the conductivity register of this variant returns zero
and no register was found that exposes a value prior to the internal conversion, so the nature of
the primary measurement is inferred from its behaviour rather than observed. The manufacturer's
documentation describes the nutrient determination as a rapid indirect method carrying appreciable
error, and provides writable registers through which externally measured values may be stored in
the device, which is consistent with what is reported here.}

"""

ANCHOR_DISC = "\\section{Authors Discussion}"
replace_once(ANCHOR_DISC, RESULTS + ANCHOR_DISC, "results subsection")



CALIBRATION = r"""\subsection{Two-soil calibration attempt}
\label{sec:calattempt}

\hl{Correction factors were then sought using two soils from the SZ-24 field for which laboratory
analyses were available: sample 59882, designated the richer of the two, and sample 59888. The
probe was removed, rinsed and reinserted for every reading, so that each value represents an
independent placement rather than a repeated sample of a settled probe. Twenty insertions were
made in each soil. One potassium value was recorded as 9189 beside a phosphorus value of 196;
the internal relation established in Section}~\ref{sec:charactres}\hl{ predicts 189.5 for that
reading, so it was treated as a leading-digit transcription slip and corrected to 189 rather than
discarded. Repeating the analysis with that reading removed instead changes the fitted gains by
under two percent and alters none of the conclusions. Sensor and laboratory values are summarised
in Table}
~\ref{tab:calinputs}\hl{. Sensor phosphorus and potassium are compared with the laboratory }
$P_2O_5$\hl{ and }$K_2O$\hl{, following the convention already used in Tables}
~\ref{tab: SoilChar}\hl{ and}~\ref{tab: NPKlecture}\hl{.}

\begin{table}[H]
\caption{\hl{Sensor readings and laboratory reference values for the two calibration soils. Sensor
values are means over independent insertions, with the standard deviation between
insertions.}\label{tab:calinputs}}
\centering
\begin{tabular}{lcccc}
\toprule
\textbf{Quantity} & \textbf{Sample 59882} & \textbf{Sample 59888} & \textbf{Units} & \textbf{Source}\\
\midrule
Insertions & $20$ & $20$ & -- & sensor\\
$N$ & $38.75 \pm 9.32$ & $73.30 \pm 11.74$ & mg/kg & sensor\\
$P$ & $136.35 \pm 21.42$ & $216.05 \pm 27.21$ & mg/kg & sensor\\
$K$ & $129.25 \pm 21.72$ & $209.75 \pm 27.33$ & mg/kg & sensor\\
Moisture & $28.6 \pm 6.3$ & $43.0 \pm 1.7$ & \%RH & sensor\\
\midrule
$NO_2/NO_3$-$N$ & $19.1$ & $20.7$ & mg/kg & laboratory\\
$P_2O_5$ & $188.0$ & $119.0$ & mg/kg & laboratory\\
$K_2O$ & $269.0$ & $202.0$ & mg/kg & laboratory\\
\bottomrule
\end{tabular}
\end{table}

\hl{The calibration could not be completed in a form we are willing to report as valid, for three
reasons that are visible in Table}~\ref{tab:calinputs}\hl{ before any coefficient is computed.}

\hl{First, the instrument and the laboratory rank the two soils in opposite order for phosphorus
and potassium. The laboratory reports sample 59882 as the richer in both, whereas the sensor
reports the reverse in both. Solving for the correction factors under these conditions returns
negative gains, as listed in Table}~\ref{tab:calresult}\hl{. A negative gain reproduces the two
reference points exactly, as any two-point fit must, while asserting that the measured quantity
decreases as the true concentration increases. We do not regard this as a calibration.}

\hl{Second, the two soils are almost identical in nitrate-nitrogen, differing by 1.6~mg/kg. The
corresponding sensor readings differ by 34.5~mg/kg. The fitted gain of 0.046 therefore compresses
the entire sensor range into a span narrower than the laboratory repeatability, which is a
consequence of the reference pair rather than a property of the instrument: two soils of nearly
equal nitrogen content cannot define a nitrogen scale.}

\hl{Third, the two sets of readings were taken at different water contents, 28.6 and 43.0~\%RH
respectively. Applying the moisture sensitivity measured in Section}~\ref{sec:charactres}\hl{,
1.36~mg/kg of apparent nitrogen per 1~\%RH, that difference alone accounts for 19.6~mg/kg of the
34.5~mg/kg separation between the two soils, or approximately 57~\%. Any coefficients fitted to
these data would encode that difference in water as though it were a difference in nutrient
content.}

\begin{table}[H]
\caption{\hl{Correction factors obtained from the two-soil fit, reported for completeness. The
negative gains for }$P$\hl{ and }$K$\hl{ indicate that the fit is not
usable.}\label{tab:calresult}}
\centering
\begin{tabular}{lccc}
\toprule
\textbf{Channel} & \textbf{$A$} & \textbf{$B$} & \textbf{Direction vs. laboratory}\\
\midrule
$N$ & $+0.0463$ & $+17.31$ & same\\
$P$ & $-0.8658$ & $+306.04$ & opposite\\
$K$ & $-0.8323$ & $+376.57$ & opposite\\
\bottomrule
\end{tabular}
\end{table}

\hl{We note that the direction disagreement is not removed by exchanging the two sample
designations. Under the alternative assignment the phosphorus and potassium channels agree in
direction while the nitrogen channel does not, so at least one channel is inconsistent with the
laboratory under either mapping. This makes the finding robust to a labelling error, though we
have verified the assignment against the sampling record.}

\hl{Accordingly, no correction factors are applied to the nutrient channels in this work. The
moisture and temperature channels, which showed values consistent with independent references
during the seven-day test, are unaffected by this and remain usable. We report the attempt rather
than omitting it, since the reasons it failed are informative about what a two-point calibration
of this device can and cannot establish, and since a successful-looking fit obtained from soils
measured at different water contents would have been misleading.}

"""

ANCHOR_DISC2 = "\\section{Authors Discussion}"
replace_once(ANCHOR_DISC2, CALIBRATION + ANCHOR_DISC2, "calibration attempt subsection")


# ---------------------------------------------------------------------------
# 4. Correct the nitrogen-zero claim in Authors Discussion
# ---------------------------------------------------------------------------
OLD_N = (r"while the $N$ lecture is $0$ possible due to the rapid decrease of nitrates in the "
         r"soil over time or the sensor resolution cannot capture such small values. Further "
         r"analysis, in which supplements are added to the soil for each variable, is part of "
         r"the next step in this development.")

NEW_N = (r"while the $N$ lecture is $0$. \hl{This was initially attributed to depletion of "
         r"nitrates in the soil or to insufficient resolution at low concentrations. The "
         r"characterisation reported in Section}~\ref{sec:charactres}\hl{ indicates a simpler "
         r"explanation: the nitrogen output reaches the bottom of its range while the other two "
         r"channels still have headroom, so a reported zero marks the limit of the output rather "
         r"than the absence of nitrogen. The corresponding entry in Table}~\ref{tab:errTable}"
         r"\hl{, which treats the zero as a 100~\% deviation from the labelled minimum, should "
         r"therefore be read as a bound rather than as a measured error.} Further analysis, in "
         r"which supplements are added to the soil for each variable, is part of the next step "
         r"in this development.")

replace_once(OLD_N, NEW_N, "nitrogen-zero claim in Discussion")


# ---------------------------------------------------------------------------
# 5. Correct the conclusions
# ---------------------------------------------------------------------------
OLD_CONC = (r"These results, together with the observed transient peaks after irrigation events "
            r"and stabilization after approximately two days, indicate that the system is highly "
            r"sensitive to soil water conditions and motivates a controlled calibration/"
            r"validation campaign.")

NEW_CONC = (r"These results, together with the observed transient peaks after irrigation events "
            r"and stabilization after approximately two days, indicate that the system is highly "
            r"sensitive to soil water conditions and motivates a controlled calibration/"
            r"validation campaign. \hl{The characterisation described in Section}"
            r"~\ref{sec:charactres}\hl{ qualifies these figures in two respects. The nitrogen "
            r"entry reflects the lower bound of the output range rather than a measured "
            r"concentration, and the three nutrient outputs were found to be related by fixed "
            r"linear constants, so they do not constitute three independent determinations. The "
            r"deviations in Table}~\ref{tab:errTable}\hl{ are accordingly reported as observed "
            r"differences from the label values, and are not interpreted as independent accuracy "
            r"figures for the three nutrients.}")

replace_once(OLD_CONC, NEW_CONC, "conclusions paragraph")


# ---------------------------------------------------------------------------
# 6. Label the Results section so the new cross-references resolve
# ---------------------------------------------------------------------------
replace_once("\\section{Results}", "\\section{Results}\n\\label{sec:results}",
             "label on Results section")

DST.write_text(s, encoding="utf-8")
print()
print(f"written: {DST.name}")
print(f"  original {orig_len} chars -> revised {len(s)} chars (+{len(s)-orig_len})")
print(f"  original left untouched: {SRC.name}")
