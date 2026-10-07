"""
Validation and normalization helpers for applicant CSV rows.
Ensures data integrity prior to database insertion and identifies invalid rows.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_COLUMNS = [
    "user_id",
    "email",
    "monthly_income",
    "credit_score",
    "employment_status",
    "age",
]

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EMPLOYMENT_MAP = {
    "salaried": "salaried",
    "self-employed": "self_employed",
    "self employed": "self_employed",
    "self_employed": "self_employed",
    "business": "self_employed",
    "freelancer": "self_employed",
    "freelance": "self_employed",
    "unemployed": "unemployed",
    "student": "student",
    "retired": "other",
    "other": "other",
}


def check_header(fieldnames: Optional[List[str]]) -> Tuple[bool, Optional[str]]:
    """
    Validate that all required columns are present in the CSV header.
    Returns (True, None) if valid, or (False, error_message) if columns are missing.
    """
    if not fieldnames:
        return False, "CSV header is empty or missing."

    normalized_fields = {col.strip() for col in fieldnames if col}
    missing_columns = [col for col in REQUIRED_COLUMNS if col not in normalized_fields]

    if missing_columns:
        return False, f"Missing required columns: {', '.join(missing_columns)}"

    return True, None


def validate_row(row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Validate and clean an individual CSV row.
    Returns (clean_row_dict, None) on success, or (None, rejection_reason) on failure.
    """
    cleaned: Dict[str, Any] = {}

    # 1. Check required fields and trim whitespace
    for col in REQUIRED_COLUMNS:
        raw_val = row.get(col)
        if raw_val is None or str(raw_val).strip() == "":
            return None, f"Missing required field '{col}'"
        cleaned[col] = str(raw_val).strip()

    # 2. Validate email format
    email = cleaned["email"]
    if not EMAIL_REGEX.match(email):
        return None, "Invalid email address format"

    # 3. Validate monthly_income (numeric >= 0)
    try:
        income = Decimal(cleaned["monthly_income"])
        if income < 0:
            return None, "monthly_income must be non-negative"
        cleaned["monthly_income"] = income
    except (InvalidOperation, ValueError):
        return None, "monthly_income must be a valid number"

    # 4. Validate credit_score (integer between 300 and 900)
    try:
        credit = int(cleaned["credit_score"])
        if not (300 <= credit <= 900):
            return None, "credit_score must be an integer between 300 and 900"
        cleaned["credit_score"] = credit
    except ValueError:
        return None, "credit_score must be a valid integer"

    # 5. Validate age (integer between 18 and 100)
    try:
        age = int(cleaned["age"])
        if not (18 <= age <= 100):
            return None, "age must be an integer between 18 and 100"
        cleaned["age"] = age
    except ValueError:
        return None, "age must be a valid integer"

    # 6. Normalize employment_status
    raw_status = cleaned["employment_status"].lower()
    cleaned["employment_status"] = EMPLOYMENT_MAP.get(raw_status, "other")

    return cleaned, None
