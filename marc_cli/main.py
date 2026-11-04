#!/usr/bin/env python3
"""
marc: fast lookup of MARC 21 Bibliographic and Holdings field definitions.

    marc 245          field with its subfields
    marc 245a         one subfield (245$a also works)
    marc 5xx / 24x    list fields matching a pattern
    marc 008/23       character position(s) in LDR, 006, 007 or 008
    marc isbn         keyword search
    marc -v 245       full detail (definition, indicators, examples)
    marc -h 852       Holdings format instead of Bibliographic
"""

import argparse
import json
import os
import re
import sys
import textwrap
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
FORMAT_NAMES = {"bibliographic": "Bibliographic", "holdings": "Holdings"}

# --------------------------------------------------------------------------- colour


_ESC = chr(27) + "["
PALETTE = {
    name: _ESC + code + "m"
    for name, code in {
        "FIELD": "1;36", "TAG": "34", "SUB": "35", "HEAD": "1;33", "R": "32", "NR": "33",
        "DIM": "2", "WARN": "33", "ERR": "31", "OK": "32", "RESET": "0",
    }.items()
}


class C:
    """ANSI colour codes; empty unless setup_colour() finds a terminal."""


for _name in PALETTE:
    setattr(C, _name, "")


def setup_colour() -> None:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return
    if sys.platform == "win32":
        try:
            from colorama import just_fix_windows_console

            just_fix_windows_console()
        except ImportError:
            pass
    for name, code in PALETTE.items():
        setattr(C, name, code)


# --------------------------------------------------------------------------- data


