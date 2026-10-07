#!/usr/bin/env bash
# ==============================================================================
# Dispatch a test webhook payload directly to n8n Workflow B
# Uses the fixed test batch seeded from sql/seed_test_users.sql
# Reads N8N_WEBHOOK_URL and N8N_WEBHOOK_SECRET from .env
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  exit 1
fi

# Load variables from .env
export $(grep -v '^#' "$ENV_FILE" | grep -v '^\s*$' | xargs)

if [[ -z "${N8N_WEBHOOK_URL:-}" ]]; then
  echo "Error: N8N_WEBHOOK_URL is not set in .env" >&2
  exit 1
fi

if [[ -z "${N8N_WEBHOOK_SECRET:-}" ]]; then
  echo "Error: N8N_WEBHOOK_SECRET is not set in .env" >&2
  exit 1
fi

echo "Sending test webhook to: $N8N_WEBHOOK_URL"

PAYLOAD='{
  "batch_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
  "user_count": 30,
  "rejected_count": 0,
  "filename": "uploads/seed_test_users.csv"
}'

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X POST "$N8N_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $N8N_WEBHOOK_SECRET" \
  -d "$PAYLOAD")

BODY=$(echo "$RESPONSE" | sed '$d')
STATUS=$(echo "$RESPONSE" | tail -n 1 | sed 's/HTTP_STATUS://')

echo "Response Status: $STATUS"
echo "Response Body:   $BODY"

if [[ "$STATUS" -ge 200 && "$STATUS" -lt 300 ]]; then
  echo "SUCCESS: Test webhook accepted by n8n."
  exit 0
else
  echo "FAILED: n8n webhook returned non-2xx status ($STATUS)." >&2
  exit 1
fi
