"""Show the changes of the current round in a second highlight color.

Highlights that were already in the version submitted in the previous round
stay as \\hl{} (yellow). Highlights that are not in that version are changed to
\\hlnew{} (light orange), a command this script defines in the preamble.

A highlight counts as old if the baseline contains it literally as \\hl{...},
or if its text occurs in the baseline. Short fragments (the pieces between
formulas and references) follow the longer highlights of their paragraph.

    C:/Users/User/anaconda3/python.exe tools/paper/mark_new_changes.py [--apply]

Without --apply it only reports what it would change.
"""
import re, sys, pathlib
import paper_data as pd_

BS = chr(92)
HL, HLNEW = BS + "hl{", BS + "hlnew{"
BASELINE = pd_.PAPER / "agriculture-V1-4351955.text"      # as submitted in the previous round
SHORT = 12                                                 # characters, ignoring spaces

PREAMBLE = (
    "% Changes of the current round are shown in light orange; those of the previous round stay yellow.\n"
    + BS + "definecolor{neworange}{RGB}{255,200,140}\n"
    + BS + "DeclareRobustCommand{" + BS + "hlnew}[1]{{" + BS + "sethlcolor{neworange}" + BS + "hl{#1}}}\n")


def manuscript():
    hits = sorted(pd_.PAPER.glob("*revised*.tex"), key=lambda q: q.stat().st_mtime, reverse=True)
    if not hits:
        sys.exit("no revised manuscript found")
    return hits[0]


def norm(text):
    return " ".join(text.split())


def spans(text):
    """(start, end, body) of every \\hl{...} and \\hlnew{...}, brace-matched."""
    out = []
    for m in re.finditer(re.escape(BS) + r"hl(?:new)?\{", text):
        depth, j = 1, m.end()
        while j < len(text) and depth:
            if text[j] == BS:
                j += 2
                continue
            depth += (text[j] == "{") - (text[j] == "}")
            j += 1
        if text[m.end():j - 1] == "#1":          # the definition of the command itself
            continue
        out.append((m.start(), j, text[m.end():j - 1]))
    return out


def strip_markup(text):
    """The text with the highlight commands removed, keeping what they enclose."""
    out, last = [], 0
    for a, b, body in spans(text):
        if a < last:
            continue
        out.append(text[last:a])
        out.append(body)
        last = b
    out.append(text[last:])
    return "".join(out)


def main(apply):
    path = manuscript()
    t = path.read_text(encoding="utf-8")
    base_raw = BASELINE.read_text(encoding="utf-8")
    base_marked = {norm(body) for _, _, body in spans(base_raw)}
    base_text = norm(strip_markup(base_raw))

    sp = spans(t)
    verdict = {}
    for k, (a, b, body) in enumerate(sp):
        nb = norm(body)
        long_enough = len(nb.replace(" ", "")) >= SHORT
        verdict[k] = "old" if (nb in base_marked or (long_enough and nb in base_text)) else "new"

    n_new = sum(v == "new" for v in verdict.values())
    print(f"{path.name}: {len(sp)} highlights, {len(sp) - n_new} from the previous round, {n_new} new")
    print("highlights kept as previous round (yellow):")
    for k, (a, b, body) in enumerate(sp):
        if verdict[k] == "old":
            print(f"  line {t.count(chr(10), 0, a) + 1:4d}: {norm(body)[:90]!r}")
    if not apply:
        print("\nnothing written; run again with --apply")
        return

    out, last = [], 0
    for k, (a, b, body) in enumerate(sp):
        out.append(t[last:a])
        out.append((HLNEW if verdict[k] == "new" else HL) + body + "}")
        last = b
    out.append(t[last:])
    t = "".join(out)
    if BS + "DeclareRobustCommand{" + BS + "hlnew}" not in t:
        anchor = BS + "begin{document}"
        if t.count(anchor) != 1:
            sys.exit("could not place the preamble definition")
        t = t.replace(anchor, PREAMBLE + "\n" + anchor)
    path.write_text(t, encoding="utf-8")
    print(f"\nwritten: {n_new} highlights now use {HLNEW}...}}")


if __name__ == "__main__":
    main("--apply" in sys.argv)