@lru_cache(maxsize=None)
def load(fmt: str) -> dict:
    path = DATA_DIR / f"{fmt}.json"
    if not path.exists():
        sys.exit(f"{C.ERR}Data file not found: {path}\n"
                 f"{C.WARN}Run 'python scrape_marc.py' to generate it.{C.RESET}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["fields"]


def find_field(tag: str, fmt: str) -> tuple[dict | None, str]:
    """Look up a tag; bibliographic lookups fall back to holdings (841-878 etc.)."""
    fields = load(fmt)
    if tag in fields:
        return fields[tag], fmt
    if fmt == "bibliographic" and tag in load("holdings"):
        return load("holdings")[tag], "holdings"
    return None, fmt


# --------------------------------------------------------------------------- query parsing

CODE_RE = re.compile(r"^(ldr|leader|\d{3})\s*(?:[$‡|]?\s*([a-z0-9]))?$", re.I)
POSITION_RE = re.compile(r"^(ldr|leader|\d{3})\s*/\s*(\d{1,2})(?:\s*-\s*(\d{1,2}))?$", re.I)
PATTERN_RE = re.compile(r"^[\dx]{3}$", re.I)


def norm_tag(tag: str) -> str:
    return "LDR" if tag.lower() in ("ldr", "leader") else tag


def pos_range(pos: str) -> tuple[int, int] | None:
    m = re.match(r"^(\d{1,2})(?:-(\d{1,2}))?$", pos.strip())
    if not m:
        return None
    start = int(m.group(1))
    return start, int(m.group(2) or start)


# --------------------------------------------------------------------------- formatting


def width() -> int:
    try:
        cols = os.get_terminal_size().columns
    except OSError:  # not a terminal
        cols = 100
    return min(cols, 110)


def wrap(text: str, indent: str = "  ") -> str:
    out = []
    for para in text.split("\n\n"):
        out.append(textwrap.fill(para, width(), initial_indent=indent, subsequent_indent=indent))
    return "\n".join(out)


def rep(repeatable: bool | None) -> str:
    if repeatable is None:
        return ""
    return f"{C.R}(R){C.RESET}" if repeatable else f"{C.NR}(NR){C.RESET}"


def field_line(f: dict) -> str:
    aliases = f" {C.DIM}[{', '.join(f['aliases'])}]{C.RESET}" if f.get("aliases") else ""
    return f"{C.FIELD}{f['tag']:<6}{C.RESET} {f['name']} {rep(f['repeatable'])}{aliases}"


def subfield_line(tag: str, sf: dict) -> str:
    return f"{C.TAG}{tag}{C.SUB}${sf['code']}{C.RESET}  {sf['name']} {rep(sf['repeatable'])}"


def format_note(fmt: str, asked: str) -> str:
    if fmt == asked:
        return ""
    return f"{C.DIM}({FORMAT_NAMES[fmt]} format; use -h to search holdings directly){C.RESET}\n"


def print_concise(f: dict) -> None:
    print(field_line(f))
    for sf in sort_subfields(f["subfields"]):
        print(subfield_line(f["tag"], sf))
    if f["positions"]:
        print_positions_short(f["tag"], f["positions"])
    for v in f.get("variants", []):
        print(f"  {C.HEAD}{v['name']}{C.RESET}")
        print_positions_short(f["tag"], v["positions"], indent="    ")


def print_positions_short(tag: str, positions: list[dict], indent: str = "  ") -> None:
    for p in positions:
        print(f"{indent}{C.TAG}{tag}/{p['position']:<6}{C.RESET} {p['name']}")


def sort_subfields(subfields: list[dict]) -> list[dict]:
    """Letters before digits, as LOC lists them."""
    return sorted(subfields, key=lambda s: (s["code"].isdigit(), s["code"]))


def heading(text: str) -> None:
    print(f"\n{C.HEAD}{text}{C.RESET}")


def print_values(values: list[dict], indent: str, verbose: bool = True) -> None:
    for v in values:
        print(f"{indent}{C.SUB}{v['code']}{C.RESET} - {v['label']}")
        if verbose and v.get("description"):
            print(f"{C.DIM}{wrap(v['description'], indent + '    ')}{C.RESET}")


def print_position(tag: str, p: dict, verbose: bool) -> None:
    print(f"  {C.TAG}{tag}/{p['position']}{C.RESET} - {C.FIELD}{p['name']}{C.RESET}")
    if verbose and p.get("description"):
        print(wrap(p["description"], "      "))
    print_values(p["values"], "      ", verbose)


def print_verbose(f: dict, only_subfield: str | None = None) -> None:
    bar = "=" * min(width(), 70)
    print(f"{C.FIELD}{bar}\n{f['tag']} - {f['name']} {rep(f['repeatable'])}{C.FIELD}\n{bar}{C.RESET}")

    if only_subfield:
        sf = next((s for s in f["subfields"] if s["code"] == only_subfield), None)
        print(subfield_line(f["tag"], sf))
        if sf["description"]:
            print(wrap(sf["description"]))
        return

    if f["definition"]:
        heading("Definition")
        print(wrap(f["definition"]))

    if f["indicators"]:
        heading("Indicators")
        for ind in f["indicators"]:
            print(f"  {C.SUB}{ind['position']}{C.RESET} - {ind['name']}")
            if ind.get("description"):
                print(f"{C.DIM}{wrap(ind['description'], '      ')}{C.RESET}")
            print_values(ind["values"], "      ")

    if f["subfields"]:
        heading("Subfields")
        for sf in sort_subfields(f["subfields"]):
            print(f"  {C.SUB}${sf['code']}{C.RESET} - {sf['name']} {rep(sf['repeatable'])}")
            if sf["description"]:
                print(f"{C.DIM}{wrap(sf['description'], '      ')}{C.RESET}")

    if f["positions"]:
        heading("Character positions")
        for p in f["positions"]:
            print_position(f["tag"], p, verbose=True)

    for v in f.get("variants", []):
        heading(f"Character positions: {v['name']}")
        for p in v["positions"]:
            print_position(f["tag"], p, verbose=True)

    if f["examples"]:
        heading("Examples")
        for i, ex in enumerate(f["examples"][:6], 1):
            print(f"  {C.OK}{i}.{C.RESET} {ex}")

    print(f"\n{C.DIM}{f['url']}{C.RESET}")


# --------------------------------------------------------------------------- commands


def cmd_code(tag: str, sub: str | None, fmt: str, verbose: bool) -> int:
    f, found_fmt = find_field(tag, fmt)
    if not f:
        print(f"{C.WARN}No {FORMAT_NAMES[fmt].lower()} field {tag}.{C.RESET}")
        return 1
    print(format_note(found_fmt, fmt), end="")
    if sub:
        sub = sub.lower()
        sf = next((s for s in f["subfields"] if s["code"] == sub), None)
        if not sf:
            print(f"{C.WARN}Field {tag} has no subfield ${sub}.{C.RESET}")
            print(field_line(f))
            return 1
        if verbose:
            print_verbose(f, only_subfield=sub)
        else:
            print(subfield_line(tag, sf))
        return 0
    if verbose:
        print_verbose(f)
    else:
        print_concise(f)
    return 0


def cmd_position(tag: str, start: int, end: int, fmt: str, verbose: bool) -> int:
    f, found_fmt = find_field(tag, fmt)
    if not f:
        print(f"{C.WARN}No {FORMAT_NAMES[fmt].lower()} field {tag}.{C.RESET}")
        return 1
    print(format_note(found_fmt, fmt), end="")
    groups = [("", f["positions"])] + [(v["name"], v["positions"]) for v in f.get("variants", [])]
    found = False
    for name, positions in groups:
        hits = []
        for p in positions:
            r = pos_range(p["position"])
            if r and r[0] <= end and start <= r[1]:
                hits.append(p)
        if hits:
            found = True
            if name:
                heading(f"{tag} - {name}")
            for p in hits:
                print_position(tag, p, verbose)
    if not found:
        print(f"{C.WARN}No character position {start:02d}"
              f"{'-%02d' % end if end != start else ''} defined for {tag}.{C.RESET}")
        return 1
    return 0


def cmd_pattern(pattern: str, fmt: str) -> int:
    rx = re.compile("^" + pattern.lower().replace("x", r"\d") + "$")
    fields = [f for t, f in load(fmt).items() if rx.match(t)]
    if not fields:
        print(f"{C.WARN}No {FORMAT_NAMES[fmt].lower()} fields match {pattern.upper()}.{C.RESET}")
        return 1
    print(f"{C.OK}{FORMAT_NAMES[fmt]} fields matching {pattern.upper()} ({len(fields)}):{C.RESET}\n")
    for f in fields:
        print(field_line(f))
    return 0


def cmd_prefix(prefix: str, fmt: str) -> int:
    fields = [f for t, f in load(fmt).items() if t.startswith(prefix)]
    if not fields:
        print(f"{C.WARN}No {FORMAT_NAMES[fmt].lower()} fields start with {prefix}.{C.RESET}")
        return 1
    for f in fields:
        print(field_line(f))
    return 0


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def search(query: str, fmt: str, deep: bool) -> list[tuple[int, str, str, str]]:
    """Return (score, tag, matched name, display line); lower score ranks higher."""
    q = query.lower().strip()
    qwords = words(q)
    whole = lambda text: bool(qwords) and qwords <= words(text)
    hits = []
    for tag, f in load(fmt).items():
        aliases = [a.lower() for a in f.get("aliases", [])]
        if q in aliases:
            score = 0
        elif whole(f["name"]):
            score = 1
        elif q in f["name"].lower():
            score = 2
        elif deep and q in f["definition"].lower():
            score = 6
        else:
            score = None
        if score is not None:
            hits.append((score, tag, f["name"], field_line(f)))

        for sf in f["subfields"]:
            if whole(sf["name"]):
                score = 3
            elif q in sf["name"].lower():
                score = 4
            elif deep and q in sf["description"].lower():
                score = 7
            else:
                continue
            # Generic control subfields ($6 Linkage, $8 ...) appear everywhere; rank them lower
            hits.append((score + 0.5 * sf["code"].isdigit(), tag, sf["name"], subfield_line(tag, sf)))

        # Character positions: same position often recurs per material type, so group them
        found: dict[tuple, list[str]] = {}
        groups = [("", f["positions"])] + [(v["name"], v["positions"]) for v in f.get("variants", [])]
        for group, positions in groups:
            for p in positions:
                value = next((v for v in p["values"] if whole(v["label"])), None)
                if whole(p["name"]):
                    key = (3, p["position"], p["name"], "")
                elif q in p["name"].lower():
                    key = (4, p["position"], p["name"], "")
                elif value:
                    key = (5, p["position"], p["name"], f"{value['code']} - {value['label']}")
                else:
                    continue
                found.setdefault(key, []).append(group)
        for (score, pos, name, value), grp in found.items():
            where = f" {C.DIM}({', '.join(g for g in grp if g)}){C.RESET}" if any(grp) else ""
            extra = f": {C.SUB}{value}{C.RESET}" if value else ""
            hits.append((score, tag, name, f"{C.TAG}{tag}/{pos:<6}{C.RESET} {name}{extra}{where}"))

    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def cmd_keyword(query: str, fmt: str, deep: bool) -> int:
    hits = search(query, fmt, deep)
    if not hits:
        tip = "" if deep else " Try -v to search definitions too."
        print(f"{C.WARN}No {FORMAT_NAMES[fmt].lower()} fields match '{query}'.{tip}{C.RESET}")
        return 1
    if len(hits) > 1:
        print(f"{C.OK}{len(hits)} matches:{C.RESET}\n")
    for hit in hits:
        print(hit[3])
    return 0


def update_installation() -> int:
    """git pull for a clone installed with `uv tool install -e`; otherwise say how to upgrade.

    A PyPI install isn't upgraded from here: on Windows the running marc.exe is
    locked, so `uv tool upgrade` has to be run on its own.
    """
    repo_dir = Path(__file__).resolve().parent.parent
    if not (repo_dir / ".git").exists():
        print("marcfinder was installed from PyPI. To update, run:\n\n"
              f"  {C.FIELD}uv tool upgrade marcfinder{C.RESET}\n\n"
              f"{C.DIM}(or 'pip install -U marcfinder' if you installed it with pip){C.RESET}")
        return 0
    import subprocess

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True)

    print(f"{C.FIELD}Updating marcfinder in {repo_dir}...{C.RESET}")
    try:
        before = git("rev-parse", "HEAD").stdout.strip()
        result = git("pull", "--ff-only")
    except FileNotFoundError:
        print(f"{C.ERR}git not found. Is git installed and on your PATH?{C.RESET}")
        return 1
    for out in (result.stdout, result.stderr):
        if out:
            print(out.rstrip())
    if result.returncode:
        print(f"{C.ERR}git pull failed (exit code {result.returncode}). If you have local "
              f"changes in {repo_dir}, commit or stash them first.{C.RESET}")
        return result.returncode
    # Code and data update in place, but new dependencies need a reinstall
    changed = git("diff", "--name-only", before, "HEAD", "--", "pyproject.toml").stdout.strip()
    if changed:
        print(f"{C.WARN}Dependencies changed. Finish the update with:\n\n"
              f"  uv tool install --reinstall -e \"{repo_dir}\"{C.RESET}")
    print(f"{C.OK}Update complete.{C.RESET}")
    return 0


