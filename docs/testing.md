# Testing & Verification Guide

This guide covers running unit test suites locally with `pytest` and executing offline CSV validation dry runs.

---

## 1. Prerequisites

Install the development and testing dependencies:
```powershell
pip install -r requirements-dev.txt
```

---

## 2. Running Unit Tests with `pytest`

The test suite covers header validation, row-level sanitization, normalization edge cases, S3 streaming, database batching, and error handling without requiring active AWS or RDS connections.

### Run the Complete Test Suite
```powershell
pytest -v
```

### Run Validator Tests Only
Tests all field constraints, email formats, numerical ranges, and employment mappings:
```powershell
pytest tests/test_validators.py -v
```

### Run Lambda Ingestion Tests Only
Tests S3 streaming, 1,000-row batching, S3 `rejected/` row uploads, and failure states using mocks:
```powershell
pytest tests/test_process_csv.py -v
```

### Expected Output
```
tests/test_process_csv.py::test_mixed_csv_counts PASSED
tests/test_process_csv.py::test_chunking_at_1000 PASSED
tests/test_process_csv.py::test_header_failure_marks_failed_and_reraises PASSED
tests/test_process_csv.py::test_webhook_failure_marks_webhook_failed_without_raising PASSED
tests/test_validators.py::test_check_header_valid PASSED
...
============================= 37 passed in 3.11s ==============================
```

---

## 3. Running the Local CSV Dry-Run Script

Before uploading a new dataset to AWS S3, you can validate its structure, format, and rejected row reasons offline using [scripts/run_process_csv_local.py](file:///d:/des/clickpe_assign/scripts/run_process_csv_local.py).

### Run on Default Sample Dataset (`data/sample_users.csv`)
```powershell
python scripts/run_process_csv_local.py
```

### Run on a Custom File
```powershell
python scripts/run_process_csv_local.py path/to/your_file.csv
```

### Expected Output
```
--- Dry Run CSV Validation: data/sample_users.csv ---
Header validation PASSED. Detected columns: ['user_id', 'name', 'email', 'monthly_income', 'credit_score', 'employment_status', 'age']

--- Validation Summary ---
Total Rows Processed : 10,000
Valid Rows (Accepted): 10,000
Rejected Rows        : 0

All processed rows satisfied validation constraints!
```
If invalid rows exist, the script reports the exact counts and prints sample reasons (e.g. `Row 42 (usr-42): monthly_income must be non-negative`).
