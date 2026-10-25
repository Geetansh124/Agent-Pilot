# Production Deployment Guide — Agent-Pilot

This guide provides end-to-end instructions for deploying Agent-Pilot across production environments, including the **active Cloudflare Workers + D1** edge deployment and the **FastAPI + LangGraph** backend on **Render** with **Next.js** on **Vercel**.

---

## 1. System Architecture & Live Endpoints

| Component | Platform | URL / Endpoint | Tier / Notes |
|---|---|---|---|
| **Production App (Full-Stack)** | [Cloudflare Workers](https://workers.cloudflare.com) | `https://agent-pilot.soapy-pint.workers.dev` | **Active** — Edge API + Static Frontend Assets |
| **Edge Database** | [Cloudflare D1](https://developers.cloudflare.com/d1/) | `agent-pilot-db` (`4171929e-dd79-4d20-a973-6fbc74a5064f`) | Serverless Edge SQL |
| **Python Backend API** | [Render](https://render.com) | `https://agent-pilot-api.onrender.com` | Free Web Service (LangGraph & Local RAG) |
| **Alternative Frontend UI** | [Vercel](https://vercel.com) | `https://agent-pilot-rust.vercel.app/` | Free Hobby (Next.js Node runtime) |
| **Local Dev Backend** | Localhost | `http://localhost:8000` | Native FastAPI |
| **Local Dev Frontend** | Localhost | `http://localhost:3000` | Native Next.js |

---

## 2. Active Primary Deployment: Cloudflare Workers + D1

The live production application runs on **Cloudflare Workers** with zero cold starts, global replication, a Cloudflare D1 SQL database, and frontend static asset hosting.

### 2.1 Configuration Files
* **Worker Configuration**: [`cloudflare/wrangler.toml`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/wrangler.toml)
* **Worker Router & Handlers**: [`cloudflare/src/index.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/index.ts)
* **Database Schema**: [`cloudflare/schema.sql`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/schema.sql)
* **Static Asset Export**: `frontend/out`

### 2.2 Environment Variables & Secrets (Cloudflare)

Configured via `vars` in [`cloudflare/wrangler.toml`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/wrangler.toml) or Cloudflare Dashboard Secrets:

| Variable | Description |
|---|---|
| `NVIDIA_API_KEY` | NVIDIA NIM API key for LLM inference |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID for 1-click token verification |
| `JWT_SECRET` | Secret key for signing and verifying user auth tokens |

### 2.3 Deployment Steps

```bash
# 1. Build optimized static frontend export
cd frontend
npm install
npm run build

# 2. Deploy schema to remote Cloudflare D1 database (first time or schema changes)
cd ../cloudflare
npm install
npx wrangler d1 execute agent-pilot-db --file=./schema.sql --remote

# 3. Deploy Worker API and static assets
npx wrangler deploy
```

---

## 3. Alternative / Hybrid Deployment: Render (Python API) + Vercel

If you require the full Python ecosystem (in-process FAISS dense embeddings, BM25 sparse indexer, LangGraph state machine, and Google Drive cloud syncing):

### 3.1 Backend Configuration (Render Dashboard → Service → Environment)

| Variable | Description | Example / Default | Required |
|---|---|---|---|
| `NVIDIA_API_KEY` | NVIDIA NIM API key for LLM generation | `nvapi-...` | ✅ Yes |
| `HF_API_TOKEN` | Hugging Face token for embeddings | `hf_...` | ✅ Yes |
| `FRONTEND_ORIGIN` | Allowed production frontend origin for CORS | `https://agent-pilot.soapy-pint.workers.dev` | ✅ Yes |
| `MAX_FILE_SIZE_MB` | Maximum document upload size limit | `500` | Optional (default: `500`) |
| `JWT_SECRET_KEY` | Secret key for signing user auth tokens | `secure-random-token` | Recommended |
| `STORAGE_BACKEND` | Storage provider (`google_drive`, `aws`, `local`) | `google_drive` | Optional |
| `GOOGLE_DRIVE_FOLDER_ID` | Root folder ID for document persistence | Drive folder hash | When using Drive |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth Client ID for cloud storage | `...apps.googleusercontent.com` | When using OAuth |
| `GOOGLE_DRIVE_CLIENT_SECRET` | OAuth Client Secret | Client secret string | When using OAuth |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Long-lived OAuth refresh token | Refresh token string | When using OAuth |

### 3.2 Automated Deployment via Blueprint (`render.yaml`)

1. Push your repository to GitHub:
   ```bash
   git add -A
   git commit -m "feat: prepare production deployment"
   git push origin main
   ```
2. Log in to [Render Dashboard](https://dashboard.render.com/) → **New +** → **Blueprint**.
3. Select your `Agent-Pilot` repository. Render detects [`render.yaml`](file:///d:/Main/Projects/Agent-Pilot/render.yaml) automatically.
4. Set required secret keys and click **Apply**.
5. Live service URL: `https://agent-pilot-api.onrender.com`.

### 3.3 Frontend Deployment on Vercel

1. Log in to [Vercel Dashboard](https://vercel.com/dashboard) → **Add New…** → **Project**.
2. Import repository `Agent-Pilot` and set Root Directory to `frontend`.
3. Set environment variable:
   - `NEXT_PUBLIC_API_URL`: `https://agent-pilot-api.onrender.com` (or your Cloudflare worker URL)
4. Click **Deploy**. Live domain: `https://agent-pilot-rust.vercel.app`.

---

## 4. Connecting Services & CORS

Agent-Pilot's Python backend (`api_server.py`) includes dynamic CORS origin matching allowing:
* `https://agent-pilot.soapy-pint.workers.dev` (Active Cloudflare Worker domain)
* `*.workers.dev` and `*.pages.dev` domains
* `*.vercel.app` preview and production deployments
* `http://localhost:3000` and `http://localhost:3001` for local development

---

## 5. Verification & Health Checks

1. **Verify Cloudflare Worker Health**:
   ```bash
   curl -s https://agent-pilot.soapy-pint.workers.dev/health
   # Expected: {"status":"ok","storage":{"backend":"d1","status":"connected"},"version":"1.2.0-cloudflare"}
   ```

2. **Verify Render Python API Health**:
   ```bash
   curl -s https://agent-pilot-api.onrender.com/health
   # Expected: {"status":"ok","storage":{"backend":"...","status":"connected"}}
   ```

3. **Verify Interactive API Documentation**:
   Visit `https://agent-pilot-api.onrender.com/docs` to test Swagger UI endpoints.
