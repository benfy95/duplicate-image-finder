"""Numbered variants: files like 99591443_p0 / 99591443_p1 are pages of one set,
not duplicates. They are kept visible but are not ticked automatically.

Pattern syntax (one per line, case-insensitive, matched against the file name
without extension):
    *   any text            #   the number that changes
    re:<regex>              advanced; name the number group (?P<num>...)

Two files are variants when they match the same pattern with the same text
around the number and a *different* number.
"""

import os
import re

DEFAULT_PATTERNS = []               # ships empty; users add their own (e.g. "*_p#" for Pixiv)
VARIANT_KIND = "variant"


def split_patterns(text):
    """Patterns are entered comma-separated (newlines also accepted)."""
    return [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]

# Windows copy names are real copies, never variants.
_COPY_NAME = re.compile(r"(\s\(\d+\)|\s-\s(copy|複製|副本)(\s\(\d+\))?)$", re.IGNORECASE)


def compile_patterns(lines):
    """-> list of (source_line, compiled_regex). Invalid lines are skipped."""
    out = []
    for raw in lines or []:
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        try:
            if line.lower().startswith("re:"):
                rx = re.compile(line[3:].strip(), re.IGNORECASE)
            else:
                if "#" not in line:
                    continue
                parts = []
                for ch in line:
                    if ch == "*":
                        parts.append("(.+?)")
                    elif ch == "#":
                        parts.append("(?P<num>\\d+)")
                    else:
                        parts.append(re.escape(ch))
                rx = re.compile("".join(parts), re.IGNORECASE)
            out.append((line, rx))
        except (re.error, IndexError):
            continue
    return out


def check_patterns(lines):
    """Lines that are not valid patterns (for the editor to report)."""
    bad = []
    for raw in lines or []:
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if not compile_patterns([line]):
            bad.append(line)
    return bad


def variant_key(name, compiled):
    """(pattern index, text around the number, number) or None."""
    stem = os.path.splitext(os.path.basename(name))[0]
    if _COPY_NAME.search(stem):
        return None
    for pi, (_, rx) in enumerate(compiled):
        m = rx.fullmatch(stem)
        if not m:
            continue
        if "num" in rx.groupindex:
            g = "num"
        elif m.lastindex:
            g = m.lastindex                    # re: pattern without a named group
        else:
            continue
        num = m.group(g)
        if num is None or not num.isdigit():
            continue
        s, e = m.span(g)
        around = (stem[:s] + "\0" + stem[e:]).lower()
        return pi, around, int(num)
    return None


def are_variants(name_a, name_b, compiled):
    a, b = variant_key(name_a, compiled), variant_key(name_b, compiled)
    return bool(a and b and a[:2] == b[:2] and a[2] != b[2])


def norm_stem(name):
    """File name without extension and without a Windows copy suffix, lower-case.
    'Image_01 (1).PNG' -> 'image_01'. Files with equal norm_stem are copies."""
    stem = os.path.splitext(os.path.basename(name))[0]
    return _COPY_NAME.sub("", stem).strip().lower()


def prefix_key(name, n):
    """First n characters of the (normalized) name, or None if it is shorter."""
    if n <= 0:
        return None
    s = norm_stem(name)
    return s[:n] if len(s) >= n else None


def safety_reason(name_a, name_b, sha_a=None, sha_b=None):
    """Why two files must stay duplicates whatever the exception rules say."""
    if sha_a and sha_a == sha_b:
        return "identical"
    if norm_stem(name_a) == norm_stem(name_b):
        return "same_name"      # same name in another format, or a Windows copy
    return None


def explain(name_a, name_b, compiled, prefix_len):
    """For the tester: ('safety', reason) | ('pattern', source) | ('prefix', n) | None."""
    r = safety_reason(name_a, name_b)
    if r:
        return "safety", r
    a, b = variant_key(name_a, compiled), variant_key(name_b, compiled)
    if a and b and a[:2] == b[:2] and a[2] != b[2]:
        return "pattern", compiled[a[0]][0]
    pa, pb = prefix_key(name_a, prefix_len), prefix_key(name_b, prefix_len)
    if pa is not None and pa == pb:
        return "prefix", prefix_len
    return None


def apply_variants(groups, ft, lines, prefix_len=0, auto_kinds=("exact", "similar", "cropped")):
    """Exception rules: mark members as 'variant' (kept, not ticked).

    Two independent rules; either one is enough:
      1. name patterns (lines)      e.g. 12345678_p0 / 12345678_p1
      2. same first prefix_len characters (0 = off)   e.g. image_01 / image_02
    Safety always wins: byte-identical files and files with the same name
    (other format, Windows copy) stay duplicates.

    Within a group, files of one family are bucketed by their normalized name;
    the best file of each name is kept, other files with that same name stay
    duplicates. m.reason records which rule applied ('pattern' / 'prefix:N').
    Members keep their original match type in base_kind, so this can be
    re-applied when the rules change. Returns the groups re-sorted
    (groups with nothing ticked last)."""
    compiled = compile_patterns(lines)
    for g in groups:
        for k, m in enumerate(g.members):
            if not getattr(m, "base_kind", ""):
                m.base_kind = m.kind
            m.kind = m.base_kind
            m.reason = ""
            m.remove = k != 0 and m.kind in auto_kinds
        if not compiled and prefix_len <= 0:
            continue
        names = [ft.paths[m.idx] for m in g.members]

        def mark(families, reason):
            for buckets in families.values():
                if len(buckets) < 2:            # only one distinct name: nothing to except
                    continue
                kept = [0]                       # the best file of the group is always kept
                for ks in buckets.values():
                    head = ks[0]                 # members are sorted best-first
                    m = g.members[head]
                    if head == 0 or m.kind == VARIANT_KIND or m.base_kind == "exact":
                        continue
                    sha = ft.sha[m.idx]
                    if any(safety_reason(names[head], names[j], sha, ft.sha[g.members[j].idx]) for j in kept):
                        continue
                    m.kind, m.reason, m.remove = VARIANT_KIND, reason, False
                    kept.append(head)

        if compiled:                              # rule 1: name patterns
            fam = {}
            for k, nm in enumerate(names):
                key = variant_key(nm, compiled)
                if key:
                    fam.setdefault(key[:2], {}).setdefault(key[2], []).append(k)
            mark(fam, "pattern")
        if prefix_len > 0:                        # rule 2: same beginning of name
            fam = {}
            for k, nm in enumerate(names):
                key = prefix_key(nm, prefix_len)
                if key is not None:
                    fam.setdefault(key, {}).setdefault(norm_stem(nm), []).append(k)
            mark(fam, f"prefix:{prefix_len}")
    groups.sort(key=lambda g: (not any(m.remove for m in g.members),
                               -sum(int(ft.size[m.idx]) for m in g.members if m.remove)))
    return groups
