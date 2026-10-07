#!/usr/bin/env python3
"""
Reset script to clear database history and test batches.
Truncates matches, users, and upload_batches tables in RDS PostgreSQL
so you have a completely clean slate for testing and demo recordings.
Preserves discovered loan_products.

Usage:
    python scripts/reset_data.py [--with-seeds]
"""

import os
import sys

# Ensure root directory is on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

import psycopg2

def main():
    print("Connecting to RDS PostgreSQL...")
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ.get("DB_NAME", "postgres"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"].strip("'"),
        sslmode="require",
    )
    conn.autocommit = True
    cur = conn.cursor()

    print("Clearing matches, users, and upload_batches...")
    cur.execute("TRUNCATE TABLE matches, users, upload_batches CASCADE;")

    with_seeds = "--with-seeds" in sys.argv

    if with_seeds:
        print("Re-seeding 30 test applicants from sql/seed_test_users.sql...")
        seed_users_path = os.path.join(ROOT_DIR, "sql", "seed_test_users.sql")
        with open(seed_users_path, "r", encoding="utf-8") as f:
            cur.execute(f.read())
        print("Re-seeded 30 test applicants successfully!")

    # Check products count
    cur.execute("SELECT count(*) FROM loan_products;")
    prod_count = cur.fetchone()[0]
    if prod_count == 0:
        print("Loan products catalog is empty. Seeding from sql/seed_loan_products.sql...")
        seed_prod_path = os.path.join(ROOT_DIR, "sql", "seed_loan_products.sql")
        with open(seed_prod_path, "r", encoding="utf-8") as f:
            cur.execute(f.read())
        cur.execute("SELECT count(*) FROM loan_products;")
        prod_count = cur.fetchone()[0]

    # Verify counts
    cur.execute("SELECT count(*) FROM users;")
    u_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM upload_batches;")
    b_count = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM matches;")
    m_count = cur.fetchone()[0]

    print("\n================== RESET COMPLETE ==================")
    print(f"Active Loan Products : {prod_count}")
    print(f"Total Users          : {u_count}")
    print(f"Total Batches        : {b_count}")
    print(f"Total Matches        : {m_count}")
    print("Database is clean and ready for a fresh upload!")
    print("====================================================\n")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
