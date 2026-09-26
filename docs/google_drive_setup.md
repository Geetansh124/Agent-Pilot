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

## Step 4: Create a Google Workspace "Shared Drive" and Add Service Account

> **CRITICAL QUOTA RULE**: Standalone Google Service Accounts have **0 MB personal storage quota**.
> You **MUST** use a **Shared Drive** (Team Drive), where files belong to the organization/Shared Drive rather than the service account. Creating a regular folder in personal "My Drive" will fail with `403 storageQuotaExceeded`.

1. Open [Google Drive](https://drive.google.com/).
2. In the left navigation sidebar, click on **Shared drives** (under "My Drive").
3. Click **+ New** (or right-click in the empty area) to create a new Shared Drive named **Agent-Pilot**.
4. Open your new `Agent-Pilot` Shared Drive and click **Manage members** in the upper right.
5. In the "Add people, groups, and calendar events" field, paste your **service account email**:
   ```
   agent-pilot-storage@my-docupilot-project.iam.gserviceaccount.com
   ```
6. Set permissions to **Content manager** (or **Manager**). This allows the service account to create folders, upload files, and manage artifacts.
7. Uncheck "Notify people" and click **Send** / **Save**.

---

## Step 5: Obtain the Shared Drive ID

1. Open your newly created `Agent-Pilot` Shared Drive in the browser.
2. Look at the browser URL bar. The URL will look like:
   ```
   https://drive.google.com/drive/folders/1s1Mak4AY88adi8hHg5by-YIHY1f4nEqs
   ```
3. The alphanumeric string after `/folders/` is your **Shared Drive ID**:
   - Example: `1s1Mak4AY88adi8hHg5by-YIHY1f4nEqs`
4. Copy this ID and use it as `GOOGLE_DRIVE_FOLDER_ID`.

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
