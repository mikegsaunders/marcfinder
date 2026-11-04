#!/usr/bin/env python3
"""
MARC 21 scraper (Bibliographic + Holdings).

Builds marc_cli/data/<format>.json from the Library of Congress "concise"
documentation at https://www.loc.gov/marc/.

    uv run --extra dev python scrape_marc.py            # use cached pages where present
    uv run --extra dev python scrape_marc.py --refresh  # re-download everything

Pages are cached in .cache/loc/ so re-runs are fast and polite to LOC.

LOC uses several page templates, all handled here:
  * "new" template:  div.definition / div.indicators (dl) / div.subfields (dl) /
                     table.examples or div.examplesec, div.characterPositions
  * "old" template:  bare <p> definition, div.indicatorhead + div.indicatorvalue,
                     div.subfieldhead + div.subfieldvalue, div.example tables
  * holdings 853-878: indicators/subfields live only on shared "general
                     information" pages (e.g. hd863865.html)
  * holdings leader: no concise page; parsed from the full page
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / ".cache" / "loc"
DATA_DIR = ROOT / "marc_cli" / "data"
LOC = "https://www.loc.gov/marc/"
USER_AGENT = "marcfinder-scraper (+https://github.com/mikegsaunders/marcfinder)"

FORMATS = {
    "bibliographic": {
        "prefix": "bd",
        "index_pages": [
            "bd00x.html", "bd01x09x.html", "bd1xx.html", "bd20x24x.html",
            "bd25x28x.html", "bd3xx.html", "bd4xx.html", "bd5xx.html",
            "bd6xx.html", "bd70x75x.html", "bd76x78x.html", "bd760787.html",
            "bd80x83x.html", "bd84188x.html",
        ],
        "leader": "concise/bdleader.html",
        "group_pages": [],
    },
    "holdings": {
        "prefix": "hd",
        "index_pages": [
            "hd00x.html", "hd0xx.html", "hd5xx84x.html", "hd852856.html",
            "hd853855.html", "hd863865.html", "hd866868.html",
            "hd876878.html", "hd88x.html",
        ],
        "leader": "hdleader.html",
        # Fields whose indicators/subfields are only documented on a shared page
        "group_pages": [
            "hd853855.html", "hd863865.html", "hd866868.html", "hd876878.html",
        ],
    },
}

# Extra search terms that don't appear in the official field names
ALIASES = {
    "bibliographic": {
        "010": ["LCCN"], "020": ["ISBN"], "022": ["ISSN"], "024": ["ISMN", "UPC", "EAN", "DOI"],
        "035": ["OCLC", "system control number"], "050": ["LC call number", "LCC"],
        "082": ["Dewey", "DDC"], "100": ["author"], "245": ["title"],
        "260": ["imprint", "publisher"], "264": ["imprint", "publisher", "RDA"],
        "300": ["extent", "pagination"], "336": ["RDA"], "337": ["RDA"], "338": ["RDA"],
        "650": ["subject heading", "LCSH"], "856": ["URL", "URI", "link"],
    },
    "holdings": {
        "852": ["call number", "shelfmark", "location"], "856": ["URL", "URI", "link"],
        "863": ["enumeration", "chronology"], "866": ["summary holdings"],
        "876": ["barcode", "item"],
    },
}

TAG_RE = re.compile(r"(?<![\d/$.])(\d{3})(?![\d/])")
HEADING_RE = re.compile(r"^(?:(\d{3}|Leader)\s*-\s*)?(.*?)\s*\((R|NR)\)\s*$", re.I)
SUBFIELD_RE = re.compile(r"^\$(\w)\s*-\s*(.*?)\s*\((R|NR)\)\s*(\[[^\]]*\])?\s*$")
CODE_LABEL_RE = re.compile(r"^(.+?)\s+-\s+(.*)$")


# --------------------------------------------------------------------------- fetching

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def fetch(url: str, refresh: bool = False) -> str | None:
    """Return page HTML (cached), or None on 404."""
    cache_file = CACHE_DIR / re.sub(r"[^\w.-]", "_", url.removeprefix(LOC))
    if not refresh and cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
        return text or None
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                text = ""
                break
            r.raise_for_status()
            text = r.content.decode("utf-8", errors="replace")
            break
        except requests.RequestException as e:
            if attempt == 2:
                raise
            print(f"  retrying {url}: {e}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(text, encoding="utf-8")
    return text or None


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# --------------------------------------------------------------------------- text helpers


def clean(text: str) -> str:
    return " ".join(text.split())


def own_text(el: Tag, skip=("p", "div", "dd", "dl")) -> str:
    """Text of an element, excluding nested block children (descriptions)."""
    parts = []
    for child in el.children:
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name not in skip:
            parts.append(child.get_text())
    return clean("".join(parts))


def block_text(el: Tag | None) -> str:
    if el is None:
        return ""
    paras = [clean(p.get_text()) for p in el.find_all("p")]
    paras = [p for p in paras if p]
    return "\n\n".join(paras) if paras else clean(el.get_text())


def split_code(text: str) -> tuple[str, str]:
    m = CODE_LABEL_RE.match(text)
    return (m.group(1).strip(), m.group(2).strip()) if m else (text, "")


def has_class(el, *names) -> bool:
    return isinstance(el, Tag) and any(c in (el.get("class") or []) for c in names)


# --------------------------------------------------------------------------- page parsing


def parse_heading(soup: BeautifulSoup) -> tuple[str, bool | None]:
    h1 = soup.find("h1")
    text = clean(h1.get_text()) if h1 else ""
    m = HEADING_RE.match(text)
    if not m:
        return text, None
    return m.group(2).strip(), m.group(3).upper() == "R"


def parse_definition(soup: BeautifulSoup) -> str:
    div = soup.find("div", class_="definition")
    if div:
        return block_text(div)
    # Old template: bare <p> tags after the heading, before the first section
    h1 = soup.find("h1")
    paras = []
    for el in h1.find_all_next() if h1 else []:
        if has_class(el, "indicatorhead", "subfieldhead", "examplehead", "example",
                     "characterposition", "characterPositions"):
            break
        if el.name in ("h3", "h4") and paras:
            break
        if el.name == "p" and not el.find_parent(class_=["example", "examples"]):
            t = clean(el.get_text())
            if t:
                paras.append(t)
    return "\n\n".join(paras)


def parse_indicators(soup: BeautifulSoup) -> list[dict]:
    indicators = []
    div = soup.find("div", class_="indicators")
    if div:  # new template: <dt>First - Name</dt><dd>0 - Value <p>desc</p></dd>
        current = None
        for el in div.find_all(["dt", "dd"]):
            if el.name == "dt":
                pos, name = split_code(own_text(el, skip=("p", "div", "span")))
                current = {"position": pos, "name": name, "values": []}
                desc = clean(" ".join(s.get_text() for s in el.find_all("span", recursive=False)))
                if desc:
                    current["description"] = desc
                indicators.append(current)
            elif current is not None:
                code, label = split_code(own_text(el))
                current["values"].append(
                    {"code": code, "label": label, "description": block_text_or_empty(el)}
                )
        return indicators
    # old template: nested div.indicatorvalue
    for top in soup.find_all("div", class_="indicatorvalue"):
        if top.find_parent("div", class_="indicatorvalue"):
            continue
        pos, name = split_code(own_text(top))
        values = []
        for v in top.find_all("div", class_="indicatorvalue"):
            code, label = split_code(own_text(v))
            desc = v.find("div", class_="description")
            values.append({"code": code, "label": label,
                           "description": clean(desc.get_text()) if desc else ""})
        indicators.append({"position": pos, "name": name, "values": values})
    return indicators


def block_text_or_empty(el: Tag) -> str:
    paras = [clean(p.get_text()) for p in el.find_all(["p", "div"])]
    return "\n\n".join(p for p in paras if p)


def make_subfield(text: str, description: str = "") -> dict | None:
    m = SUBFIELD_RE.match(clean(text))
    if not m or "OBSOLETE" in m.group(2).upper():
        return None
    return {"code": m.group(1).lower(), "name": m.group(2).strip(),
            "repeatable": m.group(3).upper() == "R", "description": description}


def parse_subfields(soup: BeautifulSoup) -> list[dict]:
    subfields = []
    div = soup.find("div", class_="subfields")
    if div:  # new template: <dl><dt>$a - Name (NR)</dt><dd>desc</dd></dl>
        for dt in div.find_all("dt"):
            dd = dt.find_next_sibling()
            desc = clean(dd.get_text()) if dd is not None and dd.name == "dd" else ""
            sf = make_subfield(dt.get_text(), desc)
            if sf:
                subfields.append(sf)
        return subfields
    for el in soup.find_all("div", class_="subfieldvalue"):  # old template
        desc = el.find("div", class_="description")
        sf = make_subfield(own_text(el), clean(desc.get_text()) if desc else "")
        if sf:
            subfields.append(sf)
    return subfields


def parse_examples(soup: BeautifulSoup) -> list[str]:
    examples = []
    containers = soup.find_all(["table", "div"], class_=["examples", "example", "examplesec"])
    seen_rows = set()
    for c in containers:
        for tr in c.find_all("tr"):
            if id(tr) in seen_rows:
                continue
            seen_rows.add(id(tr))
            cells = [clean(td.get_text()) for td in tr.find_all("td")]
            cells = [x for x in cells if x]
            if len(cells) >= 2:
                ex = " ".join(cells[1:])
                if ex not in examples:
                    examples.append(ex)
    return examples


def parse_positions(soup: BeautifulSoup) -> list[dict]:
    positions = []
    div = soup.find("div", class_="characterPositions")
    if div:  # new template
        for item in div.find_all("div", recursive=False):
            strong = item.find("strong")
            if not strong:
                continue
            pos, name = split_code(clean(strong.get_text()))
            desc_div = next((d for d in item.find_all("div", recursive=False)
                             if not has_class(d, "value")), None)
            values = []
            for v in item.find_all("div", class_="value", recursive=False):
                label_el = v.find(class_="valueLabel")
                code, label = split_code(clean(label_el.get_text()) if label_el else "")
                vdesc = label_el.find_next_sibling("div") if label_el else None
                values.append({"code": code, "label": label, "description": block_text(vdesc)
                               if vdesc else ""})
            positions.append({"position": pos, "name": name,
                              "description": block_text(desc_div) if desc_div else "",
                              "values": values})
        return positions
    for item in soup.find_all("div", class_="characterposition"):  # old/full template
        strong = item.find("strong")
        if not strong:
            continue
        pos, name = split_code(clean(strong.get_text()))
        desc = item.find("div", class_="description", recursive=False)
        values = []
        for v in item.find_all("div", class_="charactervalue", recursive=False):
            vs = v.find("strong")
            code, label = split_code(clean(vs.get_text()) if vs else own_text(v))
            vdesc = v.find("div", class_="description")
            values.append({"code": code, "label": label,
                           "description": clean(vdesc.get_text()) if vdesc else ""})
        entry = {"position": pos, "name": name,
                 "description": clean(desc.get_text()) if desc else "", "values": values}
        # 006 lists every material type on one page under "006--BOOKS" style headings
        heading = item.find_previous(string=re.compile(r"^\s*\d{3}--\S"))
        if heading:
            entry["group"] = clean(heading).split("--", 1)[1].title()
        positions.append(entry)
    return positions


def parse_field_page(html: str) -> dict:
    soup = soup_of(html)
    name, repeatable = parse_heading(soup)
    return {
        "name": name,
        "repeatable": repeatable,
        "definition": parse_definition(soup),
        "indicators": parse_indicators(soup),
        "subfields": parse_subfields(soup),
        "positions": parse_positions(soup),
        "examples": parse_examples(soup),
    }


def parse_group_page(html: str) -> tuple[list[str], list[dict], list[dict]]:
    """Holdings general-information pages: (tags, indicators, subfields).

    Values may carry a "[863/864]" note meaning they apply only to those tags;
    that is kept in an "only" list.
    """
    soup = soup_of(html)
    tags = []
    for toc in soup.find_all("div", class_="fieldtoc"):
        m = re.match(r"(\d{3})", clean(toc.get_text()))
        if m:
            tags.append(m.group(1))

    def lines(td: Tag) -> list[str]:
        # split on <br> only, so inline notes like <em>[863/864]</em> stay on their line
        td = soup_of(re.sub(r"<br\s*/?>", "\n", str(td)))
        return [clean(x) for x in td.get_text().split("\n") if clean(x)]

    def restrict(text: str) -> tuple[str, list[str]]:
        m = re.search(r"\[([\d/,\s]+)\]\s*$", text)
        if not m:
            return text, []
        return text[: m.start()].strip(), re.findall(r"\d{3}", m.group(1))

    indicators, subfields = [], []
    for td in soup.find_all("td"):
        strong = td.find("strong")
        label = clean(strong.get_text()) if strong else ""
        if label in ("First Indicator", "Second Indicator") and not indicators_has(indicators, label):
            ls = lines(td)
            em = td.find("em")
            ind = {"position": label.split()[0], "name": clean(em.get_text()) if em else "",
                   "values": []}
            for line in ls[1:]:
                text, only = restrict(line)
                code, lab = split_code(text)
                if lab:
                    v = {"code": code, "label": lab, "description": ""}
                    if only:
                        v["only"] = only
                    ind["values"].append(v)
            indicators.append(ind)
        elif "$" in td.get_text() and not td.find("table"):
            for line in lines(td):
                text, only = restrict(line)
                sf = make_subfield(text)
                if sf and not any(s["code"] == sf["code"] for s in subfields):
                    if only:
                        sf["only"] = only
                    subfields.append(sf)
    return tags, indicators, subfields


def indicators_has(indicators, label):
    return any(i["position"] == label.split()[0] for i in indicators)


def apply_only(items: list[dict], tag: str) -> list[dict]:
    out = []
    for it in items:
        if "only" in it and tag not in it["only"]:
            continue
        out.append({k: v for k, v in it.items() if k != "only"})
    return out


# --------------------------------------------------------------------------- orchestration


def discover_tags(fmt: str, cfg: dict, refresh: bool) -> list[str]:
    tags = set()
    for page in cfg["index_pages"]:
        html = fetch(urljoin(LOC + fmt + "/", page), refresh)
        if not html:
            print(f"  ! index page missing: {page}", file=sys.stderr)
            continue
        soup = soup_of(html)
        for a in soup.find_all("a", href=True):
            m = re.search(rf"{cfg['prefix']}(\d{{3}})\.html$", a["href"])
            if m:
                tags.add(m.group(1))
        for strong in soup.find_all(["strong", "li", "div"]):
            m = re.match(r"\s*(\d{3})\s*-\s*[A-Z]", strong.get_text())
            if m:
                tags.add(m.group(1))
    return sorted(tags)


def scrape_field(fmt: str, cfg: dict, tag: str, refresh: bool) -> dict | None:
    url = f"{LOC}{fmt}/concise/{cfg['prefix']}{tag}.html"
    html = fetch(url, refresh)
    if not html:
        return None
    field = parse_field_page(html)
    if "OBSOLETE" in field["name"].upper() or field["repeatable"] is None:
        return None
    field = {"tag": tag, **field, "url": url}

    if any("group" in p for p in field["positions"]):
        groups: dict[str, list] = {}
        for p in field.pop("positions"):
            groups.setdefault(p.pop("group", ""), []).append(p)
        field["positions"] = groups.pop("", [])
        field["variants"] = [{"code": "", "name": g, "definition": "", "positions": ps, "url": url}
                             for g, ps in groups.items()]

    # 007 / 008: per-material sub-pages (bd008b.html, bd007m.html, ...)
    soup = soup_of(html)
    variant_pages = sorted({a["href"] for a in soup.find_all("a", href=True)
                            if re.fullmatch(rf"{cfg['prefix']}{tag}[a-z]\.html", a["href"])})
    if variant_pages:
        field["variants"] = []
        for vp in variant_pages:
            vurl = urljoin(url, vp)
            vhtml = fetch(vurl, refresh)
            if not vhtml:
                continue
            v = parse_field_page(vhtml)
            field["variants"].append({
                "code": vp[len(cfg["prefix"]) + 3:-5],
                "name": v["name"],
                "definition": v["definition"],
                "positions": v["positions"],
                "url": vurl,
            })
    return field


def scrape_format(fmt: str, refresh: bool, workers: int) -> dict:
    cfg = FORMATS[fmt]
    print(f"\n== {fmt}")
    tags = discover_tags(fmt, cfg, refresh)
    print(f"  {len(tags)} candidate tags")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda t: scrape_field(fmt, cfg, t, refresh), tags))
    fields = {f["tag"]: f for f in results if f}

    # Leader
    lurl = urljoin(LOC + fmt + "/", cfg["leader"])
    lhtml = fetch(lurl, refresh)
    if lhtml:
        ldr = parse_field_page(lhtml)
        ldr["name"] = "Leader"
        ldr["repeatable"] = False
        fields["LDR"] = {"tag": "LDR", **ldr, "url": lurl}

    # Shared indicator/subfield definitions for holdings field groups
    for page in cfg["group_pages"]:
        html = fetch(urljoin(LOC + fmt + "/", page), refresh)
        if not html:
            continue
        gtags, inds, sfs = parse_group_page(html)
        for t in gtags:
            f = fields.get(t)
            if not f:
                continue
            if not f["indicators"]:
                f["indicators"] = [{**i, "values": apply_only(i["values"], t)} for i in inds]
            if not f["subfields"]:
                f["subfields"] = apply_only(sfs, t)
            f.setdefault("see_also", urljoin(LOC + fmt + "/", page))

    for tag, words in ALIASES.get(fmt, {}).items():
        if tag in fields:
            fields[tag]["aliases"] = words

    order = lambda k: (k != "LDR", k)
    return {k: fields[k] for k in sorted(fields, key=order)}


def report(fmt: str, fields: dict) -> None:
    """Print anything that looks incomplete so it can be checked by hand."""
    control = {"LDR", "001", "003", "004", "005", "006", "007", "008"}
    problems = []
    for tag, f in fields.items():
        if not f["definition"]:
            problems.append(f"{tag}: no definition")
        if tag in control:
            if tag in ("LDR", "008") and not (f["positions"] or f.get("variants")):
                problems.append(f"{tag}: no character positions")
            continue
        if not f["subfields"]:
            problems.append(f"{tag}: no subfields")
        if len(f["indicators"]) != 2:
            problems.append(f"{tag}: {len(f['indicators'])} indicators")
    n_sub = sum(len(f["subfields"]) for f in fields.values())
    print(f"  {len(fields)} fields, {n_sub} subfields")
    for p in problems:
        print(f"  ? {p}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("formats", nargs="*", default=list(FORMATS), choices=list(FORMATS))
    ap.add_argument("--refresh", action="store_true", help="ignore the page cache")
    ap.add_argument("--workers", type=int, default=4, help="parallel downloads (default 4)")
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for fmt in args.formats:
        fields = scrape_format(fmt, args.refresh, args.workers)
        report(fmt, fields)
        out = {
            "meta": {
                "format": fmt,
                "source": f"{LOC}{fmt}/",
                "scraped": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            "fields": fields,
        }
        path = DATA_DIR / f"{fmt}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
