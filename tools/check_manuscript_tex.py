"""Check the revised manuscript for the things that break soul's \\hl and for
unbalanced structure. Not a compiler, but it catches the usual failures."""
import pathlib, re, sys

p = pathlib.Path(r"C:/Users/User/Documents/GitHub/Agriculture-4351955/agriculture-4351955-revised.tex")
orig = pathlib.Path(r"C:/Users/User/Documents/GitHub/Agriculture-4351955/agriculture-4351955.tex")
s = p.read_text(encoding="utf-8")
o = orig.read_text(encoding="utf-8")

problems = 0


def brace_spans(text, macro):
    """Yield (start, end, body) for each macro{...}, brace-matched."""
    for m in re.finditer(re.escape("\\" + macro) + r"\{", text):
        i = m.end() - 1
        depth = 0
        j = i
        while j < len(text):
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    yield m.start(), j + 1, text[i + 1:j]
                    break
            j += 1


print("=== \\hl spans containing constructs soul cannot typeset ===")
RISK = (("$", "math"), ("\\ref", "\\ref"), ("\\cite", "\\cite"),
        ("\\textbf", "\\textbf"), ("\\texttt", "\\texttt"),
        ("\\label", "\\label"), ("\\\\", "line break"))
new_only = []
for a, b, body in brace_spans(s, "hl"):
    # only report spans that are NOT present in the original file
    if body in o:
        continue
    new_only.append((a, body))
    hits = [name for tok, name in RISK if tok in body]
    if "{" in body or "}" in body:
        hits.append("nested braces")
    if hits:
        line = s[:a].count("\n") + 1
        print(f"  !! line {line}: contains {', '.join(sorted(set(hits)))}")
        print(f"     {body[:100]!r}")
        problems += 1
print(f"  {len(new_only)} newly added \\hl spans checked")
if problems == 0:
    print("  none contain math, refs, cites or nested groups")

print()
print("=== brace balance ===")
depth = 0
i = 0
while i < len(s):
    if s[i] == "\\":
        i += 2
        continue
    if s[i] == "%" and (i == 0 or s[i-1] != "\\"):
        nl = s.find("\n", i)
        i = len(s) if nl < 0 else nl
        continue
    if s[i] == "{":
        depth += 1
    elif s[i] == "}":
        depth -= 1
        if depth < 0:
            print(f"  !! unmatched }} at line {s[:i].count(chr(10))+1}")
            problems += 1
            depth = 0
    i += 1
print(f"  final brace depth {depth}" + ("  ok" if depth == 0 else "   <-- UNBALANCED"))
if depth:
    problems += 1

print()
print("=== environments ===")
for env in ("table", "tabular", "figure", "equation", "document", "center"):
    b = len(re.findall(r"\\begin\{" + env + r"\}", s))
    e = len(re.findall(r"\\end\{" + env + r"\}", s))
    flag = "" if b == e else "   <-- MISMATCH"
    if b != e:
        problems += 1
    print(f"  {env:10} begin {b:3d}  end {e:3d}{flag}")

print()
print("=== cross-references resolve ===")
labels = set(re.findall(r"\\label\{([^}]*)\}", s))
refs = set(re.findall(r"\\(?:ref|cref|Cref)\{([^}]*)\}", s))
missing = sorted(r for r in refs if r not in labels)
if missing:
    for r_ in missing:
        print(f"  !! \\ref{{{r_}}} has no \\label")
    problems += len(missing)
else:
    print(f"  all {len(refs)} refs have labels")
dupes = [l for l in labels if len(re.findall(r"\\label\{" + re.escape(l) + r"\}", s)) > 1]
if dupes:
    print(f"  !! duplicate labels: {dupes}")
    problems += 1

print()
print("=== tabular column counts in new tables ===")
for name in ("tab:collinearity", "tab:labcorr", "tab:calinputs", "tab:calresult"):
    m = re.search(r"\\label\{" + re.escape(name) + r"\}(.*?)\\end\{table\}", s, re.S)
    if not m:
        print(f"  !! {name} not found")
        problems += 1
        continue
    body = m.group(1)
    spec = re.search(r"\\begin\{tabular\}\{([^}]*)\}", body)
    ncol = sum(1 for ch in spec.group(1) if ch in "lcr") if spec else 0
    bad = []
    for row in body.split("\\\\"):
        row = re.sub(r"\\multicolumn\{(\d+)\}", lambda mm: "&" * (int(mm.group(1)) - 1), row)
        if "&" not in row:
            continue
        if re.search(r"\\(toprule|midrule|bottomrule|begin|end|caption|centering)", row.split("&")[0]):
            pass
        cells = row.count("&") + 1
        if cells != ncol:
            bad.append((cells, row.strip()[:60]))
    print(f"  {name}: {ncol} columns" + ("   ok" if not bad else ""))
    for cells, txt in bad:
        print(f"    !! row has {cells} cells: {txt!r}")
        problems += 1

print()
print("=" * 60)
print("clean" if problems == 0 else f"{problems} problem(s) to fix")
sys.exit(1 if problems else 0)
