# AGENTS.md

Instructions for AI coding agents (Antigravity or any other) working in this repository. Read this file and `ARCHITECTURE.md` fully before writing any code.

---

## 1. Project summary

**Loan Eligibility Engine**: an automated pipeline that ingests a user CSV, discovers personal loan products from public websites, matches users to eligible products, and emails them.

Flow: `HTML UI -> S3 (presigned PUT) -> Lambda process_csv -> RDS PostgreSQL -> n8n webhook -> Workflow B (match) -> Workflow C (email via SES)`. Workflow A (crawler) runs daily on its own.

This is an SDE intern assignment. It is graded on: n8n workflow design (30), backend code quality (30), cloud architecture (20), documentation and video (20). Code must be easy for a beginner to read and explain.

---

## 2. Ownership: two parallel tracks (IMPORTANT)

The work is split between you (the agent) and the human. Stay inside your track.

| Track | Owner | Scope |
|---|---|---|
| **Code track** | **Agent** | SQL schema and seeds, `serverless.yml`, both Lambdas, `common/` helpers, frontend, `docker-compose.yml`, `.env.example`, tests, README skeleton |
| **n8n track** | **Human** | Workflow A (crawler), Workflow B (matching), Workflow C (notification), all n8n credentials, exported workflow JSON |

**The agent must NOT:**
- Create or edit any file in `n8n/workflows/`. The human builds workflows by hand in the n8n editor and exports the JSON themselves.
- Write n8n workflow JSON, n8n node configurations, or n8n Code-node scripts unless the human explicitly asks in that message.
- Change the contract in section 3 without telling the human, because their n8n workflows depend on it.

**The agent MUST:**
- Keep the contract (section 3) exactly as written. If a change is truly needed, stop and ask first, and update `ARCHITECTURE.md` in the same change.
- Provide the seed and test data (`seed_loan_products.sql`, `seed_test_users.sql`) so the human can build workflows before the Lambdas work.

---

## 3. Interface contract with the n8n track

Both tracks rely on these. Do not rename anything.

**Database tables and columns:** exactly as defined in `ARCHITECTURE.md` section 5 (`upload_batches`, `users`, `loan_products`, `matches`, `crawl_runs`).

**Webhook called by `process_csv` after a successful ingest:**
- Method: `POST`
- URL: value of env var `N8N_WEBHOOK_URL` (full URL, e.g. `https://<tunnel-host>/webhook/loan-batch`)
- Header: `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>`
- Header: `Content-Type: application/json`
- Body:
  ```json
  {
    "batch_id": "uuid-string",
    "user_count": 123,
    "rejected_count": 2,
    "filename": "uploads/2025-01-01T10-00-00-uuid.csv"
  }
  ```
- Expected response: HTTP 200 quickly (n8n responds immediately and processes afterwards).

