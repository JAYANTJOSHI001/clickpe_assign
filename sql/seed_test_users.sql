-- Seed data for 30 test users in a fixed test batch
-- Designed for testing matching logic: ~10 clear matches, ~10 clear rejects, ~10 borderline cases
-- Idempotent: safe to run multiple times using ON CONFLICT clauses

-- 1. Create or update the test batch record
INSERT INTO upload_batches (
    batch_id,
    filename,
    total_rows,
    inserted_rows,
    rejected_rows,
    status,
    created_at
) VALUES (
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    'uploads/seed_test_users.csv',
    30,
    30,
    0,
    'ingested',
    NOW()
)
ON CONFLICT (batch_id) DO UPDATE
SET total_rows = EXCLUDED.total_rows,
    inserted_rows = EXCLUDED.inserted_rows,
    rejected_rows = EXCLUDED.rejected_rows,
    status = EXCLUDED.status;

-- 2. Insert test users
INSERT INTO users (
    user_id,
    email,
    monthly_income,
    credit_score,
    employment_status,
    age,
    upload_batch_id,
    created_at
) VALUES
-- ============================================================================
-- GROUP 1: CLEAR MATCHES (~10 users)
-- High/moderate income, high credit score, eligible age, valid employment status
-- ============================================================================
(
    'usr_clear_01',
    'testuser01@example.com',
    85000.00,
    780,
    'salaried',
    32,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_02',
    'testuser02@example.com',
    120000.00,
    810,
    'salaried',
    40,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_03',
    'testuser03@example.com',
    65000.00,
    750,
    'salaried',
    29,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_04',
    'testuser04@example.com',
    90000.00,
    740,
    'self_employed',
    38,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_05',
    'testuser05@example.com',
    55000.00,
    725,
    'salaried',
    35,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_06',
    'testuser06@example.com',
    70000.00,
    760,
    'self_employed',
    45,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_07',
    'testuser07@example.com',
    45000.00,
    715,
    'salaried',
    28,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_08',
    'testuser08@example.com',
    150000.00,
    820,
    'salaried',
    42,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_09',
    'testuser09@example.com',
    50000.00,
    735,
    'salaried',
    30,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_clear_10',
    'testuser10@example.com',
    80000.00,
    755,
    'self_employed',
    34,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),

-- ============================================================================
-- GROUP 2: CLEAR REJECTS (~10 users)
-- Fails core criteria: unemployed, student, subprime credit, extreme age, or tiny income
-- ============================================================================
(
    'usr_reject_11',
    'testuser11@example.com',
    8000.00,
    520,
    'unemployed',
    24,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_12',
    'testuser12@example.com',
    0.00,
    610,
    'student',
    20,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_13',
    'testuser13@example.com',
    12000.00,
    540,
    'salaried',
    22,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_14',
    'testuser14@example.com',
    60000.00,
    480,
    'salaried',
    36,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_15',
    'testuser15@example.com',
    50000.00,
    750,
    'salaried',
    72,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_16',
    'testuser16@example.com',
    40000.00,
    720,
    'salaried',
    17,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_17',
    'testuser17@example.com',
    200000.00,
    790,
    'unemployed',
    35,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_18',
    'testuser18@example.com',
    10000.00,
    500,
    'other',
    40,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_19',
    'testuser19@example.com',
    0.00,
    580,
    'student',
    22,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    'usr_reject_20',
    'testuser20@example.com',
    35000.00,
    450,
    'self_employed',
    48,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),

-- ============================================================================
-- GROUP 3: BORDERLINE CASES (~10 users)
-- Metrics are within ~5% of product thresholds (income or credit score)
-- ============================================================================
(
    -- Within 3.2% of HDFC 25,000 min income requirement (meets 720 score)
    'usr_borderline_21',
    'testuser21@example.com',
    24200.00,
    725,
    'salaried',
    26,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 1.1% of HDFC 720 credit score requirement (meets 25k income)
    'usr_borderline_22',
    'testuser22@example.com',
    26000.00,
    712,
    'salaried',
    28,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 4% of Kotak 20,000 min income requirement (meets 720 score)
    'usr_borderline_23',
    'testuser23@example.com',
    19200.00,
    730,
    'salaried',
    25,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 0.7% of Tata Capital 675 credit score requirement (income 35k)
    'usr_borderline_24',
    'testuser24@example.com',
    35000.00,
    670,
    'salaried',
    30,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 3.4% of ICICI 35,000 min income requirement for self-employed
    'usr_borderline_25',
    'testuser25@example.com',
    33800.00,
    710,
    'self_employed',
    27,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 3.3% of Poonawalla 30,000 min income requirement (score 735)
    'usr_borderline_26',
    'testuser26@example.com',
    29000.00,
    735,
    'salaried',
    31,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 2.2% of Bajaj 22,000 min income requirement (score 690)
    'usr_borderline_27',
    'testuser27@example.com',
    21500.00,
    690,
    'salaried',
    24,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 0.8% of SBI 650 credit score requirement (income 45k)
    'usr_borderline_28',
    'testuser28@example.com',
    45000.00,
    645,
    'salaried',
    27,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 0.7% of IDFC FIRST 710 credit score requirement (income 28k)
    'usr_borderline_29',
    'testuser29@example.com',
    28000.00,
    705,
    'salaried',
    29,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
),
(
    -- Within 0.7% of Axis Bank 700 credit score requirement (income 31k)
    'usr_borderline_30',
    'testuser30@example.com',
    31000.00,
    695,
    'salaried',
    28,
    'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    NOW()
)
ON CONFLICT (user_id) DO UPDATE
SET email = EXCLUDED.email,
    monthly_income = EXCLUDED.monthly_income,
    credit_score = EXCLUDED.credit_score,
    employment_status = EXCLUDED.employment_status,
    age = EXCLUDED.age,
    upload_batch_id = EXCLUDED.upload_batch_id;
