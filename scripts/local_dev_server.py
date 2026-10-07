#!/usr/bin/env python3
"""
Local Development Server for Loan Eligibility Engine.
Runs a local HTTP server simulating AWS API Gateway/Lambda and S3 for end-to-end testing.
Serves frontend/index.html and processes CSV uploads directly into RDS PostgreSQL,
then triggers the local n8n matching webhook.

Usage:
    python scripts/local_dev_server.py
"""

import csv
import io
import json
import logging
import os
import sys
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

# Ensure root directory is on sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
os.environ.setdefault("N8N_WEBHOOK_TIMEOUT", "60.0")

from src.common.db import (
    create_batch,
    get_batch_details,
    get_connection,
    get_recent_batches,
    get_system_stats,
    update_batch,
    upsert_users,
)
from src.common.n8n_client import notify_n8n
from src.common.validators import check_header, validate_row

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("local_server")

PORT = 8000
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
CHUNK_SIZE = 1000


class LocalDevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Connection", "close")

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/api/upload-url", "/upload-url"):
            # Simulate get_upload_url Lambda
            unique_id = str(uuid.uuid4())
            response_data = {
                "upload_url": f"http://localhost:{PORT}/api/upload?batch_id={unique_id}",
                "key": f"uploads/local-{unique_id}.csv",
                "batch_id": unique_id,
            }
            body = json.dumps(response_data).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            logger.info("Provided presigned upload URL simulation for local batch %s", unique_id)
            return

        if parsed.path in ("/api/batches", "/batches"):
            try:
                conn = get_connection()
                batches = get_recent_batches(conn, limit=15)
                body = json.dumps({"batches": batches}).encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                logger.error("Failed to fetch batches: %s", str(exc))
                err_body = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
            return

        if parsed.path in ("/api/batch-status", "/batch-status"):
            query_params = parse_qs(parsed.query)
            batch_id = query_params.get("batch_id", [None])[0]
            if not batch_id:
                err_body = json.dumps({"error": "Missing batch_id query parameter"}).encode("utf-8")
                self.send_response(400)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
                return

            try:
                conn = get_connection()
                details = get_batch_details(conn, batch_id)
                if not details:
                    err_body = json.dumps({"error": "Batch not found"}).encode("utf-8")
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(err_body)
                    return

                body = json.dumps(details).encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                logger.error("Failed to fetch batch details for %s: %s", batch_id, str(exc))
                err_body = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
            return

        if parsed.path in ("/api/stats", "/stats"):
            try:
                conn = get_connection()
                stats = get_system_stats(conn)
                body = json.dumps(stats).encode("utf-8")
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                logger.error("Failed to fetch stats: %s", str(exc))
                err_body = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
            return

        # Fallback to serving frontend static files
        super().do_GET()

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/upload":
            self.send_response(404)
            self.end_headers()
            return

        # Handle direct CSV upload and process through ingest pipeline
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        query_params = parse_qs(parsed.query)
        batch_id = query_params.get("batch_id", [str(uuid.uuid4())])[0]
        filename = f"uploads/local-test-{batch_id[:8]}.csv"

        logger.info("Processing uploaded CSV locally (%d bytes, batch=%s)...", len(raw_body), batch_id)

        try:
            conn = get_connection()
            create_batch(conn, batch_id, filename)

            text_stream = io.StringIO(raw_body.decode("utf-8", errors="replace"))
            reader = csv.DictReader(text_stream)

            # 1. Header Validation
            is_valid_header, header_error = check_header(reader.fieldnames)
            if not is_valid_header:
                raise ValueError(f"Header validation failed: {header_error}")

            total_rows = 0
            inserted_rows = 0
            rejected_rows_count = 0
            valid_chunk = []

            # 2. Row Validation & Batch Upsert
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

            if valid_chunk:
                upsert_users(conn, valid_chunk, batch_id)
                inserted_rows += len(valid_chunk)

            # 3. Mark Batch Ingested
            update_batch(
                conn,
                batch_id,
                total_rows=total_rows,
                inserted_rows=inserted_rows,
                rejected_rows=rejected_rows_count,
                status="ingested",
            )
            logger.info(
                "Ingestion complete: total=%d, inserted=%d, rejected=%d",
                total_rows,
                inserted_rows,
                rejected_rows_count,
            )

            resp_body = json.dumps({
                "status": "success",
                "batch_id": batch_id,
                "total_rows": total_rows,
                "inserted_rows": inserted_rows,
                "rejected_rows": rejected_rows_count,
            }).encode("utf-8")

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
            self.wfile.flush()

            # 4. Trigger n8n Webhook asynchronously in background so client is never blocked
            def _async_notify():
                try:
                    webhook_url = os.environ.get("N8N_WEBHOOK_URL", "")
                    # Try local n8n first for fast dev iteration, then tunnel URL
                    preferred_url = "http://localhost:5678/webhook/loan-batch"
                    logger.info("Dispatching async webhook to n8n (%s)...", preferred_url)
                    ok = notify_n8n(
                        batch_id=batch_id,
                        user_count=inserted_rows,
                        rejected_count=rejected_rows_count,
                        filename=filename,
                        webhook_url=preferred_url,
                    )
                    if not ok and webhook_url and webhook_url != preferred_url:
                        logger.info("Trying configured N8N_WEBHOOK_URL: %s...", webhook_url)
                        ok = notify_n8n(
                            batch_id=batch_id,
                            user_count=inserted_rows,
                            rejected_count=rejected_rows_count,
                            filename=filename,
                            webhook_url=webhook_url,
                        )
                    if ok:
                        logger.info("n8n webhook accepted batch %s successfully!", batch_id)
                    else:
                        logger.warning("n8n webhook notification returned non-2xx or timed out.")
                        c = get_connection()
                        update_batch(c, batch_id, status="webhook_failed")
                except Exception as exc:
                    logger.error("Async webhook dispatch error: %s", str(exc))

            import threading
            threading.Thread(target=_async_notify, daemon=True).start()
            return

        except Exception as exc:
            logger.error("Local ingest failed: %s", str(exc), exc_info=True)
            err_body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(500)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/api/retry-webhook", "/retry-webhook"):
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                data = {}

            query_params = parse_qs(parsed.query)
            batch_id = data.get("batch_id") or query_params.get("batch_id", [None])[0]

            if not batch_id:
                err_body = json.dumps({"error": "Missing batch_id"}).encode("utf-8")
                self.send_response(400)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
                return

            try:
                conn = get_connection()
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT filename, inserted_rows, rejected_rows FROM upload_batches WHERE batch_id = %s",
                        (batch_id,),
                    )
                    row = cur.fetchone()

                if not row:
                    err_body = json.dumps({"error": "Batch not found"}).encode("utf-8")
                    self.send_response(404)
                    self._send_cors_headers()
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err_body)))
                    self.end_headers()
                    self.wfile.write(err_body)
                    return

                filename, inserted_rows, rejected_rows = row
                webhook_url = os.environ.get("N8N_WEBHOOK_URL", "")
                logger.info("Retrying webhook dispatch for batch %s...", batch_id)

                webhook_ok = notify_n8n(
                    batch_id=batch_id,
                    user_count=inserted_rows,
                    rejected_count=rejected_rows,
                    filename=filename,
                )

                if not webhook_ok and ("trycloudflare" in webhook_url or "ngrok" in webhook_url):
                    local_fallback_url = "http://localhost:5678/webhook/loan-batch"
                    logger.info("Tunnel failed. Retrying with local n8n endpoint: %s...", local_fallback_url)
                    webhook_ok = notify_n8n(
                        batch_id=batch_id,
                        user_count=inserted_rows,
                        rejected_count=rejected_rows,
                        filename=filename,
                        webhook_url=local_fallback_url,
                    )

                if webhook_ok:
                    update_batch(conn, batch_id, status="ingested")
                    resp = json.dumps({"status": "success", "batch_status": "ingested", "n8n_webhook_dispatched": True}).encode("utf-8")
                else:
                    update_batch(conn, batch_id, status="webhook_failed")
                    resp = json.dumps({"status": "failed", "batch_status": "webhook_failed", "n8n_webhook_dispatched": False}).encode("utf-8")

                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            except Exception as exc:
                logger.error("Retry webhook failed: %s", str(exc), exc_info=True)
                err_body = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            return

        self.send_response(404)
        self.end_headers()


def main() -> None:
    logger.info("Starting Local Development Server...")
    logger.info("Connecting to RDS: %s (db: %s)...", os.environ.get("DB_HOST"), os.environ.get("DB_NAME"))
    try:
        conn = get_connection()
        conn.close()
        logger.info("RDS PostgreSQL connection verified!")
    except Exception as exc:
        logger.error("Failed to connect to RDS: %s", str(exc))
        sys.exit(1)

    server = ThreadedHTTPServer(("0.0.0.0", PORT), LocalDevHandler)
    logger.info("Local Web Server running at: http://localhost:%d", PORT)
    logger.info("Serving UI from: %s", FRONTEND_DIR)
    logger.info("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down local server.")
        server.server_close()


if __name__ == "__main__":
    main()
