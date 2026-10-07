# n8n and Tunnel Setup Guide

This guide covers running self-hosted n8n locally via Docker Compose, exposing it to AWS Lambda via a public tunnel, and configuring the required credentials.

---

## 1. How to Start n8n

Ensure Docker Desktop is running on your machine.

To start n8n along with the Cloudflare quick tunnel service, run:
```bash
docker compose --profile tunnel up -d
```

If you only want to start n8n locally without the tunnel container (for example, if using ngrok manually):
```bash
docker compose up -d n8n
```

Once started, access the n8n web editor at:
```
http://localhost:5678
```
Log in using the credentials defined in your `.env` file (`N8N_BASIC_AUTH_USER` and `N8N_BASIC_AUTH_PASSWORD`).

---

## 2. Finding the Tunnel URL and Setting `WEBHOOK_URL`

When the `cloudflared` service starts, it creates a temporary public HTTPS tunnel to your local n8n instance.

1. Inspect the container logs to find your assigned public URL:
   ```bash
   docker compose logs cloudflared
   ```
2. Look for an output line containing a URL formatted like:
   ```
   https://<random-words>.trycloudflare.com
   ```
3. Update your `.env` file with this base URL:
   ```env
   WEBHOOK_URL=https://<random-words>.trycloudflare.com/
   N8N_WEBHOOK_URL=https://<random-words>.trycloudflare.com/webhook/loan-batch
   ```
4. Restart the n8n service so it registers the external URL for webhook triggers:
   ```bash
   docker compose restart n8n
   ```

---

## 3. Production Webhook URL Format & Webhook Contract

When building Workflow B in n8n, configure the **Webhook** node with:
- **HTTP Method:** `POST`
- **Path:** `loan-batch`
- **Authentication:** Header Auth (checking `X-Webhook-Secret`)
- **Respond:** `Immediately` (HTTP 200)

> [!IMPORTANT]
> **Immediate Response Required:** Workflow B's Webhook node **must respond with HTTP 200 immediately** before running matching logic. If it waits for subsequent nodes to finish, Lambda's 10-second timeout may expire and mark the batch as `webhook_failed`.

In production mode (workflow active), n8n registers the URL as:
```
<tunnel-url>/webhook/loan-batch
```
*(During initial testing in the editor, n8n uses `<tunnel-url>/webhook-test/loan-batch`)*.

AWS Lambda reads `N8N_WEBHOOK_URL` from its environment variables and calls this exact endpoint upon finishing CSV ingestion.

### Webhook Contract Specification
- **Method:** `POST`
- **Headers:**
  - `Content-Type: application/json`
  - `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>`
- **JSON Body:**
  ```json
  {
    "batch_id": "uuid-string",
    "user_count": 123,
    "rejected_count": 2,
    "filename": "uploads/2025-01-01T10-00-00-uuid.csv"
  }
  ```

### Manual Trigger / Test Script
You can trigger Workflow B without uploading a file to S3 using the provided test scripts:
- **Linux / Git Bash:** `./scripts/send_test_webhook.sh`
- **Windows PowerShell:** `powershell -ExecutionPolicy Bypass -File scripts/send_test_webhook.ps1`

Both scripts send the contract payload using the pre-seeded batch UUID (`a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d`) from `sql/seed_test_users.sql`.

---

## 4. Tunnel Persistence & Alternatives

> [!NOTE]
> Cloudflare quick tunnels (`trycloudflare.com`) are free and require no account, but **the URL changes every time the container restarts**. Whenever you restart the tunnel container, update `WEBHOOK_URL` and `N8N_WEBHOOK_URL` in `.env` and restart n8n.

### Alternative: ngrok
If you prefer a persistent or manual tunnel using ngrok:
1. Start n8n alone:
   ```bash
   docker compose up -d n8n
   ```
2. Start ngrok in your terminal:
   ```bash
   ngrok http 5678
   ```
3. Copy the resulting forwarding URL (e.g., `https://xxxx.ngrok-free.app`) to `WEBHOOK_URL` and `N8N_WEBHOOK_URL` in `.env`, then run:
   ```bash
   docker compose restart n8n
   ```

---

## 5. Credentials to Configure in n8n

Before activating Workflows A, B, and C, create the following 4 credentials in the n8n editor under **Settings > Credentials**:

### 1. Postgres (for Amazon RDS)
Used to read users, read/write loan products, and record matches.
- **Credential Type:** `Postgres`
- **Host:** Value of `DB_HOST` from `.env`
- **Database:** Value of `DB_NAME` (default: `postgres`)
- **User:** Value of `DB_USER`
- **Password:** Value of `DB_PASSWORD`
- **Port:** `5432`
- **SSL:** `require` (or toggle **SSL** on, and allow unauthorized certs if using standard RDS default certificates)

### 2. AWS (for Amazon SES)
Used in Workflow C to send recommendation emails.
- **Credential Type:** `AWS`
- **Auth Type:** `IAM User`
- **Access Key ID:** Your AWS IAM access key (with `ses:SendEmail` permissions)
- **Secret Access Key:** Your AWS IAM secret access key
- **Region:** Value of `AWS_REGION` (e.g. `ap-south-1` or `us-east-1`)

### 3. Google Gemini API Key
Used in Workflow A (loan extraction) and Workflow B (borderline pair evaluation).
- **Credential Type:** `Google Gemini API` (or Google PaLM / Gemini credentials)
- **API Key:** Your free Gemini API key from Google AI Studio

### 4. Header Auth (for Webhook Security)
Used in Workflow B's Webhook node to reject unauthorized requests.
- **Credential Type:** `Header Auth`
- **Name:** `X-Webhook-Secret`
- **Value:** Exact string matching `N8N_WEBHOOK_SECRET` in `.env`
