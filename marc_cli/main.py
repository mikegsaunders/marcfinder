#!/usr/bin/env python3
"""
marc-cli: Fast CLI tool for looking up MARC 21 bibliographic field definitions.

Usage:
    marc 020        # Look up field by code (shows field + all subfields)
    marc 245a       # Look up specific subfield
    marc isbn       # Search by keyword in descriptions
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from colorama import init, Fore, Style

# Initialize colorama for cross-platform color support
init(autoreset=True)


def load_marc_data() -> Dict[str, dict]:
    """Load MARC field data from marc.json."""
    data_file = Path(__file__).parent.parent / "marc.json"

    if not data_file.exists():
        print(f"{Fore.RED}Error: marc.json not found at {data_file}")
        print(f"{Fore.YELLOW}Run 'python scrape_marc.py' to generate the data file.")
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_verbose_data() -> Dict[str, dict]:
    """Load detailed MARC field data from marc-verbose.json."""
    data_file = Path(__file__).parent.parent / "marc-verbose.json"

    if not data_file.exists():
        print(f"{Fore.RED}Error: marc-verbose.json not found at {data_file}")
        print(
            f"{Fore.YELLOW}Run 'python scrape_marc.py' to generate the verbose data file."
        )
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        return json.load(f)


def is_code_query(query: str) -> bool:
    """Determine if query is a field code (starts with digit) or keyword (starts with letter)."""
    return query and query[0].isdigit()


def search_by_code(data: Dict[str, dict], code: str) -> List[Tuple[str, dict]]:
    """
    Search for fields/subfields by code prefix.
    Returns list of (key, entry) tuples matching the code.
    """
    code_lower = code.lower()
    matches = []

    for key, entry in data.items():
        if key.lower().startswith(code_lower):
            matches.append((key, entry))

    # Sort by:
    # 1. Key length (exact match first - field before subfields)
    # 2. For subfields (len > 3): alphabetic subfields (a-z) before numeric (0-9)
    # 3. Then alphabetically within each group
    def sort_key(item):
        key = item[0]
        if len(key) == 3:
            # Field code - comes first
            return (0, key)
        else:
            # Subfield - separate alphabetic from numeric
            subfield_char = key[3]
            if subfield_char.isalpha():
                return (1, key)  # Alphabetic subfields
            else:
                return (2, key)  # Numeric subfields

    matches.sort(key=sort_key)

    return matches


def search_by_keyword(
    data: Dict[str, dict], keyword: str
) -> List[Tuple[str, dict, bool]]:
    """
    Search for fields/subfields by keyword in description.
    Returns list of (key, entry, is_exact_match) tuples.
    """
    keyword_lower = keyword.lower()
    matches = []

    for key, entry in data.items():
        value_lower = entry["Value"].lower()

        # Check for exact word match vs partial match
        # Split by common delimiters and check if keyword matches a whole word
        words = (
            value_lower.replace("-", " ")
            .replace("/", " ")
            .replace(",", " ")
            .replace("(", " ")
            .replace(")", " ")
            .split()
        )
        is_exact = keyword_lower in words

        if keyword_lower in value_lower:
            matches.append((key, entry, is_exact))

    # Sort:
    # 1. Exact word matches first (is_exact=True comes before is_exact=False)
    # 2. Within same exactness, fields (3 chars) before subfields (4+ chars)
    # 3. Then by length (shorter first)
    # 4. Then alphabetically
    matches.sort(key=lambda x: (not x[2], len(x[0]) > 3, len(x[0]), x[0]))

    return [(k, e) for k, e, _ in matches]


def format_output(key: str, value: str) -> str:
    """Format a single entry with colors."""
    # Determine if it's a field (3 digits) or subfield (3+ chars)
    is_field = len(key) == 3

    # Format key with $ separator for subfields
    if is_field:
        display_key = f"{Fore.CYAN}{Style.BRIGHT}{key}"
        # Add extra spaces to align with subfields that have "$x"
        spacing = "    "
    else:
        # For subfields, color the field part and the $ + subfield differently
        # e.g., "020$a" -> blue "020" + magenta "$a"
        field_part = f"{Fore.BLUE}{key[:3]}"
        subfield_part = f"{Fore.MAGENTA}${key[3:]}"
        display_key = f"{field_part}{subfield_part}"
        spacing = "  "

    # Extract repeatability indicator
    repeatability = ""
    if value.endswith("(R)"):
        repeatability = f"{Fore.GREEN}(R){Style.RESET_ALL}"
        value = value[:-3].strip()
    elif value.endswith("(NR)"):
        repeatability = f"{Fore.YELLOW}(NR){Style.RESET_ALL}"
        value = value[:-4].strip()

    return f"{display_key}{Style.RESET_ALL}{spacing}{value} {repeatability}"


def format_verbose_output(key: str, entry: dict) -> str:
    """Format detailed field information for verbose mode."""
    output = []

    # Only show verbose details for 3-digit field codes (not subfields)
    if len(key) != 3 or "Details" not in entry:
        # Fall back to normal format for subfields or if no details
        return format_output(key, entry["Value"])

    details = entry["Details"]

    # Header with field code and title
    output.append(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 70}")
    output.append(f"{Fore.CYAN}{Style.BRIGHT}{key} - {entry['Value']}")
    output.append(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 70}{Style.RESET_ALL}\n")

    # Definition
    if details.get("definition"):
        output.append(f"{Fore.YELLOW}{Style.BRIGHT}Definition:{Style.RESET_ALL}")
        output.append(f"  {details['definition']}\n")

    # Indicators
    if details.get("indicators"):
        output.append(f"{Fore.YELLOW}{Style.BRIGHT}Indicators:{Style.RESET_ALL}")
        for indicator_name, values in details["indicators"].items():
            output.append(f"  {Fore.MAGENTA}{indicator_name}{Style.RESET_ALL}")
            for value in values:
                output.append(f"    {value}")
        output.append("")

    # Subfields
    if details.get("subfields"):
        output.append(f"{Fore.YELLOW}{Style.BRIGHT}Subfields:{Style.RESET_ALL}")
        # Sort subfields: alphabetic first, then numeric
        subfield_items = list(details["subfields"].items())
        subfield_items.sort(key=lambda x: (x[0].isdigit(), x[0]))

        for subfield_code, subfield_info in subfield_items:
            repeat_color = (
                Fore.GREEN if subfield_info["repeatability"] == "R" else Fore.YELLOW
            )
            output.append(
                f"  {Fore.MAGENTA}${subfield_code}{Style.RESET_ALL} - {subfield_info['description']} {repeat_color}({subfield_info['repeatability']}){Style.RESET_ALL}"
            )
            if subfield_info.get("extended"):
                output.append(
                    f"      {Fore.WHITE}{Style.DIM}{subfield_info['extended']}{Style.RESET_ALL}"
                )
        output.append("")

    # Examples (show first 5)
    if details.get("examples"):
        output.append(f"{Fore.YELLOW}{Style.BRIGHT}Examples:{Style.RESET_ALL}")
        for i, example in enumerate(details["examples"][:5], 1):
            output.append(f"  {Fore.GREEN}{i}.{Style.RESET_ALL} {example}")
        output.append("")

    return "\n".join(output)


def display_results(matches: List[Tuple[str, dict]], verbose: bool = False):
    """Display search results with formatting."""
    if not matches:
        print(f"{Fore.YELLOW}No matches found.")
        return

    if verbose:
        # In verbose mode, only show fields (3 digits), not subfields
        # Subfields are already included in the verbose field display
        for key, entry in matches:
            if len(key) == 3:  # Only show fields, skip subfields
                print(format_verbose_output(key, entry))
    else:
        for key, entry in matches:
            print(format_output(key, entry["Value"]))


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Look up MARC 21 bibliographic field definitions",
        epilog="Examples:\n  marc 020      Look up ISBN field\n  marc 245a     Look up title subfield\n  marc isbn     Search for ISBN-related fields\n  marc -v 245   Show detailed information for field 245",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query", help="Field code (e.g., 020, 245a) or keyword to search for"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed field information (definition, indicators, examples)",
    )

    args = parser.parse_args()

    # Load data (verbose or regular)
    if args.verbose:
        data = load_verbose_data()
    else:
        data = load_marc_data()

    # Determine query type and search
    query = args.query

    if is_code_query(query):
        # Code lookup
        matches = search_by_code(data, query)
        if matches:
            display_results(matches, verbose=args.verbose)
        else:
            print(f"{Fore.YELLOW}No field found matching code: {Fore.WHITE}{query}")
    else:
        # Keyword search - always use simple format (verbose produces too much output)
        if args.verbose:
            print(
                f"{Fore.YELLOW}Note: Verbose mode is not available for keyword searches.\n"
            )
        matches = search_by_keyword(data, query)
        if matches:
            if len(matches) > 1:
                print(f"{Fore.GREEN}Found {len(matches)} matches:\n")
            display_results(matches, verbose=False)  # Always False for keyword searches
        else:
            print(f"{Fore.YELLOW}No fields found matching keyword: {Fore.WHITE}{query}")


if __name__ == "__main__":
    main()
