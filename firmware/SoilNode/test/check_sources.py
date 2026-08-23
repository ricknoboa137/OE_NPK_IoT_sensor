"""Static checks for the SoilNode sources, for editing without a toolchain.

    python check_sources.py ..

Catches the mistakes that cost a full compile-flash cycle to discover:
unterminated string literals, unbalanced brackets, printf argument counts,
unresolved local includes, methods declared but never defined, and stray NUL
bytes. It is not a compiler and does not pretend to be one - it will not catch
a type error - but everything it does check, it checks cheaply.

Exit status is non-zero if anything is wrong, so it can gate a commit.
"""
import pathlib, re, sys

BS = chr(92)
SRC_SUFFIXES = ('.h', '.cpp', '.ino')


def strip_code(src):
    """Remove comments and string/char literals, keeping everything else."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j
        elif c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif c in '"\'':
            q, i = c, i + 1
            while i < n:
                if src[i] == BS:
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def unterminated_literals(src):
    """Lines where a string literal opens and never closes."""
    bad = []
    for lineno, line in enumerate(src.split('\n'), 1):
        i, n, in_str = 0, len(line), False
        while i < n:
            c = line[i]
            if not in_str:
                if c == '/' and i + 1 < n and line[i + 1] == '/':
                    break
                if c == '"':
                    in_str = True
                i += 1
            else:
                if c == BS:
                    i += 2
                    continue
                if c == '"':
                    in_str = False
                i += 1
        if in_str:
            bad.append((lineno, line.strip()[:70]))
    return bad


SPEC = re.compile(
    r'%[-+ #0]*(?P<w>\*|[0-9]*)(?:\.(?P<p>\*|[0-9]*))?'
    r'(?:hh|h|ll|l|j|z|t|L)?[diouxXeEfFgGaAcspn%]'
)
CALL = re.compile(r'\.printf\s*\(')


def split_top_level(text):
    args, depth, cur, i, n = [], 0, [], 0, len(text)
    in_str = in_chr = False
    while i < n:
        c = text[i]
        if in_str:
            if c == BS:
                cur.append(text[i:i + 2]); i += 2; continue
            if c == '"':
                in_str = False
        elif in_chr:
            if c == BS:
                cur.append(text[i:i + 2]); i += 2; continue
            if c == "'":
                in_chr = False
        else:
            if c == '"':
                in_str = True
            elif c == "'":
                in_chr = True
            elif c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
            elif c == ',' and depth == 0:
                args.append(''.join(cur).strip()); cur = []; i += 1; continue
        cur.append(c); i += 1
    if ''.join(cur).strip():
        args.append(''.join(cur).strip())
    return args


def printf_calls(src):
    for m in CALL.finditer(src):
        start, depth, i, n = m.end(), 1, m.end(), len(src)
        in_str = in_chr = False
        while i < n and depth:
            c = src[i]
            if in_str:
                if c == BS: i += 2; continue
                if c == '"': in_str = False
            elif in_chr:
                if c == BS: i += 2; continue
                if c == "'": in_chr = False
            else:
                if c == '"': in_str = True
                elif c == "'": in_chr = True
                elif c == '(': depth += 1
                elif c == ')': depth -= 1
            i += 1
        yield m.start(), src[start:i - 1]


LIT = r'"((?:[^"' + BS + BS + r']|' + BS + r'.)*)"'


def literal_format(arg):
    parts = re.findall(LIT, arg)
    if parts and re.sub(LIT, '', arg).strip() == '':
        return ''.join(parts)
    return None


def main(root):
    root = pathlib.Path(root)
    files = {p.name: p.read_text(encoding='utf-8')
             for p in sorted(root.glob('*')) if p.suffix in SRC_SUFFIXES}
    if not files:
        print(f"no sources found in {root}")
        return 1

    problems = 0

    for name, src in files.items():
        if b'\x00' in (root / name).read_bytes():
            print(f"  !! {name}: contains NUL bytes")
            problems += 1
        for lineno, text in unterminated_literals(src):
            print(f"  !! {name}:{lineno} unterminated string literal: {text}")
            problems += 1
        code = strip_code(src)
        for open_c, close_c, label in (('{', '}', 'braces'),
                                       ('(', ')', 'parens'),
                                       ('[', ']', 'brackets')):
            d = code.count(open_c) - code.count(close_c)
            if d:
                print(f"  !! {name}: {label} unbalanced by {d:+d}")
                problems += 1
        for inc in re.findall(r'#include\s+"([^"]+)"', src):
            if inc not in files:
                print(f"  !! {name}: includes missing {inc}")
                problems += 1
        for pos, inner in printf_calls(src):
            args = split_top_level(inner)
            if not args:
                continue
            fmt = literal_format(args[0])
            if fmt is None:
                continue
            need = 0
            for m in SPEC.finditer(fmt):
                if m.group(0) == '%%':
                    continue
                need += 1 + (m.group('w') == '*') + (m.group('p') == '*')
            if need != len(args) - 1:
                line = src[:pos].count('\n') + 1
                print(f"  !! {name}:{line} printf needs {need} args, "
                      f"has {len(args) - 1}: {fmt[:50]!r}")
                problems += 1

    for hname, hsrc in files.items():
        if not hname.endswith('.h'):
            continue
        for m in re.finditer(r'class\s+(\w+)[^;{]*\{(.*?)\n\};', hsrc, re.S):
            cls, body = m.group(1), m.group(2)
            for d in re.finditer(
                    r'^\s*(?:virtual\s+)?[\w:<>&*\s]+?\b(\w+)\s*\([^;{]*\)\s*'
                    r'(?:const\s*)?(?:override\s*)?;', body, re.M):
                nm = d.group(1)
                if nm in ('if', 'for', 'while', 'return', 'switch', 'typedef', 'void'):
                    continue
                defined = any(re.search(r'\b' + cls + '::' + nm + r'\s*\(', v)
                              for v in files.values())
                inline = re.search(r'\b' + nm + r'\s*\([^;{]*\)\s*(?:const\s*)?\{', body)
                if not defined and not inline:
                    print(f"  !! {hname}: {cls}::{nm} declared but never defined")
                    problems += 1

    print(f"\n  {len(files)} files checked - "
          f"{'all clean' if problems == 0 else str(problems) + ' problem(s)'}")
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
