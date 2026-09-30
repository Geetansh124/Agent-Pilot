# Production Deployment Guide — Agent-Pilot

This guide provides end-to-end instructions for deploying Agent-Pilot with a **FastAPI + LangGraph** backend on **Render** and a **Next.js** frontend on **Vercel**.

---

## 1. System Architecture & Live Endpoints

| Component | Platform | URL / Endpoint | Tier |
|---|---|---|---|
| **Backend API** | [Render](https://render.com) | `https://agent-pilot-api.onrender.com` | Free Web Service |
| **Frontend UI** | [Vercel](https://vercel.com) | `https://agent-pilot-rust.vercel.app/` | Free Hobby |
| **Storage Layer** | Cloud Storage | Multi-tenant persistent cloud store | Automated |
| **Local Dev Backend** | Localhost | `http://localhost:8000` | Native |
| **Local Dev Frontend** | Localhost | `http://localhost:3000` | Native |

---

## 2. Environment Variables

### Backend Configuration (Render Dashboard → Service → Environment)

| Variable | Description | Example / Default | Required |
|---|---|---|---|
| `NVIDIA_API_KEY` | NVIDIA NIM API key for LLM generation | `nvapi-...` | ✅ Yes |
| `HF_API_TOKEN` | Hugging Face token for embeddings | `hf_...` | ✅ Yes |
| `FRONTEND_ORIGIN` | Allowed production frontend origin for CORS | `https://agent-pilot-rust.vercel.app` | ✅ Yes |
| `MAX_FILE_SIZE_MB` | Maximum document upload size limit | `500` | Optional (default: `500`) |
| `JWT_SECRET_KEY` | Secret key for signing user auth tokens | `generate-secure-random-token` | Recommended |
| `STORAGE_BACKEND` | Storage provider (`google_drive`, `aws`, `local`) | `google_drive` | Optional |
| `GOOGLE_DRIVE_FOLDER_ID` | Root folder ID for document persistence | Drive folder hash | When using Drive |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth Client ID for cloud storage | `...apps.googleusercontent.com` | When using OAuth |
| `GOOGLE_DRIVE_CLIENT_SECRET` | OAuth Client Secret | Client secret string | When using OAuth |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Long-lived OAuth refresh token | Refresh token string | When using OAuth |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service Account JSON (alternative to OAuth) | Base64 or JSON string | Alternative |

### Frontend Configuration (Vercel Project Settings → Environment Variables)

| Variable | Description | Value | Required |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | Public endpoint of the backend API | `https://agent-pilot-api.onrender.com` | ✅ Yes |

> **Note for Local Development:** In `frontend/.env.local`, set:
> ```env
> NEXT_PUBLIC_API_URL=http://localhost:8000
> ```

---

## 3. Backend Deployment on Render

### Method A — Automated via Blueprint (`render.yaml`)

1. Push your repository to GitHub:
   ```bash
   git add -A
   git commit -m "feat: prepare production deployment"
   git push origin main
   ```
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** → **Blueprint**.
4. Select your `Agent-Pilot` repository. Render detects [`render.yaml`](../render.yaml) automatically.
5. In the service settings, provide your secret keys:
   - `NVIDIA_API_KEY`
   - `HF_API_TOKEN`
   - `FRONTEND_ORIGIN`: `https://agent-pilot-rust.vercel.app`
6. Click **Apply**.

### Method B — Manual Web Service Setup

1. In Render, select **New +** → **Web Service**.
2. Connect your `Agent-Pilot` repository.
3. Configure the runtime settings:
   - **Name**: `agent-pilot-api`
   - **Region**: Oregon (US West) or Frankfurt (EU Central)
   - **Branch**: `main`
   - **Root Directory**: `.` *(leave blank / project root)*
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     python -m uvicorn api_server:app --host 0.0.0.0 --port $PORT
     ```
   - **Plan**: `Free`
4. Add all environment variables listed in Section 2 under the **Environment** tab.
5. Click **Create Web Service**.
6. Note your service URL: `https://agent-pilot-api.onrender.com`.

---

## 4. Frontend Deployment on Vercel

1. Log in to [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New…** → **Project**.
3. Import your GitHub repository: `Agent-Pilot`.
4. Configure the project:
   - **Framework Preset**: Next.js (automatically detected)
   - **Root Directory**: Click *Edit* and select `frontend`
   - **Build Command**: `next build` (default)
   - **Output Directory**: `.next` (default)
5. Expand **Environment Variables** and add:
   - **Name**: `NEXT_PUBLIC_API_URL`
   - **Value**: `https://agent-pilot-api.onrender.com`
6. Click **Deploy**.
7. Once deployed, verify your live domain (e.g., `https://agent-pilot-rust.vercel.app`).

---

## 5. Connecting Frontend & Backend (CORS)

Agent-Pilot's backend includes dynamic CORS origin matching. To guarantee communication between your Vercel deployment and Render:

1. In Render Dashboard, ensure `FRONTEND_ORIGIN` matches your exact Vercel URL:
   ```text
   https://agent-pilot-rust.vercel.app
   ```
2. The backend also automatically allows:
   - All `*.vercel.app` preview deployments via regex (`r"https://.*\.vercel\.app"`)
   - `http://localhost:3000` and `http://127.0.0.1:3000` for seamless local testing.

---

## 6. Verification & Health Checks

Once both services are deployed:

1. **Verify Backend Health**:
   ```bash
   curl -s https://agent-pilot-api.onrender.com/health
   # Expected response: {"status":"ok","storage":{"backend":"...","status":"connected"}}
   ```

2. **Verify Interactive API Documentation**:
   Visit `https://agent-pilot-api.onrender.com/docs` to test Swagger UI endpoints.

3. **Verify Frontend UI**:
   - Open `https://agent-pilot-rust.vercel.app/`
   - Open **Cloud Hub** (modal should load your documents catalog)
   - Upload a test document (supports up to 500MB)
   - Create a chat thread and query the uploaded document.

---

## 7. Troubleshooting & Operational Notes

* **Render Free Tier Spin-Down**: Free Render instances sleep after 15 minutes of inactivity. The first request after a sleep period takes ~25–40 seconds to start the container. Subsequent requests execute instantly.
* **Large File Uploads (500MB)**: The backend supports files up to 500MB via `MAX_FILE_SIZE_MB`. For multi-hundred-megabyte files, ensure your network connection allows sufficient upload time.
* **Isolated Multi-Tenancy**: Documents and threads are securely partitioned by user identity (`sub`). Guest users only view documents uploaded in their guest session; authenticated users have their own private catalog.
