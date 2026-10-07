# Frontend Upload UI Usage Guide

This guide explains how to configure and run the applicant data upload web interface locally.

---

## 1. Configure the Lambda Function URL

After deploying the backend with `npx serverless deploy`, copy the output value for `GetUploadUrlFunctionUrl`.

Open [frontend/index.html](file:///d:/des/clickpe_assign/frontend/index.html) and update line 38 with your Function URL:

```javascript
// Replace with your real Function URL output from serverless deploy
const API_URL = "https://<your-lambda-function-url-id>.lambda-url.<region>.on.aws/";
```

---

## 2. Opening the UI Locally

You can open the interface using Python's built-in lightweight HTTP server or directly in any modern browser:

### Option A: Local HTTP Server (Recommended)
Run this command from the repository root:
```powershell
python -m http.server 3000 --directory frontend
```
Then navigate to:
```
http://localhost:3000
```

### Option B: Direct File Open
You can also directly double-click [frontend/index.html](file:///d:/des/clickpe_assign/frontend/index.html) or open it with your browser (e.g. `start frontend/index.html` in PowerShell).

---

## 3. Uploading Files

1. Click **Choose File** and select a valid CSV (e.g. `data/sample_users.csv`).
2. Click **Upload Applicant Data**.
3. The UI will request a presigned S3 upload URL from Lambda, stream the file directly to your private S3 bucket under the `uploads/` folder, and display:
   ```
   Upload complete. Processing started.
   ```