**`upload_batches.status` values:** `processing`, `ingested`, `failed`, `webhook_failed` (set by the agent's code). The human's workflows may later set `matched` and `notified`.

**Seed data for the human:**
- `sql/seed_loan_products.sql`: 8-10 realistic personal loan products with varied criteria (some with `eligibility_notes` free text).
- `sql/seed_test_users.sql`: about 30 users in one test batch, deliberately including clear matches, clear rejects and borderline cases (income or credit score within ~5% of some product thresholds, mixed employment types).

---

## 4. Hard constraints

1. **Free tier only.** Never add a paid service. No NAT Gateway, no ElastiCache, no EC2/ECS unless the human asks. No Secrets Manager (use SSM Parameter Store standard tier or env vars).
2. **Backend language:** Python 3.12.
3. **IaC:** Serverless Framework (`serverless.yml`). n8n runs via Docker Compose.
4. **Region:** use a single region from the `AWS_REGION` env var.
5. **Lambdas run outside a VPC** and connect to a publicly accessible RDS over SSL (`sslmode=require`). Do not add VPC config or a NAT Gateway.
6. **Lambda only ingests.** Crawl, match and notify logic lives in n8n (human track), not in Lambda.
7. **No secrets in code or Git.** Use `.env` (gitignored) and `.env.example` (placeholders only).
8. **Keep it simple.** Plain functions over class hierarchies. No unnecessary frameworks or abstractions. The human must be able to explain every file.

---

## 5. Tech stack

| Area | Tool |
|---|---|
| Language | Python 3.12 (boto3, psycopg2-binary) |
| AWS | S3, Lambda (Function URL), RDS PostgreSQL (free tier), SES, SSM, SQS DLQ, CloudWatch |
| IaC | Serverless Framework + `serverless-python-requirements` |
| Workflow engine | n8n (Docker Compose, community edition), human-built workflows |
| Tunnel | Cloudflare Tunnel or ngrok (so Lambda can reach the n8n webhook) |
| LLM | Gemini Flash (free key), used inside n8n only |
| Frontend | Single `index.html` with vanilla JS, no build step |

---

## 6. Repository layout

```
loan-eligibility-engine/
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── serverless.yml
├── docker-compose.yml
├── .env.example
├── .gitignore
├── sql/
│   ├── schema.sql
│   ├── seed_loan_products.sql
│   └── seed_test_users.sql
├── src/
│   ├── get_upload_url.py
│   ├── process_csv.py
│   └── common/
│       ├── db.py
│       ├── validators.py
│       └── n8n_client.py
├── tests/
├── scripts/
│   ├── send_test_webhook.sh
│   └── run_process_csv_local.py
├── frontend/index.html
├── n8n/workflows/            <- HUMAN-OWNED, agent must not touch
├── data/sample_users.csv     <- provided by the human
└── docs/
```

Do not create files outside this layout without stating the reason.

---

## 7. Coding rules

**Python**
- Type hints on all function signatures; short docstring on every function explaining what and why.
- One responsibility per function. Keep Lambda handlers thin; logic goes in `common/`.
- Use the `logging` module, never `print`. Never log full emails or whole user rows.
- Read configuration only from environment variables.
- Stream the CSV (`csv.DictReader` over the S3 body); never load the whole file into memory.
- Batch DB writes (about 1,000 rows) with `psycopg2.extras.execute_values`.
- All inserts must be idempotent (`ON CONFLICT ... DO UPDATE` or `DO NOTHING`).
- One transaction per batch; always close connections.
- Bad rows are counted and written to `rejected/` in S3, not fatal. Real failures raise so retry and the DLQ catch them.

**SQL**
- Everything in `sql/schema.sql` with `CREATE TABLE IF NOT EXISTS`, plus the indexes in `ARCHITECTURE.md`.

**Frontend**
- Under about 100 lines. Status text for: requesting URL, uploading, success, error.

**serverless.yml**
- Least-privilege IAM: only the one bucket, needed SSM paths, the DLQ and logs.
- Define S3 CORS, the S3 event trigger (prefix `uploads/`, suffix `.csv`), env vars, timeouts (`process_csv`: 300s, 512 MB) and a DLQ.

---

## 8. Environment variables

Defined in `.env.example` (placeholders only):

```
AWS_REGION=
UPLOAD_BUCKET=
DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
N8N_WEBHOOK_URL=
N8N_WEBHOOK_SECRET=
SES_SENDER_EMAIL=
```

Gemini and AWS SES credentials for n8n are entered in the n8n credential store by the human, not in Lambda env vars.

---

## 9. Build order for the agent (follow strictly)

Work one step at a time. After each step: stop, summarize what was built in plain language, and tell the human exactly how to test it before moving on.

1. Repo skeleton, `.gitignore`, `.env.example`, `sql/schema.sql`, seed SQL files (unblocks the human)
2. `docker-compose.yml` for n8n and tunnel instructions (unblocks the human)
3. `serverless.yml` skeleton (S3, CORS, IAM, DLQ)
4. `get_upload_url` Lambda and `frontend/index.html`
5. `process_csv` Lambda and `common/` helpers
6. `n8n_client.py` webhook call with retry, status handling, and `scripts/send_test_webhook.sh`
7. Tests, idempotency check, local run script
8. `README.md` skeleton (the human fills the n8n sections)
9. Final review: secrets scan, checklist, clean-clone deploy test instructions

Do not jump ahead or generate everything at once. Do not start any n8n work.

---

## 10. How to work with the human

- The human is a beginner and must explain this project in a video. **Explain each file in 3-5 plain sentences** after creating it.
- Give exact commands to run and the expected output for each step.
- If something is ambiguous, ask one short question rather than guessing.
- Flag any step that could cost money before doing it.
- Do not refactor working code unless asked.
- Never invent AWS features. If unsure, say so.

---

## 11. Do not

- Do not touch `n8n/workflows/` or generate n8n workflow JSON.
- Do not add authentication, user accounts or an ORM.
- Do not add Kubernetes, Terraform, CI/CD or extra cloud services.
- Do not commit `.env`, keys, tokens, real-data DB dumps, or `node_modules`.
- Do not change table names, column names or the webhook contract silently.

---

## 12. Definition of done (agent track)

- [ ] `schema.sql` and both seed files run cleanly on a fresh RDS database
- [ ] CSV upload through the UI puts rows in `users` with no manual steps
- [ ] Re-uploading the same CSV creates no duplicates
- [ ] Bad CSV rows are rejected and logged without crashing the batch
- [ ] After ingest, the n8n webhook receives the contract payload; failures set `webhook_failed`
- [ ] `docker compose up -d` launches n8n; tunnel instructions work
- [ ] `serverless deploy` works from a clean clone
- [ ] README skeleton exists; no secrets in the repo
- [ ] Collaborators invited: saurabh@clickpe.ai, harsh.srivastav@clickpe.ai
