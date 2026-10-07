"""
Lambda handler for streaming, validating, and ingesting applicant CSV uploads.
Triggers automatically on S3 ObjectCreated events in uploads/*.csv.
Streams records in chunks of 1000, writes rejected rows to S3, and records batch metrics.
"""

import csv
import io
import logging
import os
import urllib.parse
import uuid
from typing import Any, Dict, List
import boto3
from botocore.config import Config

from src.common.db import create_batch, get_connection, update_batch, upsert_users
from src.common.n8n_client import notify_n8n
from src.common.validators import check_header, validate_row

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4"),
)

CHUNK_SIZE = 1000


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main entry point for S3 ObjectCreated event notification.
    Streams CSV directly from S3, validates each record, and batch-upserts into RDS.
    """
    records = event.get("Records", [])
    if not records:
        logger.warning("No records found in S3 event payload.")
        return {"statusCode": 200, "body": "No records to process."}

    # Extract bucket and S3 object key
    s3_info = records[0].get("s3", {})
    bucket = s3_info.get("bucket", {}).get("name")
    raw_key = s3_info.get("object", {}).get("key")

    if not bucket or not raw_key:
        raise ValueError("Invalid S3 event: missing bucket name or object key.")

    # URL-decode the key (e.g. spaces, timestamps with plus signs)
    key = urllib.parse.unquote_plus(raw_key)
    logger.info("Starting ingestion for file: s3://%s/%s", bucket, key)

    batch_id = str(uuid.uuid4())
    conn = get_connection()

    # Step 1: Initialize batch record in 'processing' status
    create_batch(conn, batch_id, key)

    total_rows = 0
    inserted_rows = 0
    rejected_rows_count = 0
    rejected_records: List[Dict[str, Any]] = []

    try:
        # Step 2: Stream object body from S3 without loading entire file into memory
        s3_response = s3_client.get_object(Bucket=bucket, Key=key)
        body_stream = io.TextIOWrapper(s3_response["Body"], encoding="utf-8", errors="replace")
        reader = csv.DictReader(body_stream)

        # Validate CSV header before processing rows
        is_valid_header, header_error = check_header(reader.fieldnames)
        if not is_valid_header:
            raise ValueError(f"Header validation failed: {header_error}")

        valid_chunk: List[Dict[str, Any]] = []

        # Step 3: Stream and validate each row
        for row in reader:
            total_rows += 1
            clean_row, rejection_reason = validate_row(row)

            if clean_row is not None:
                valid_chunk.append(clean_row)
                if len(valid_chunk) >= CHUNK_SIZE:
                    upsert_users(conn, valid_chunk, batch_id)
                    inserted_rows += len(valid_chunk)
                    valid_chunk = []
            else:
                rejected_rows_count += 1
                rejected_row = dict(row)
                rejected_row["rejection_reason"] = rejection_reason
                rejected_records.append(rejected_row)

        # Flush any remaining valid rows
        if valid_chunk:
            upsert_users(conn, valid_chunk, batch_id)
            inserted_rows += len(valid_chunk)
            valid_chunk = []

        # Step 4: Write rejected rows to S3 if any were encountered
        if rejected_records:
            rejected_key = f"rejected/{batch_id}.csv"
            logger.info("Writing %d rejected rows to s3://%s/%s", len(rejected_records), bucket, rejected_key)

            output_buffer = io.StringIO()
            fieldnames = list(rejected_records[0].keys())
            writer = csv.DictWriter(output_buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rejected_records)

            s3_client.put_object(
                Bucket=bucket,
                Key=rejected_key,
                Body=output_buffer.getvalue().encode("utf-8"),
                ContentType="text/csv",
            )

        # Step 5: Mark batch as successfully ingested
        update_batch(
            conn,
            batch_id,
            total_rows=total_rows,
            inserted_rows=inserted_rows,
            rejected_rows=rejected_rows_count,
            status="ingested",
        )

        logger.info(
            "Batch %s completed: total=%d, inserted=%d, rejected=%d",
            batch_id,
            total_rows,
            inserted_rows,
            rejected_rows_count,
        )

        # Step 6: Dispatch notification webhook to n8n
        webhook_ok = notify_n8n(
            batch_id=batch_id,
            user_count=inserted_rows,
            rejected_count=rejected_rows_count,
            filename=key,
        )

        if not webhook_ok:
            logger.warning(
                "n8n webhook notification failed for batch %s. Marking status as 'webhook_failed'.",
                batch_id,
            )
            update_batch(conn, batch_id, status="webhook_failed")

        return {
            "statusCode": 200,
            "body": {
                "batch_id": batch_id,
                "total_rows": total_rows,
                "inserted_rows": inserted_rows,
                "rejected_rows": rejected_rows_count,
            },
        }

    except Exception as exc:
        logger.error("Ingestion failed for batch %s: %s", batch_id, str(exc), exc_info=True)
        try:
            update_batch(conn, batch_id, status="failed")
        except Exception:
            logger.exception("Failed to update batch status to 'failed'")
        # Re-raise so Lambda retry and SQS DLQ handle the failure
        raise
