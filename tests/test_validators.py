"""
Unit tests for applicant CSV validators and normalizers.
Covers header validation, required fields, data formats, and employment mapping.
"""

from decimal import Decimal
import pytest
from src.common.validators import check_header, validate_row


def test_check_header_valid():
    """Verify that headers containing all required columns pass validation."""
    fieldnames = ["user_id", "email", "monthly_income", "credit_score", "employment_status", "age"]
    is_valid, error = check_header(fieldnames)
    assert is_valid is True
    assert error is None


def test_check_header_with_extra_columns():
    """Verify that headers with extra columns (e.g. 'name') still pass validation."""
    fieldnames = ["user_id", "name", "email", "monthly_income", "credit_score", "employment_status", "age"]
    is_valid, error = check_header(fieldnames)
    assert is_valid is True
    assert error is None


def test_check_header_missing_columns():
    """Verify that missing required columns return False with an informative error."""
    fieldnames = ["user_id", "email", "monthly_income"]
    is_valid, error = check_header(fieldnames)
    assert is_valid is False
    assert "Missing required columns" in error
    assert "credit_score" in error


def test_check_header_empty():
    """Verify that an empty or None header fails validation."""
    is_valid_none, _ = check_header(None)
    assert is_valid_none is False

    is_valid_empty, _ = check_header([])
    assert is_valid_empty is False


def test_validate_row_valid():
    """Verify a completely valid row cleans properly and returns Decimal income."""
    raw_row = {
        "user_id": "usr-100",
        "email": "applicant@example.com",
        "monthly_income": "55000.50",
        "credit_score": "750",
        "employment_status": "salaried",
        "age": "32",
    }
    clean_row, error = validate_row(raw_row)
    assert error is None
    assert clean_row is not None
    assert clean_row["user_id"] == "usr-100"
    assert clean_row["email"] == "applicant@example.com"
    assert clean_row["monthly_income"] == Decimal("55000.50")
    assert clean_row["credit_score"] == 750
    assert clean_row["employment_status"] == "salaried"
    assert clean_row["age"] == 32


def test_validate_row_whitespace_trimming():
    """Verify leading and trailing whitespace is stripped from all fields."""
    raw_row = {
        "user_id": "  usr-200  ",
        "email": "  user@domain.com  ",
        "monthly_income": "  40000  ",
        "credit_score": " 700 ",
        "employment_status": "  salaried  ",
        "age": " 28 ",
    }
    clean_row, error = validate_row(raw_row)
    assert error is None
    assert clean_row is not None
    assert clean_row["user_id"] == "usr-200"
    assert clean_row["email"] == "user@domain.com"


def test_validate_row_missing_field():
    """Verify missing required column fails validation."""
    raw_row = {
        "user_id": "usr-300",
        "monthly_income": "50000",
        "credit_score": "700",
        "employment_status": "salaried",
        "age": "30",
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "Missing required field 'email'" in error


def test_validate_row_empty_field():
    """Verify whitespace-only value fails validation as missing."""
    raw_row = {
        "user_id": "usr-400",
        "email": "   ",
        "monthly_income": "50000",
        "credit_score": "700",
        "employment_status": "salaried",
        "age": "30",
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "Missing required field 'email'" in error


@pytest.mark.parametrize("invalid_email", [
    "plainaddress",
    "missingatsign.com",
    "@missingusername.com",
    "user@nodot",
    "spaces in@address.com",
])
def test_validate_row_invalid_email(invalid_email):
    """Verify malformed email addresses are rejected."""
    raw_row = {
        "user_id": "usr-500",
        "email": invalid_email,
        "monthly_income": "45000",
        "credit_score": "720",
        "employment_status": "salaried",
        "age": "29",
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "Invalid email address format" in error


def test_validate_row_negative_income():
    """Verify negative income is rejected."""
    raw_row = {
        "user_id": "usr-600",
        "email": "test@example.com",
        "monthly_income": "-100",
        "credit_score": "720",
        "employment_status": "salaried",
        "age": "29",
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "monthly_income must be non-negative" in error


def test_validate_row_non_numeric_income():
    """Verify non-numeric income strings are rejected."""
    raw_row = {
        "user_id": "usr-601",
        "email": "test@example.com",
        "monthly_income": "forty-thousand",
        "credit_score": "720",
        "employment_status": "salaried",
        "age": "29",
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "monthly_income must be a valid number" in error


@pytest.mark.parametrize("invalid_credit", [299, 901, "abc", -50])
def test_validate_row_invalid_credit_score(invalid_credit):
    """Verify credit scores outside 300-900 or non-integer are rejected."""
    raw_row = {
        "user_id": "usr-700",
        "email": "test@example.com",
        "monthly_income": "50000",
        "credit_score": str(invalid_credit),
        "employment_status": "salaried",
        "age": "30",
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "credit_score" in error


@pytest.mark.parametrize("invalid_age", [17, 101, "twenty", 0])
def test_validate_row_invalid_age(invalid_age):
    """Verify ages outside 18-100 or non-integer are rejected."""
    raw_row = {
        "user_id": "usr-800",
        "email": "test@example.com",
        "monthly_income": "50000",
        "credit_score": "750",
        "employment_status": "salaried",
        "age": str(invalid_age),
    }
    clean_row, error = validate_row(raw_row)
    assert clean_row is None
    assert "age" in error


@pytest.mark.parametrize(
    "input_status, expected_status",
    [
        ("Salaried", "salaried"),
        ("self-employed", "self_employed"),
        ("Self Employed", "self_employed"),
        ("business", "self_employed"),
        ("freelancer", "self_employed"),
        ("unemployed", "unemployed"),
        ("student", "student"),
        ("retired", "other"),
        ("homemaker", "other"),
        ("unknown_category", "other"),
    ],
)
def test_validate_row_employment_normalization(input_status, expected_status):
    """Verify varied employment status strings map to canonical categories."""
    raw_row = {
        "user_id": "usr-900",
        "email": "test@example.com",
        "monthly_income": "50000",
        "credit_score": "750",
        "employment_status": input_status,
        "age": "35",
    }
    clean_row, error = validate_row(raw_row)
    assert error is None
    assert clean_row["employment_status"] == expected_status
