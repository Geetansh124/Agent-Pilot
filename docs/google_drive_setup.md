# Google Drive Persistent Storage Setup for Agent-Pilot

This guide explains how to set up Google Drive as the **single persistent file storage backend** for Agent-Pilot.

---

## Architecture Overview

Agent-Pilot separates structured relational application state from persistent file storage:

- **Database (SQLite / PostgreSQL)**: Checkpoints, sessions, messages, users, audit logs, and memories.
- **Google Drive**: All persistent user and application files that must survive Render redeployments and restarts:
  - Uploaded documents (PDF, DOCX, CSV, TXT, JSON, MD)
  - Agent-generated workspace files (`workspace/<thread_id>/...`)
  - FAISS vector store artifacts (`index.faiss`, `index.pkl`)
  - Generated reports and exports
  - Audio files

---

## Step 1: Enable Google Drive API in Google Cloud Console

1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new Google Cloud project or select an existing one (e.g., `agent-pilot-storage`).
3. In the search bar at the top, search for **Google Drive API**.
4. Click on **Google Drive API** and select **Enable**.

---

## Step 2: Create a Service Account

1. In Google Cloud Console, navigate to **IAM & Admin** > **Service Accounts**.
2. Click **+ CREATE SERVICE ACCOUNT**.
3. Set the service account details:
   - **Service account name**: `agent-pilot-storage`
   - **Service account ID**: `agent-pilot-storage` (auto-populated)
   - **Description**: `Persistent file storage agent for Agent-Pilot`
4. Click **CREATE AND CONTINUE**.
5. Granting project roles is optional since we will share a specific folder directly with the service account (least privilege principle). Click **CONTINUE** and then **DONE**.
6. Find the newly created service account in the list and copy its **Email address**:
   - Example: `agent-pilot-storage@agent-pilot-xxxxxx.iam.gserviceaccount.com`
   - **Save this email address** for Step 4.

---

## Step 3: Generate and Download Service Account Key JSON

1. Click on the newly created service account.
2. Navigate to the **KEYS** tab.
3. Click **ADD KEY** > **Create new key**.
4. Select **JSON** as the key type and click **CREATE**.
5. A `.json` key file will download to your local machine.
   > **CRITICAL SECURITY RULE**:
   > - **NEVER** commit this JSON key file to Git.
   > - **NEVER** place this JSON file in the public repository or frontend.
   > - Keep this file safe and secure on your local computer.

---

## Step 4: Create and Share the Agent-Pilot Drive Folder

> **IMPORTANT**: A service account cannot see your personal Google Drive files unless you explicitly share a folder with its email address!

1. Open [Google Drive](https://drive.google.com/).
2. Create a new folder named `Agent-Pilot` (or any name you prefer).
3. Right-click the folder and select **Share** > **Share**.
4. In the "Add people and groups" field, paste the **service account email address** copied in Step 2:
   - Example: `agent-pilot-storage@agent-pilot-xxxxxx.iam.gserviceaccount.com`
5. Set permissions to **Editor** (this allows the service account to create folders and upload/download files).
6. Uncheck "Notify people" (service accounts do not have an inbox) and click **Share** / **Save**.

---

## Step 5: Obtain the Google Drive Folder ID

1. Double-click to open your newly created `Agent-Pilot` folder in Google Drive.
2. Look at the browser URL bar. The URL will look like:
   ```
   https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345
   ```
3. The long alphanumeric string after `/folders/` is your **Folder ID**:
   - Example: `1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345`
4. Copy this Folder ID.

---

## Step 6: Configure Render Environment Variables

In your [Render Dashboard](https://dashboard.render.com/):

1. Navigate to your **agent-pilot-api** Web Service.
2. Go to the **Environment** tab.
3. Add the following environment variables:

| Key | Value / Source | Description |
|---|---|---|
| `STORAGE_BACKEND` | `google_drive` | Activates Google Drive as single persistent file storage |
| `GOOGLE_DRIVE_FOLDER_ID` | `<Your-Folder-ID>` | The Folder ID obtained in Step 5 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `<Entire JSON content>` | Open the downloaded JSON key file in a text editor, copy the entire JSON string, and paste it directly into Render as the secret value. |

*(Optional Base64 format: You can also base64-encode the JSON if you prefer: `cat credentials.json | base64 -w 0`. Agent-Pilot automatically detects both raw JSON and base64-encoded JSON.)*

---

## Google Drive Storage Hierarchy

Agent-Pilot deterministically organizes all files under your shared folder:

```
Agent-Pilot/ (Root Folder)
├── documents/
│   └── <thread_id>/
│       ├── uploaded_document.pdf
│       └── metadata.json
│
├── workspace/
│   └── <thread_id>/
│       ├── analysis.csv
│       ├── report.md
│       ├── code.py
│       └── subfolder/
│           └── output.json
│
├── vectors/
│   └── <thread_id>/
│       ├── index.faiss
│       └── index.pkl
│
├── exports/
│   └── <thread_id>/
│       └── summary_export.pdf
│
├── attachments/
│   └── <thread_id>/
│       └── user_attachment.png
│
└── audio/
    └── <thread_id>/
        └── voice_query.wav
```

---

## Verification & Health Check

After setting the environment variables in Render:
1. Render will automatically redeploy the service.
2. Call the `/health` endpoint:
   ```bash
   curl https://<your-render-url>.onrender.com/health
   ```
3. The response will confirm the storage connection:
   ```json
   {
     "status": "ok",
     "storage": {
       "backend": "google_drive",
       "status": "connected"
     }
   }
   ```
4. If `status` is `connected`, Agent-Pilot is successfully reading, writing, and synchronizing all persistent files directly with Google Drive!
