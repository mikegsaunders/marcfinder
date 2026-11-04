# marcfinder

CLI tool for looking up MARC 21 **Bibliographic** and **Holdings** field definitions.

## Installation

```bash
uv tool install marcfinder
```

This installs the `marc` command globally while keeping dependencies isolated.
To update later: `uv tool upgrade marcfinder`.

To run from a clone instead (for development):

```bash
git clone https://github.com/mikegsaunders/marcfinder.git
cd marcfinder
uv tool install -e .
```

## Usage

**Fields and subfields:**

```bash
marc 245        # Field 245 and all its subfields
marc 245a       # One subfield (245$a and "245 a" also work)
marc ldr        # Leader, with its character positions
```

**Character positions (Leader, 006, 007, 008):**

```bash
marc 008/23     # Form of item, for every material type that defines it
marc ldr/06     # Type of record, with all its codes
marc 008/07-10  # A range
```

**Browse fields by pattern:**

```bash
marc 5xx        # All 5XX note fields
marc 24x        # 240-249
marc 6          # Every field starting with 6
```

**Keyword search** (field, subfield and character-position names and codes, plus
common terms like ISBN, LCCN, Dewey):

```bash
marc isbn
marc place of publication
marc braille            # finds 007/01, 008/23 etc.
marc -v accessibility   # -v also searches definitions
```

**Holdings format:**

```bash
marc -h 852             # Holdings 852 Location
marc -h 8xx
marc -h -v 863          # Indicators, subfields and examples for 863
marc 863                # Holdings-only fields (841-878) are found without -h too
```

**Verbose mode** shows the definition, indicators (with explanations), subfield
descriptions, character positions, examples and a link to the LOC page:

```bash
marc -v 245
marc -v 040b
```

**Update marcfinder:**

```bash
marc --update   # or: marc -up
```

For a clone this runs `git pull`. For a PyPI install it prints the
`uv tool upgrade marcfinder` command to run.

Help is `marc --help` (`-h` is holdings).

Colour is turned off automatically when output is piped, or when `NO_COLOR` is set.

## Development

Data lives in `marc_cli/data/bibliographic.json` and `marc_cli/data/holdings.json`,
scraped from the Library of Congress concise format documentation.

```bash
uv run --extra dev python scrape_marc.py              # both formats
uv run --extra dev python scrape_marc.py holdings     # just one
uv run --extra dev python scrape_marc.py --refresh    # ignore the page cache
uv run --extra dev pytest
```

Downloaded pages are cached in `.cache/loc/`, so re-runs take seconds. The scraper
prints anything that looks incomplete (for example a field with no subfields) so
it can be checked by hand.

### Releasing to PyPI

1. Bump `version` in `pyproject.toml` and commit.
2. Tag and push: `git tag v0.2.1 && git push --tags`.
3. Create a GitHub release from the tag. The `publish` workflow builds and uploads it.

One-time setup: on PyPI, add a "trusted publisher" for this repo
(workflow `publish.yml`, environment `pypi`). No API token is needed.

## License

MIT. Field definitions are from the Library of Congress MARC 21 documentation.
