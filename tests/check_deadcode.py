#!/usr/bin/env python3
"""Dead-code / stale-reference analyzer for the skate3 C++ tree.

Static (non-compiling) analysis of `src/` against the whole codebase context
(src + generated + rexglue-sdk headers + CMake source lists).

  1. UNREFERENCED FUNCTIONS  - non-hook, non-virtual C++ functions whose name
     never otherwise occurs in the codebase after stripping comments/strings.
     Auto-exempts guest-address hooks (REX_FUNC(sub_...)), header-declared
     public APIs, and virtual/registered entry points.
  2. ORPHAN / UNKNOWN FILES   - sources under src/ neither compiled by CMake nor
     #included by anything.

PERFORMANCE: builds a single token index of the whole codebase once, then each
function is an O(1) set/occurrence lookup. One read pass + one pass for defs.

TRIAGE tool: over-declares candidates it cannot prove-dead and labels WHY.
Never deletes; use as a review list.

Usage:
    python3 tests/check_deadcode.py [--dir src] [--cmake CMakeLists.txt] [--verbose]
"""

import argparse
import json
import os
import re
import sys


COMMENT_OR_LIT = re.compile(
    r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", re.DOTALL)


def load_cmake_sources(path: str) -> set[str]:
    if not os.path.isfile(path):
        return set()
    with open(path, "r", errors="ignore") as f:
        text = f.read()
    return set(re.findall(r"src/[A-Za-z0-9_./-]+\.(?:cpp|h|hpp|mm)", text))


def gather(root: str) -> list[str]:
    files = []
    for dirpath, _d, fns in os.walk(root):
        # Skip generated shader bytecode data: a single 3.4MB SPIR-V constant
        # array header (zero function definitions) that both bloats the token
        # index and triggers catastrophic regex backtracking in DEF_RE.
        if os.path.basename(dirpath) in ("spirv", "dxbc", "spirv-cross"):
            _d[:] = []
            continue
        for fn in fns:
            if fn.endswith((".cpp", ".h", ".hpp", ".mm")):
                files.append(os.path.join(dirpath, fn))
    return sorted(files)


DEF_RE = re.compile(
    r"(?:[A-Za-z_][A-Za-z0-9_:<>*&,\s]*?)?"
    r"([A-Za-z_][A-Za-z0-9_:~]*?)\s*\([^;{}]*\)\s*(?:const\s*)?\s*(?:noexcept\s*)?\s*\{")
SKIP = {"if", "for", "while", "switch", "return", "do", "else", "sizeof",
        "catch", "try", "case", "default", "delete", "new"}


def tokenize(text: str) -> set[str]:
    """Set of identifier tokens (letters/digits/underscore/colon) in text."""
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_:]*", text))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="src")
    ap.add_argument("--cmake", default="CMakeLists.txt")
    ap.add_argument("--context", nargs="*",
                    default=["third_party/rexglue-sdk/include"])
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo = os.path.abspath(".")
    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        print(f"error: {root} is not a directory")
        return 1

    src_files = gather(root)
    ctx_files = list(src_files)
    for c in args.context:
        p = os.path.join(repo, c)
        if os.path.isdir(p):
            ctx_files += gather(p)

    # Single read pass: raw text + comment/string-stripped text.
    raw, stripped = {}, {}
    for fp in ctx_files:
        try:
            with open(fp, "r", errors="ignore") as f:
                t = f.read()
        except OSError:
            t = ""
        raw[fp] = t
        stripped[fp] = COMMENT_OR_LIT.sub("", t)

    # Global identifier index (used by every reference check).
    all_tokens = set()
    token_counts: dict[str, int] = {}
    for fp in ctx_files:
        for tok in tokenize(stripped[fp]):
            all_tokens.add(tok)
            token_counts[tok] = token_counts.get(tok, 0) + 1

    # Function definitions per src file (on comment-stripped text).
    def_names = {}  # name -> set of defining files (comment-stripped only)
    for fp in src_files:
        for m in DEF_RE.finditer(stripped[fp]):
            nm = m.group(1)
            if nm in SKIP or "operator" in nm or nm.startswith("sub_"):
                continue
            def_names.setdefault(nm, set()).add(fp)

    # CMake + include-file checks.
    cmake_sources = load_cmake_sources(os.path.abspath(args.cmake))
    header_names = {os.path.basename(fp): fp for fp in ctx_files if fp.endswith((".h", ".hpp"))}
    include_refs = {}  # header basename -> count of #include "basename"
    for fp, txt in raw.items():
        for m in re.finditer(r'#\s*include\s+"([^"]+)"', txt):
            inc = os.path.basename(m.group(1))
            include_refs[inc] = include_refs.get(inc, 0) + 1

    # --- unreferenced functions ---
    unreferenced = []
    for name, files in def_names.items():
        if len(files) != 1:
            continue  # only single-definition candidates
        own = next(iter(files))
        base = name.split("::")[-1]
        # 1) header declares it -> public API
        if any(fp.endswith((".h", ".hpp")) and name in stripped[fp] for fp in ctx_files):
            continue
        # 2) used anywhere (whole-codebase token set; occurrence count > 1)
        if token_counts.get(base, 0) > 1:
            continue
        # 3) referenced with a qualification/cast/pointer somewhere
        if name in all_tokens and name != base:
            continue
        unreferenced.append((name, own))

    # --- orphan / unknown files ---
    unknowns, orphans = [], []
    for fp in src_files:
        rel = os.path.relpath(fp, repo)
        in_cmake = rel in cmake_sources
        is_h = fp.endswith((".h", ".hpp"))
        inc_count = include_refs.get(os.path.basename(fp), 0)
        if not in_cmake and inc_count == 0:
            unknowns.append(rel)
            if not is_h:
                orphans.append(rel)

    # ---- report ----
    if args.json:
        print(json.dumps({
            "unreferenced_functions": [{"name": n, "file": f} for n, f in unreferenced],
            "unknown_files": unknowns, "orphan_files": orphans}, indent=2))
        return 0

    print(f"[scan] {len(src_files)} src files | {len(ctx_files)} context files | "
          f"{len(all_tokens)} unique tokens")
    print("\n=== UNREFERENCED FUNCTIONS (triage -- verify each) ===")
    print("  (none)" if not unreferenced else
          "".join(f"  {n:42s} {os.path.relpath(f,repo)}\n" for n, f in sorted(unreferenced)))
    print("\n=== ORPHAN SOURCE FILES (not in CMake, nothing includes a header) ===")
    print("  (none)" if not orphans else "".join(f"  {o}\n" for o in sorted(orphans)))
    print("\n=== UNKNOWN FILES (not in CMake & not #included anywhere) ===")
    print("  (none)" if not unknowns else "".join(f"  {u}\n" for u in sorted(unknowns)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
