-- Loan Eligibility Engine Schema
-- Idempotent schema definition safe to run multiple times against PostgreSQL.

-- Table: upload_batches
-- Tracks every CSV upload batch from intake to ingestion and webhook dispatch
CREATE TABLE IF NOT EXISTS upload_batches (
    batch_id UUID PRIMARY KEY,
    filename TEXT NOT NULL,
    total_rows INT NOT NULL DEFAULT 0,
    inserted_rows INT NOT NULL DEFAULT 0,
    rejected_rows INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'processing',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: users
-- Stores applicant profiles ingested and normalised from uploaded CSVs
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    monthly_income NUMERIC(12, 2) NOT NULL,
    credit_score INT NOT NULL,
    employment_status TEXT NOT NULL,
    age INT NOT NULL,
    upload_batch_id UUID REFERENCES upload_batches(batch_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: loan_products
-- Catalog of personal loan products discovered via crawler or seeded
CREATE TABLE IF NOT EXISTS loan_products (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    product_name TEXT NOT NULL,
    interest_rate_min NUMERIC(5, 2),
    interest_rate_max NUMERIC(5, 2),
    min_income NUMERIC(12, 2),
    min_credit_score INT,
    max_credit_score INT,
    min_age INT,
    max_age INT,
    employment_required TEXT[],
    eligibility_notes TEXT,
    source_url TEXT,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_loan_products_provider_product UNIQUE (provider, product_name)
);

-- Table: matches
-- Output of the multi-stage matching funnel associating users with eligible loan products
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES loan_products(id) ON DELETE CASCADE,
    batch_id UUID REFERENCES upload_batches(batch_id) ON DELETE SET NULL,
    match_stage TEXT NOT NULL,
    score NUMERIC(5, 2),
    reason TEXT,
    notified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_matches_user_product UNIQUE (user_id, product_id)
);

-- Table: crawl_runs
-- Audit log of loan product discovery crawler executions
CREATE TABLE IF NOT EXISTS crawl_runs (
    run_id SERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL,
    products_found INT NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes as specified in ARCHITECTURE.md section 5
CREATE INDEX IF NOT EXISTS idx_users_upload_batch_id ON users(upload_batch_id);
CREATE INDEX IF NOT EXISTS idx_users_credit_score_monthly_income ON users(credit_score, monthly_income);
CREATE INDEX IF NOT EXISTS idx_matches_notified ON matches(notified);
CREATE INDEX IF NOT EXISTS idx_loan_products_is_active ON loan_products(is_active);
