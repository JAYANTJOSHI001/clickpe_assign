"""
Database helper module for PostgreSQL connection management and batch operations.
Maintains a warm connection across Lambda invocations and provides idempotent
helpers for batch status tracking and user upserts.
"""

import logging
import os
from typing import Any, Dict, List, Optional
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_conn: Optional[psycopg2.extensions.connection] = None


def get_connection() -> psycopg2.extensions.connection:
    """
    Retrieve an active PostgreSQL database connection with SSL required.
    Reuses an existing module-level connection across warm Lambda invocations,
    reconnecting if the connection is closed or severed.
    """
    global _conn

    if _conn is not None and not _conn.closed:
        try:
            with _conn.cursor() as cur:
                cur.execute("SELECT 1")
            return _conn
        except Exception:
            logger.warning("Existing database connection is dead. Reconnecting...")
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None

    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", "5432"))
    dbname = os.environ.get("DB_NAME", "postgres")
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASSWORD")

    if not all([host, user, password]):
        raise ValueError("Missing database configuration in environment variables.")

    logger.info("Opening new database connection to %s:%s/%s over SSL", host, port, dbname)
    _conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode="require",
        connect_timeout=10,
    )
    _conn.autocommit = False
    return _conn


def create_batch(conn: psycopg2.extensions.connection, batch_id: str, filename: str) -> None:
    """
    Insert an initial record into upload_batches with 'processing' status.
    Idempotent on batch_id conflict.
    """
    query = """
        INSERT INTO upload_batches (
            batch_id,
            filename,
            total_rows,
            inserted_rows,
            rejected_rows,
            status,
            created_at
        ) VALUES (%s, %s, 0, 0, 0, 'processing', NOW())
        ON CONFLICT (batch_id) DO UPDATE SET
            filename = EXCLUDED.filename,
            status = 'processing';
    """
    with conn.cursor() as cur:
        cur.execute(query, (batch_id, filename))
    conn.commit()
    logger.info("Created batch record for batch_id=%s", batch_id)


def update_batch(conn: psycopg2.extensions.connection, batch_id: str, **fields: Any) -> None:
    """
    Update status and row counts for a given batch_id.
    Accepts arbitrary keyword arguments matching columns in upload_batches.
    """
    if not fields:
        return

    allowed_columns = {"total_rows", "inserted_rows", "rejected_rows", "status"}
    valid_fields = {k: v for k, v in fields.items() if k in allowed_columns}

    if not valid_fields:
        return

    set_clauses = [f"{col} = %s" for col in valid_fields.keys()]
    values = list(valid_fields.values())
    values.append(batch_id)

    query = f"UPDATE upload_batches SET {', '.join(set_clauses)} WHERE batch_id = %s"

    with conn.cursor() as cur:
        cur.execute(query, tuple(values))
    conn.commit()
    logger.info("Updated batch %s: %s", batch_id, valid_fields)


def upsert_users(
    conn: psycopg2.extensions.connection,
    rows: List[Dict[str, Any]],
    batch_id: str,
) -> int:
    """
    Batch upsert user records into the users table using execute_values.
    Updates existing records on user_id conflict, ensuring idempotency.
    Returns the number of rows upserted.
    """
    if not rows:
        return 0

    query = """
        INSERT INTO users (
            user_id,
            email,
            monthly_income,
            credit_score,
            employment_status,
            age,
            upload_batch_id
        ) VALUES %s
        ON CONFLICT (user_id) DO UPDATE SET
            email = EXCLUDED.email,
            monthly_income = EXCLUDED.monthly_income,
            credit_score = EXCLUDED.credit_score,
            employment_status = EXCLUDED.employment_status,
            age = EXCLUDED.age,
            upload_batch_id = EXCLUDED.upload_batch_id;
    """

    records = [
        (
            r["user_id"],
            r["email"],
            r["monthly_income"],
            r["credit_score"],
            r["employment_status"],
            r["age"],
            batch_id,
        )
        for r in rows
    ]

    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, query, records, page_size=1000)
        conn.commit()
        return len(rows)
    except Exception as exc:
        conn.rollback()
        logger.error("Database batch upsert failed: %s", str(exc))
        raise


