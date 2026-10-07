#!/usr/bin/env python3
"""
Local CSV validation and parsing dry-run script.
Runs header verification and row validation on a local CSV file without
requiring AWS or database connections. Useful for local data verification.

Usage:
    python scripts/run_process_csv_local.py [path_to_csv]
"""

import csv
import os
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.validators import check_header, validate_row


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "sample_users.csv")

    if not os.path.isfile(csv_path):
        print(f"Error: CSV file not found at '{csv_path}'")
        sys.exit(1)

    print(f"--- Dry Run CSV Validation: {csv_path} ---")

    total_rows = 0
    valid_rows = 0
    rejected_rows = 0
    rejection_reasons = []

    with open(csv_path, mode="r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)

        # 1. Verify Header
        is_valid_header, header_error = check_header(reader.fieldnames)
        if not is_valid_header:
            print(f"FAILED: Header validation failed: {header_error}")
            sys.exit(1)

        print(f"Header validation PASSED. Detected columns: {reader.fieldnames}")

        # 2. Iterate and Validate Rows
        for row in reader:
            total_rows += 1
            clean_row, error_reason = validate_row(row)

            if clean_row is not None:
                valid_rows += 1
            else:
                rejected_rows += 1
                if len(rejection_reasons) < 5:
                    user_id = row.get("user_id", f"row_{total_rows}")
                    rejection_reasons.append(f"Row {total_rows} ({user_id}): {error_reason}")

    print("\n--- Validation Summary ---")
    print(f"Total Rows Processed : {total_rows:,}")
    print(f"Valid Rows (Accepted): {valid_rows:,}")
    print(f"Rejected Rows        : {rejected_rows:,}")

    if rejection_reasons:
        print("\n--- Sample Rejection Reasons (First 5) ---")
        for reason in rejection_reasons:
            print(f"  • {reason}")
    else:
        print("\nAll processed rows satisfied validation constraints!")


if __name__ == "__main__":
    main()
