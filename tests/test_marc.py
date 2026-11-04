"""Tests for the marc CLI and the scraped data files.

    uv run --extra dev pytest
"""

import pytest

from marc_cli.main import load, run, search

CONTROL = {"LDR", "001", "003", "004", "005", "006", "007", "008"}


def out(capsys, query, fmt="bibliographic", verbose=False):
    code = run(query, fmt, verbose)
    return code, capsys.readouterr().out


# --------------------------------------------------------------------------- data


@pytest.mark.parametrize("fmt", ["bibliographic", "holdings"])
def test_data_fields_complete(fmt):
    fields = load(fmt)
    assert "LDR" in fields
    for tag, f in fields.items():
        assert f["name"], tag
        assert f["repeatable"] in (True, False), tag
        if tag in CONTROL:
            continue
        assert f["subfields"], f"{fmt} {tag} has no subfields"
        assert len(f["indicators"]) == 2, f"{fmt} {tag} indicators"


def test_bibliographic_has_known_fields():
    fields = load("bibliographic")
    # 260 was missing from the old scraper (parentheses in its name)
    for tag in ("020", "040", "245", "260", "264", "300", "650", "760", "856"):
        assert tag in fields
    assert {s["code"] for s in fields["040"]["subfields"]} >= set("abcde")


def test_holdings_group_fields_filled_from_general_pages():
    h = load("holdings")
    assert {s["code"] for s in h["863"]["subfields"]} >= set("abcijz8")
    # [863/864]-only values must not leak into 865
    assert [v["code"] for v in h["865"]["indicators"][1]["values"]] == ["#", "1", "3"]
    assert "v" in {s["code"] for s in h["865"]["subfields"]}
    assert "v" not in {s["code"] for s in h["863"]["subfields"]}


def test_fixed_fields_have_positions():
    b = load("bibliographic")
    assert b["LDR"]["positions"]
    assert {v["name"] for v in b["008"]["variants"]} >= {"All Materials", "Books", "Music"}
    assert b["006"]["variants"] and b["007"]["variants"]


# --------------------------------------------------------------------------- CLI


def test_field_lookup(capsys):
    code, text = out(capsys, "245")
    assert code == 0
    assert "Title Statement" in text and "245$a" in text


@pytest.mark.parametrize("q", ["245a", "245$a", "245 a"])
def test_subfield_lookup(capsys, q):
    code, text = out(capsys, q)
    assert code == 0 and "245$a" in text and "245$b" not in text


def test_verbose_subfield_prints_something(capsys):
    code, text = out(capsys, "040b", verbose=True)
    assert code == 0 and "Language of cataloging" in text and "Code List" in text


def test_position_lookup(capsys):
    code, text = out(capsys, "008/23")
    assert code == 0 and "Form of item" in text and "Books" in text
    code, text = out(capsys, "ldr/06")
    assert code == 0 and "Type of record" in text and "Language material" in text


def test_position_inside_range(capsys):
    code, text = out(capsys, "008/09")
    assert code == 0 and "Date 1" in text


def test_pattern(capsys):
    code, text = out(capsys, "24x")
    assert code == 0 and "245" in text and "250" not in text
    code, text = out(capsys, "1xx")
    assert "100" in text and "130" in text


def test_holdings_fallback_and_flag(capsys):
    code, text = out(capsys, "863")
    assert code == 0 and "Holdings format" in text
    code, text = out(capsys, "852", fmt="holdings")
    assert code == 0 and "Holdings format" not in text and "852$h" in text


def test_keyword_ignores_repeatability_marker():
    # the old CLI matched "(R)"/"(NR)" in every entry
    for q in ("r", "nr"):
        hits = search(q, "bibliographic", deep=False)
        # score 5 = matched a position's code value, which is shown alongside the position name
        assert hits and all(q in name.lower() for score, _, name, _ in hits if score != 5)


def test_keyword_alias_first():
    hits = search("isbn", "bibliographic", deep=False)
    assert hits[0][:3] == (0, "020", "International Standard Book Number")


def test_keyword_finds_positions_and_codes(capsys):
    code, text = out(capsys, "form of item")
    assert code == 0 and "008/23" in text and "Books" in text
    code, text = out(capsys, "braille")
    assert code == 0 and "f - Braille" in text


def test_unknown(capsys):
    assert out(capsys, "999")[0] == 1
    assert out(capsys, "245y")[0] == 1
