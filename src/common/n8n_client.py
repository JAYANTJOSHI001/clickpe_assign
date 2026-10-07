"""
Client helper for dispatching batch completion webhooks to self-hosted n8n.
Uses urllib.request with exponential backoff and timeout handling.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def notify_n8n(
    batch_id: str,
    user_count: int,
    rejected_count: int,
    filename: str,
    webhook_url: Optional[str] = None,
) -> bool:
    """
    Dispatch a POST notification to the n8n webhook URL with batch ingestion metrics.
    Retries up to 3 times with exponential backoff (1s, 2s, 4s) on connection failures
    or non-2xx HTTP responses. Returns True on success (HTTP 2xx), False otherwise.
    Never logs the secret token.
    """
    target_url = (webhook_url or os.environ.get("N8N_WEBHOOK_URL", "")).strip()
    webhook_secret = os.environ.get("N8N_WEBHOOK_SECRET", "").strip()

    if not target_url:
        logger.warning("N8N_WEBHOOK_URL is not configured; skipping webhook dispatch.")
        return False

    payload: Dict[str, object] = {
        "batch_id": batch_id,
        "user_count": user_count,
        "rejected_count": rejected_count,
        "filename": filename,
    }
    encoded_data = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": webhook_secret,
        "User-Agent": "LoanEligibilityEngine-Lambda/1.0",
    }

    req = urllib.request.Request(
        url=target_url,
        data=encoded_data,
        headers=headers,
        method="POST",
    )

    backoff_delays = [1.0, 2.0, 4.0]
    total_attempts = len(backoff_delays)

    for attempt_idx, delay in enumerate(backoff_delays, start=1):
        try:
            logger.info(
                "Dispatching n8n webhook for batch=%s (attempt %d/%d) to %s",
                batch_id,
                attempt_idx,
                total_attempts,
                target_url,
            )
            timeout_seconds = float(os.environ.get("N8N_WEBHOOK_TIMEOUT", "30.0"))
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                status_code = response.getcode()
                if 200 <= status_code < 300:
                    logger.info(
                        "n8n webhook responded successfully with HTTP %d for batch=%s",
                        status_code,
                        batch_id,
                    )
                    return True
                logger.warning(
                    "n8n webhook returned non-2xx status code: %d (attempt %d/%d)",
                    status_code,
                    attempt_idx,
                    total_attempts,
                )
        except urllib.error.HTTPError as http_err:
            logger.warning(
                "HTTP error calling n8n webhook (status %d): %s (attempt %d/%d)",
                http_err.code,
                http_err.reason,
                attempt_idx,
                total_attempts,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as net_err:
            logger.warning(
                "Network/timeout error calling n8n webhook: %s (attempt %d/%d)",
                str(net_err),
                attempt_idx,
                total_attempts,
            )
        except Exception as exc:
            logger.warning(
                "Unexpected error calling n8n webhook: %s (attempt %d/%d)",
                str(exc),
                attempt_idx,
                total_attempts,
            )

        if attempt_idx < total_attempts:
            logger.info("Retrying n8n webhook in %.1f seconds...", delay)
            time.sleep(delay)

    logger.error("All %d attempts to reach n8n webhook failed for batch=%s", total_attempts, batch_id)
    return False
