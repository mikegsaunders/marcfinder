# marcfinder

CLI tool for looking up MARC 21 bibliographic field definitions.

## Installation

```bash
# Clone the repository
git clone https://github.com/mikegsaunders/marcfinder.git
cd marcfinder

# Install with pipx (creates isolated environment)
pipx install -e .
```

This installs the `marc` command globally while keeping dependencies isolated.

If you don't have pipx:

```bash
pip install pipx
pipx ensurepath
```

Then restart your terminal and run the installation command above.

## Usage

**Look up by field code:**

```bash
marc 020        # Shows ISBN field and all subfields (020a, 020c, etc.)
marc 245a       # Shows specific subfield
marc 100        # Shows personal name field and subfields
```

**Search by keyword:**

```bash
marc isbn       # Searches for "isbn" in descriptions
marc title      # Searches for "title" in descriptions
```

**Verbose mode (detailed information):**

```bash
marc -v 245     # Shows full definition, indicators, subfield descriptions, and examples
marc -v 020     # Shows complete field documentation from LOC
```

The tool automatically detects:

- If your query starts with a digit, it's treated as a field code lookup
- If your query starts with a letter, it's treated as a keyword search

All searches are case-insensitive.

## Development

To scrape/update MARC field data from Library of Congress:

```bash
pip install -e ".[dev]"
python scrape_marc.py
```

This will backup the existing `marc-verbose.json` and generate a new one with detailed field information including definitions, indicators, extended subfield descriptions, and examples.

The scraper creates:

- `marc.json` - Basic field and subfield definitions (for normal mode)
- `marc-verbose.json` - Detailed field documentation (for verbose mode with `-v` flag)
