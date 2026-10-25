# Deployment Guide — Agent-Pilot

| Component | Platform | URL / Details | Tier |
|-----------|----------|---------------|------|
| **Production App (Full-Stack)** | [Cloudflare Workers](https://workers.cloudflare.com) | `https://agent-pilot.soapy-pint.workers.dev` | Free Edge Tier |
| **Edge Database** | [Cloudflare D1](https://developers.cloudflare.com/d1/) | `agent-pilot-db` (`4171929e-dd79-4d20-a973-6fbc74a5064f`) | Serverless SQL |
| **Backend API (Python / LangGraph)** | [Render](https://render.com) | `https://agent-pilot-api.onrender.com` | Free Web Service (Optional) |
| **Alternative Frontend UI** | [Vercel](https://vercel.com) | `https://agent-pilot-rust.vercel.app` | Free Hobby (Optional) |

---

## Primary Deployment: Cloudflare Workers + D1 (Active)

Agent-Pilot is deployed as a zero-cold-start, globally distributed application on Cloudflare Workers with static Next.js assets and Cloudflare D1.

### Step 1 — Build Frontend Static Export

```bash
cd frontend
npm install
npm run build
```
This generates the optimized production static export in `frontend/out` via Next.js (`output: "export"`).

### Step 2 — Initialize / Migrate Cloudflare D1 Database

From the `cloudflare` directory:

```bash
cd ../cloudflare
npm install
# Execute the schema against the remote Cloudflare D1 database
npx wrangler d1 execute agent-pilot-db --file=./schema.sql --remote
```

### Step 3 — Deploy Worker and Static Assets

```bash
npx wrangler deploy
```

`wrangler.toml` automatically uploads:
1. The TypeScript Hono API ([`cloudflare/src/index.ts`](file:///d:/Main/Projects/Agent-Pilot/cloudflare/src/index.ts))
2. Static assets directly from `../frontend/out`
3. Bindings for D1 database (`DB`) and environment secrets

### Live Deployment URL:
- **`https://agent-pilot.soapy-pint.workers.dev`**

---

## Alternative / Legacy Deployment: Render + Vercel

If running the Python LangGraph backend ([`api_server.py`](file:///d:/Main/Projects/Agent-Pilot/api_server.py)) alongside a Vercel-hosted frontend:

### Deploy Backend on Render
1. Connect GitHub repo: `Geetansh124/Agent-Pilot`.
2. Render reads [`render.yaml`](file:///d:/Main/Projects/Agent-Pilot/render.yaml) automatically and provisions `agent-pilot-api`.
3. Set environment variables (`NVIDIA_API_KEY`, `HF_API_TOKEN`, `FRONTEND_ORIGIN`).
4. Backend URL: `https://agent-pilot-api.onrender.com`

### Deploy Frontend on Vercel
1. Import repository in Vercel.
2. Root directory: `frontend`.
3. Set `NEXT_PUBLIC_API_URL`: `https://agent-pilot-api.onrender.com`.
4. Deploy to `https://agent-pilot-rust.vercel.app`.

---

## Verification & Health Check

Verify the Cloudflare deployment:
```bash
curl -s https://agent-pilot.soapy-pint.workers.dev/health
# Response: {"status":"ok","storage":{"backend":"d1","status":"connected"},"version":"1.2.0-cloudflare"}
```
