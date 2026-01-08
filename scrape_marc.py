#!/usr/bin/env python3
"""
MARC 21 Bibliographic Field Scraper

Scrapes field definitions from Library of Congress MARC 21 documentation
and generates/updates marc.json with complete field and subfield data.
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.loc.gov/marc/bibliographic/"

# Field range pages to scrape
FIELD_RANGE_PAGES = [
    "bd00x.html",  # Control Fields (001-008)
    "bd01x09x.html",  # Numbers and Code Fields (010-088)
    "bd1xx.html",  # Main Entry Fields (100, 110, 111, 130)
    "bd20x24x.html",  # Title and Title-Related Fields (210-247)
    "bd25x28x.html",  # Edition, Imprint, etc. (250-270)
    "bd3xx.html",  # Physical Description, etc. (300-388)
    "bd4xx.html",  # Series Statement Fields (400-490)
    "bd5xx.html",  # Note Fields (500-588)
    "bd6xx.html",  # Subject Access Fields (600-688)
    "bd70x75x.html",  # Added Entry Fields (700-758)
    # "bd76x78x.html",  # Linking Entry Fields - SKIPPED: has grouped format, handled separately
    "bd80x83x.html",  # Series Added Entry Fields (800-830)
    "bd84188x.html",  # Holdings, Location, etc. (841-887)
]

# Manually defined linking entry fields (760-788)
# These have a different page structure and need special handling
LINKING_ENTRY_FIELDS = [
    ("760", "Main Series Entry", "R"),
    ("762", "Subseries Entry", "R"),
    ("765", "Original Language Entry", "R"),
    ("767", "Translation Entry", "R"),
    ("770", "Supplement/Special Issue Entry", "R"),
    ("772", "Supplement Parent Entry", "R"),
    ("773", "Host Item Entry", "R"),
    ("774", "Constituent Unit Entry", "R"),
    ("775", "Other Edition Entry", "R"),
    ("776", "Additional Physical Form Entry", "R"),
    ("777", "Issued With Entry", "R"),
    ("780", "Preceding Entry", "R"),
    ("785", "Succeeding Entry", "R"),
    ("786", "Data Source Entry", "R"),
    ("787", "Other Relationship Entry", "R"),
    ("788", "Parallel Description in Another Language of Cataloging", "R"),
]

# Manually defined field 222 (has different HTML structure requiring manual override)
FIELD_222_MANUAL = {
    "Key": "222",
    "Value": "Key Title (R)",
    "Details": {
        "definition": "Unique title for a continuing resource that is assigned in conjunction with an ISSN recorded in field 022 by national centers under the auspices of the ISSN Network.",
        "indicators": {
            "First - Undefined": ["# - Undefined"],
            "Second - Nonfiling characters": [
                "0 - No nonfiling characters",
                "1-9 - Number of nonfiling characters",
            ],
        },
        "subfields": {
            "a": {
                "description": "Key title",
                "extended": "",
                "repeatability": "NR",
            },
            "b": {
                "description": "Qualifying information",
                "extended": "Parenthetical information that qualifies the title to make it unique.",
                "repeatability": "NR",
            },
            "6": {
                "description": "Linkage",
                "extended": "See description of this subfield in Appendix A: Control Subfields.",
                "repeatability": "NR",
            },
            "8": {
                "description": "Field link and sequence number",
                "extended": "See description of this subfield in Appendix A: Control Subfields.",
                "repeatability": "R",
            },
        },
        "examples": [
            "#0$aViva$b(New York)",
            "#0$aCauses of death",
            "#4$aDer Öffentliche Dienst$b(Köln)",
            "#0$aJournal of polymer science. Part B. Polymer letters",
            "#0$aEconomic education bulletin$b(Great Barrington)",
        ],
    },
}


def fetch_page(url: str) -> BeautifulSoup:
    """Fetch and parse a web page."""
    print(f"Fetching {url}...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.content, "html.parser")


def extract_field_links(soup: BeautifulSoup) -> List[Tuple[str, str, str]]:
    """
    Extract field numbers and their descriptions from a field range index page.
    Returns list of (field_number, description, repeatability) tuples.
    """
    fields = []

    # Look for patterns like "020 - International Standard Book Number (R)"
    # These appear as text in the page, often in <strong> tags or plain text
    text_content = soup.get_text()

    # Pattern: 3 digits, space/dash, description, repeatability in parens
    pattern = r"(\d{3})\s*[-–]\s*([^(]+?)\s*\(([RN]{1,2})\)"

    for match in re.finditer(pattern, text_content):
        field_num = match.group(1)
        description = match.group(2).strip()
        repeatability = match.group(3).strip()

        # Skip obsolete fields
        if "[OBSOLETE]" in description.upper() or "OBSOLETE" in description.upper():
            continue

        fields.append((field_num, description, repeatability))

    return fields


def extract_detailed_field_info(field_num: str) -> dict:
    """
    Fetch detailed field information from the concise LOC page.
    Returns dict with definition, indicators, subfields, and examples.
    """
    concise_url = urljoin(BASE_URL, f"concise/bd{field_num}.html")

    try:
        soup = fetch_page(concise_url)
        field_info = {
            "definition": "",
            "indicators": {},
            "subfields": {},
            "examples": [],
        }

        # Extract definition
        definition_div = soup.find("div", class_="definition")
        if definition_div:
            # Get text from paragraph, stripping extra whitespace
            p_tag = definition_div.find("p")
            if p_tag:
                field_info["definition"] = " ".join(p_tag.get_text().split())

        # Extract indicators
        indicators_div = soup.find("div", class_="indicators")
        if indicators_div:
            dts = indicators_div.find_all("dt")
            for dt in dts:
                indicator_name = dt.get_text().strip()
                # Get all dd siblings until next dt
                values = []
                for sibling in dt.find_next_siblings():
                    if sibling.name == "dt":
                        break
                    if sibling.name == "dd":
                        value_text = sibling.get_text().strip()
                        # Clean up excessive whitespace
                        value_text = " ".join(value_text.split())
                        values.append(value_text)
                if values:
                    field_info["indicators"][indicator_name] = values

        # Extract subfields with detailed descriptions
        subfields_div = soup.find("div", class_="subfields")
        if subfields_div:
            dls = subfields_div.find_all("dl")
            for dl in dls:
                dt = dl.find("dt")
                if not dt:
                    continue

                # Extract subfield code and description from dt
                dt_text = dt.get_text()
                # Pattern: $a - Description (R)
                pattern = r"\$([a-z0-9])\s*[-–]\s*([^(]+?)\s*\(([RN]{1,2})\)"
                match = re.search(pattern, dt_text, re.IGNORECASE)

                if match:
                    subfield_code = match.group(1).lower()
                    short_desc = match.group(2).strip()
                    repeatability = match.group(3).strip()

                    # Get extended description from dd if present
                    extended_desc = ""
                    dd = dl.find("dd")
                    if dd:
                        extended_desc = " ".join(dd.get_text().split())

                    field_info["subfields"][subfield_code] = {
                        "description": short_desc,
                        "extended": extended_desc,
                        "repeatability": repeatability,
                    }

        # Extract examples
        examples_table = soup.find("table", class_="examples")
        if examples_table:
            rows = examples_table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    # First cell is field tag, rest is the example
                    example_text = " ".join(
                        cell.get_text().strip() for cell in cells[1:]
                    )
                    # Clean up excessive whitespace
                    example_text = " ".join(example_text.split())
                    if example_text:
                        field_info["examples"].append(example_text)

        return field_info

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(
                f"  No concise page found for field {field_num} (may be control field)"
            )
            return None
        raise
    except Exception as e:
        print(f"  Error extracting detailed info for {field_num}: {e}")
        return None


def extract_subfields_from_concise(field_num: str) -> List[Tuple[str, str, str]]:
    """
    Fetch the concise version of a field page and extract subfield definitions.
    Returns list of (subfield_code, description, repeatability) tuples.
    (Kept for backward compatibility with basic mode)
    """
    concise_url = urljoin(BASE_URL, f"concise/bd{field_num}.html")

    try:
        soup = fetch_page(concise_url)
        subfields = []

        # Look for subfield patterns: $a - Description (R) or **$a - Description (R)**
        text_content = soup.get_text()

        # Pattern: $letter/digit - description (R/NR)
        pattern = r"\$([a-z0-9])\s*[-–]\s*([^(]+?)\s*\(([RN]{1,2})\)"

        for match in re.finditer(pattern, text_content, re.IGNORECASE):
            subfield_code = match.group(1).lower()
            description = match.group(2).strip()
            repeatability = match.group(3).strip()

            # Clean up description
            description = re.sub(r"\s+", " ", description)

            # Skip if description is too short or looks malformed
            if len(description) < 3:
                continue

            subfields.append((subfield_code, description, repeatability))

        return subfields

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(
                f"  No concise page found for field {field_num} (may be control field)"
            )
            return []
        raise
    except Exception as e:
        print(f"  Error extracting subfields for {field_num}: {e}")
        return []


def scrape_all_fields() -> Dict[str, dict]:
    """
    Scrape all MARC fields and subfields from LOC documentation.
    Returns dictionary in marc.json format with detailed information.
    """
    all_data = {}
    timestamp = datetime.now(timezone.utc).isoformat()

    # Track all field numbers we've seen
    seen_fields = set()

    # Process each field range page
    for page in FIELD_RANGE_PAGES:
        print(f"\nProcessing {page}...")
        url = urljoin(BASE_URL, page)
        soup = fetch_page(url)

        # Extract field definitions from index page
        fields = extract_field_links(soup)
        print(f"  Found {len(fields)} fields")

        for field_num, description, repeatability in fields:
            if field_num in seen_fields:
                continue
            seen_fields.add(field_num)

            # Skip field 222 - has manual override due to different HTML structure
            if field_num == "222":
                continue

            # Extract detailed information from the concise page
            detailed_info = extract_detailed_field_info(field_num)

            # Add the main field entry
            field_key = field_num
            # Special case: add (ISBN) to field 020 for better searchability
            if field_num == "020":
                field_value = f"{description} (ISBN) ({repeatability})"
            else:
                field_value = f"{description} ({repeatability})"

            field_entry = {
                "Key": field_key,
                "Value": field_value,
                "Created": timestamp,
            }

            # Add detailed info if available
            if detailed_info:
                field_entry["Details"] = detailed_info

            all_data[field_key] = field_entry
            print(f"  Added: {field_key} - {field_value}")

            # Extract subfields (simple format for backward compatibility)
            if detailed_info and detailed_info.get("subfields"):
                for subfield_code, subfield_info in detailed_info["subfields"].items():
                    subfield_key = f"{field_num}{subfield_code}"
                    subfield_value = f"{subfield_info['description']} ({subfield_info['repeatability']})"
                    all_data[subfield_key] = {
                        "Key": subfield_key,
                        "Value": subfield_value,
                        "Created": timestamp,
                    }
                    print(f"    Added: {subfield_key} - {subfield_value}")
            else:
                # Fallback to old method if detailed extraction failed
                subfields = extract_subfields_from_concise(field_num)
                for subfield_code, subfield_desc, subfield_repeat in subfields:
                    subfield_key = f"{field_num}{subfield_code}"
                    subfield_value = f"{subfield_desc} ({subfield_repeat})"
                    all_data[subfield_key] = {
                        "Key": subfield_key,
                        "Value": subfield_value,
                        "Created": timestamp,
                    }
                    print(f"    Added: {subfield_key} - {subfield_value}")

    # Add manually defined field 222 (different HTML structure)
    print("\nAdding manually defined field 222...")
    timestamp = datetime.now(timezone.utc).isoformat()
    field_222 = FIELD_222_MANUAL.copy()
    field_222["Created"] = timestamp
    all_data["222"] = field_222
    print(f"  Added: 222 - Key Title (R)")

    # Add subfields for field 222
    for subfield_code, subfield_info in FIELD_222_MANUAL["Details"][
        "subfields"
    ].items():
        subfield_key = f"222{subfield_code}"
        subfield_value = (
            f"{subfield_info['description']} ({subfield_info['repeatability']})"
        )
        all_data[subfield_key] = {
            "Key": subfield_key,
            "Value": subfield_value,
            "Created": timestamp,
        }
        print(f"    Added: {subfield_key} - {subfield_value}")

    # Process manually defined linking entry fields (760-788)
    print("\nProcessing manually defined linking entry fields (760-788)...")
    for field_num, description, repeatability in LINKING_ENTRY_FIELDS:
        if field_num in seen_fields:
            continue
        seen_fields.add(field_num)

        # Extract detailed information from the concise page
        detailed_info = extract_detailed_field_info(field_num)

        # Add the main field entry
        field_key = field_num
        field_value = f"{description} ({repeatability})"

        field_entry = {
            "Key": field_key,
            "Value": field_value,
            "Created": timestamp,
        }

        # Add detailed info if available
        if detailed_info:
            field_entry["Details"] = detailed_info

        all_data[field_key] = field_entry
        print(f"  Added: {field_key} - {field_value}")

        # Extract subfields
        if detailed_info and detailed_info.get("subfields"):
            for subfield_code, subfield_info in detailed_info["subfields"].items():
                subfield_key = f"{field_num}{subfield_code}"
                subfield_value = (
                    f"{subfield_info['description']} ({subfield_info['repeatability']})"
                )
                all_data[subfield_key] = {
                    "Key": subfield_key,
                    "Value": subfield_value,
                    "Created": timestamp,
                }
                print(f"    Added: {subfield_key} - {subfield_value}")
        else:
            # Fallback to old method if detailed extraction failed
            subfields = extract_subfields_from_concise(field_num)
            for subfield_code, subfield_desc, subfield_repeat in subfields:
                subfield_key = f"{field_num}{subfield_code}"
                subfield_value = f"{subfield_desc} ({subfield_repeat})"
                all_data[subfield_key] = {
                    "Key": subfield_key,
                    "Value": subfield_value,
                    "Created": timestamp,
                }
                print(f"    Added: {subfield_key} - {subfield_value}")

    return all_data


def backup_existing_file(filepath: Path):
    """Create a backup of the existing file."""
    if filepath.exists():
        backup_path = filepath.with_suffix(".json.backup")
        print(f"\nBacking up existing file to {backup_path}")
        shutil.copy2(filepath, backup_path)


def main():
    """Main scraper execution."""
    print("MARC 21 Field Scraper")
    print("=" * 50)

    verbose_file = Path(__file__).parent / "marc-verbose.json"
    simple_file = Path(__file__).parent / "marc.json"

    # Backup existing files
    backup_existing_file(verbose_file)
    backup_existing_file(simple_file)

    # Scrape all fields
    print("\nStarting scrape...")
    all_data = scrape_all_fields()

    # Sort by key for consistent ordering
    sorted_data = dict(sorted(all_data.items()))

    # Write verbose file (with Details)
    print(f"\nWriting {len(sorted_data)} entries to {verbose_file}")
    with open(verbose_file, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)

    # Create simple version (without Details)
    simple_data = {}
    for key, entry in sorted_data.items():
        simple_data[key] = {
            "Key": entry["Key"],
            "Value": entry["Value"],
            "Created": entry["Created"],
        }

    # Write simple file
    print(f"Writing {len(simple_data)} entries to {simple_file}")
    with open(simple_file, "w", encoding="utf-8") as f:
        json.dump(simple_data, f, indent=2, ensure_ascii=False)

    print("\nDone!")
    print(f"Total entries: {len(sorted_data)}")

    # Count fields vs subfields
    fields = sum(1 for k in sorted_data.keys() if len(k) == 3)
    subfields = len(sorted_data) - fields
    print(f"Fields: {fields}, Subfields: {subfields}")


if __name__ == "__main__":
    main()
