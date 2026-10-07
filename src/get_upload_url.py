"""
Lambda handler for generating presigned S3 PUT URLs.
Enables clients to upload user CSV files directly to Amazon S3 without passing
through Lambda payload limits.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("UPLOAD_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=Config(signature_version="s3v4"),
)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle incoming HTTP requests from Lambda Function URL.
    Returns a short-lived presigned S3 PUT URL for uploading CSV files,
    or returns batch status / system insights when query parameters are supplied.
    """
    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod", "GET")
    )

    if http_method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": "",
        }

    try:
        query_params = event.get("queryStringParameters") or {}
        batch_id_param = query_params.get("batch_id")
        action_param = query_params.get("action")

        # Status inspection endpoint for frontend poller
        if batch_id_param:
            from src.common.db import get_batch_details, get_connection
            conn = get_connection()
            details = get_batch_details(conn, batch_id_param)
            if not details:
                return {
                    "statusCode": 404,
                    "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "Batch not found"}),
                }
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(details),
            }

        # Recent batches endpoint
        if action_param == "batches":
            from src.common.db import get_recent_batches, get_connection
            conn = get_connection()
            batches = get_recent_batches(conn, limit=15)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({"batches": batches}),
            }

        # System statistics endpoint
        if action_param == "stats":
            from src.common.db import get_system_stats, get_connection
            conn = get_connection()
            stats = get_system_stats(conn)
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(stats),
            }

        if not S3_BUCKET:
            raise ValueError("UPLOAD_BUCKET environment variable is not configured.")

        # Key format: uploads/YYYY-MM-DDTHH-MM-SS-<uuid>.csv
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        unique_id = str(uuid.uuid4())
        object_key = f"uploads/{timestamp}-{unique_id}.csv"

        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": object_key,
                "ContentType": "text/csv",
            },
            ExpiresIn=300,
        )

        response_payload = {
            "upload_url": presigned_url,
            "key": object_key,
            "batch_id": unique_id,
        }

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(response_payload),
        }
    except Exception as exc:
        logger.error("Failed in get_upload_url handler: %s", str(exc), exc_info=True)
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Failed to generate upload URL"}),
        }
