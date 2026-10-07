"""
Unit tests for the process_csv Lambda function.
Uses unittest.mock to mock Amazon S3 and PostgreSQL RDS interactions.
Covers row counting, 1000-row chunking, failure recovery, and webhook handling.
"""

import io
from unittest.mock import MagicMock, patch
import pytest

from src.process_csv import handler


def make_s3_event(bucket: str = "test-bucket", key: str = "uploads/2026-10-06-batch.csv"):
    """Generate a mock S3 ObjectCreated event structure."""
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key},
                }
            }
        ]
    }


def make_s3_body(content: str):
    """Generate a mock S3 get_object response wrapping a binary buffer."""
    return {"Body": io.BytesIO(content.encode("utf-8"))}


@patch("src.process_csv.notify_n8n")
@patch("src.process_csv.update_batch")
@patch("src.process_csv.upsert_users")
@patch("src.process_csv.create_batch")
@patch("src.process_csv.get_connection")
@patch("src.process_csv.s3_client")
def test_mixed_csv_counts(
    mock_s3,
    mock_get_conn,
    mock_create_batch,
    mock_upsert_users,
    mock_update_batch,
    mock_notify_n8n,
):
    """
    Verify that a CSV containing valid and invalid rows correctly counts
    and routes valid rows to the DB and invalid rows to S3 rejected/.
    """
    csv_data = (
        "user_id,email,monthly_income,credit_score,employment_status,age\n"
        "usr-1,valid1@example.com,50000,750,salaried,30\n"
        "usr-2,invalid-email,40000,700,salaried,28\n"
        "usr-3,valid2@example.com,60000,800,self-employed,35\n"
        "usr-4,valid3@example.com,-5000,710,salaried,40\n"  # negative income rejected
        "usr-5,valid4@example.com,70000,680,business,45\n"
    )

    mock_s3.get_object.return_value = make_s3_body(csv_data)
    mock_notify_n8n.return_value = True

    event = make_s3_event()
    result = handler(event, None)

    assert result["statusCode"] == 200
    assert result["body"]["total_rows"] == 5
    assert result["body"]["inserted_rows"] == 3
    assert result["body"]["rejected_rows"] == 2

    # Verify DB upsert was called with the 3 valid rows
    assert mock_upsert_users.call_count == 1
    inserted_chunk = mock_upsert_users.call_args[0][1]
    assert len(inserted_chunk) == 3
    assert inserted_chunk[0]["user_id"] == "usr-1"
    assert inserted_chunk[1]["user_id"] == "usr-3"
    assert inserted_chunk[2]["user_id"] == "usr-5"

    # Verify rejected rows were uploaded to rejected/*.csv in S3
    assert mock_s3.put_object.call_count == 1
    put_call = mock_s3.put_object.call_args[1]
    assert put_call["Key"].startswith("rejected/")
    assert b"invalid-email" in put_call["Body"]
    assert b"-5000" in put_call["Body"]

    # Verify batch was marked ingested and n8n was notified
    mock_update_batch.assert_called_with(
        mock_get_conn(),
        mock_create_batch.call_args[0][1],
        total_rows=5,
        inserted_rows=3,
        rejected_rows=2,
        status="ingested",
    )
    mock_notify_n8n.assert_called_once()


@patch("src.process_csv.notify_n8n")
@patch("src.process_csv.update_batch")
@patch("src.process_csv.upsert_users")
@patch("src.process_csv.create_batch")
@patch("src.process_csv.get_connection")
@patch("src.process_csv.s3_client")
def test_chunking_at_1000(
    mock_s3,
    mock_get_conn,
    mock_create_batch,
    mock_upsert_users,
    mock_update_batch,
    mock_notify_n8n,
):
    """
    Verify that files exceeding 1000 rows are committed to the DB in chunks of 1000.
    2500 rows should produce 3 upsert calls: 1000, 1000, and 500.
    """
    header = "user_id,email,monthly_income,credit_score,employment_status,age\n"
    rows = [
        f"usr-{i},user{i}@example.com,50000,750,salaried,30\n"
        for i in range(2500)
    ]
    csv_data = header + "".join(rows)

    mock_s3.get_object.return_value = make_s3_body(csv_data)
    mock_notify_n8n.return_value = True

    event = make_s3_event()
    result = handler(event, None)

    assert result["body"]["total_rows"] == 2500
    assert result["body"]["inserted_rows"] == 2500
    assert result["body"]["rejected_rows"] == 0

    assert mock_upsert_users.call_count == 3
    assert len(mock_upsert_users.call_args_list[0][0][1]) == 1000
    assert len(mock_upsert_users.call_args_list[1][0][1]) == 1000
    assert len(mock_upsert_users.call_args_list[2][0][1]) == 500


@patch("src.process_csv.update_batch")
@patch("src.process_csv.create_batch")
@patch("src.process_csv.get_connection")
@patch("src.process_csv.s3_client")
def test_header_failure_marks_failed_and_reraises(
    mock_s3,
    mock_get_conn,
    mock_create_batch,
    mock_update_batch,
):
    """
    Verify that an invalid header causes the handler to set batch status
    to 'failed' and re-raise so the SQS DLQ can catch it.
    """
    bad_header_csv = "user_id,email,credit_score\nusr-1,test@example.com,700\n"
    mock_s3.get_object.return_value = make_s3_body(bad_header_csv)

    event = make_s3_event()

    with pytest.raises(ValueError, match="Header validation failed"):
        handler(event, None)

    # Verify batch was updated with status='failed'
    mock_update_batch.assert_called_with(
        mock_get_conn(),
        mock_create_batch.call_args[0][1],
        status="failed",
    )


@patch("src.process_csv.notify_n8n")
@patch("src.process_csv.update_batch")
@patch("src.process_csv.upsert_users")
@patch("src.process_csv.create_batch")
@patch("src.process_csv.get_connection")
@patch("src.process_csv.s3_client")
def test_webhook_failure_marks_webhook_failed_without_raising(
    mock_s3,
    mock_get_conn,
    mock_create_batch,
    mock_upsert_users,
    mock_update_batch,
    mock_notify_n8n,
):
    """
    Verify that if the webhook notification fails (n8n offline), the batch status
    is updated to 'webhook_failed', and the function still finishes successfully.
    """
    csv_data = (
        "user_id,email,monthly_income,credit_score,employment_status,age\n"
        "usr-1,user1@example.com,50000,750,salaried,30\n"
    )
    mock_s3.get_object.return_value = make_s3_body(csv_data)
    mock_notify_n8n.return_value = False  # Webhook fails

    event = make_s3_event()
    result = handler(event, None)

    assert result["statusCode"] == 200

    # Ensure status was updated to 'webhook_failed'
    mock_update_batch.assert_called_with(
        mock_get_conn(),
        mock_create_batch.call_args[0][1],
        status="webhook_failed",
    )