def get_batch_details(
    conn: psycopg2.extensions.connection,
    batch_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch comprehensive status, match counts, funnel breakdown, and sample matches for a batch.
    Returns None if the batch does not exist.
    """
    batch_query = """
        SELECT
            batch_id,
            filename,
            total_rows,
            inserted_rows,
            rejected_rows,
            status,
            created_at
        FROM upload_batches
        WHERE batch_id = %s;
    """
    with conn.cursor() as cur:
        cur.execute(batch_query, (batch_id,))
        batch_row = cur.fetchone()
        if not batch_row:
            return None

        batch_info = {
            "batch_id": str(batch_row[0]),
            "filename": batch_row[1],
            "total_rows": batch_row[2],
            "inserted_rows": batch_row[3],
            "rejected_rows": batch_row[4],
            "status": batch_row[5],
            "created_at": batch_row[6].isoformat() if batch_row[6] else None,
        }

        # Matches summary for this batch
        matches_summary_query = """
            SELECT
                COUNT(*) AS total_matches,
                COUNT(CASE WHEN notified = TRUE THEN 1 END) AS notified_matches
            FROM matches
            WHERE batch_id = %s;
        """
        cur.execute(matches_summary_query, (batch_id,))
        summary_row = cur.fetchone()
        total_matches = summary_row[0] if summary_row else 0
        notified_matches = summary_row[1] if summary_row else 0

        # Stages breakdown
        stages_query = """
            SELECT match_stage, COUNT(*)
            FROM matches
            WHERE batch_id = %s
            GROUP BY match_stage;
        """
        cur.execute(stages_query, (batch_id,))
        stage_counts = {row[0]: row[1] for row in cur.fetchall()}

        # Sample matches list (up to 50)
        matches_list_query = """
            SELECT
                m.user_id,
                lp.provider,
                lp.product_name,
                lp.interest_rate_min,
                lp.interest_rate_max,
                m.match_stage,
                m.score,
                m.reason,
                m.notified,
                m.created_at
            FROM matches m
            JOIN loan_products lp ON m.product_id = lp.id
            WHERE m.batch_id = %s
            ORDER BY m.notified DESC, m.id ASC
            LIMIT 200;
        """
        cur.execute(matches_list_query, (batch_id,))
        matches_sample = []
        for row in cur.fetchall():
            matches_sample.append({
                "user_id": row[0],
                "provider": row[1],
                "product_name": row[2],
                "interest_rate_min": float(row[3]) if row[3] is not None else None,
                "interest_rate_max": float(row[4]) if row[4] is not None else None,
                "match_stage": row[5],
                "score": float(row[6]) if row[6] is not None else None,
                "reason": row[7],
                "notified": bool(row[8]),
                "created_at": row[9].isoformat() if row[9] else None,
            })

    conn.commit()
    return {
        "batch": batch_info,
        "stats": {
            "total_matches": total_matches,
            "notified_matches": notified_matches,
            "stages": stage_counts,
        },
        "matches": matches_sample,
    }


def get_recent_batches(
    conn: psycopg2.extensions.connection,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Fetch a list of recent upload batches with aggregated match counts.
    """
    query = """
        SELECT
            b.batch_id,
            b.filename,
            b.total_rows,
            b.inserted_rows,
            b.rejected_rows,
            b.status,
            b.created_at,
            COUNT(m.id) AS match_count,
            COUNT(CASE WHEN m.notified = TRUE THEN 1 END) AS notified_count
        FROM upload_batches b
        LEFT JOIN matches m ON b.batch_id = m.batch_id
        GROUP BY b.batch_id, b.filename, b.total_rows, b.inserted_rows, b.rejected_rows, b.status, b.created_at
        ORDER BY b.created_at DESC
        LIMIT %s;
    """
    with conn.cursor() as cur:
        cur.execute(query, (limit,))
        rows = cur.fetchall()

    result = []
    for row in rows:
        result.append({
            "batch_id": str(row[0]),
            "filename": row[1],
            "total_rows": row[2],
            "inserted_rows": row[3],
            "rejected_rows": row[4],
            "status": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
            "match_count": row[7],
            "notified_count": row[8],
        })
    conn.commit()
    return result


def get_system_stats(
    conn: psycopg2.extensions.connection,
) -> Dict[str, Any]:
    """
    Fetch overall system counts: active loan products, total applicants,
    total batches, total matches, and SES notifications.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM loan_products WHERE is_active = TRUE;")
        active_products = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users;")
        total_users = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM upload_batches;")
        total_batches = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM matches;")
        total_matches = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM matches WHERE notified = TRUE;")
        total_notified = cur.fetchone()[0]

    conn.commit()
    return {
        "active_products": active_products,
        "total_users": total_users,
        "total_batches": total_batches,
        "total_matches": total_matches,
        "total_notified": total_notified,
    }