def run(query: str, fmt: str, verbose: bool) -> int:
    q = query.strip()
    if m := POSITION_RE.match(q):
        start = int(m.group(2))
        return cmd_position(norm_tag(m.group(1)), start, int(m.group(3) or start), fmt, verbose)
    if m := CODE_RE.match(q):
        return cmd_code(norm_tag(m.group(1)), m.group(2), fmt, verbose)
    if PATTERN_RE.match(q) and "x" in q.lower():
        return cmd_pattern(q, fmt)
    if re.fullmatch(r"\d{1,2}", q):
        return cmd_prefix(q, fmt)
    return cmd_keyword(q, fmt, deep=verbose)


def main() -> None:
    setup_colour()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="marc",
        description="Look up MARC 21 Bibliographic and Holdings field definitions.",
        epilog=__doc__.split("\n", 2)[2],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,  # -h means holdings; help is --help
    )
    parser.add_argument("query", nargs="*", help="field code, pattern, position or keyword(s)")
    parser.add_argument("-h", "--holdings", action="store_true",
                        help="use the MARC 21 Holdings format")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="full detail; for keywords, also search definitions")
    parser.add_argument("-up", "--update", action="store_true", help="update marcfinder")
    parser.add_argument("--help", action="help", help="show this help and exit")
    args = parser.parse_args()

    if args.update:
        sys.exit(update_installation())
    if not args.query:  # includes a bare `marc -h`
        parser.print_help()
        return
    fmt = "holdings" if args.holdings else "bibliographic"
    try:
        sys.exit(run(" ".join(args.query), fmt, args.verbose))
    except BrokenPipeError:  # e.g. piped into `head`
        sys.stdout = None


if __name__ == "__main__":
    main()
