# Deployment Guide — Agent-Pilot (100% Free)

| Component | Platform | Tier |
|-----------|----------|------|
| **Backend** (FastAPI + LangGraph) | [Render](https://render.com) | Free Web Service |
| **Frontend** (Next.js) | [Vercel](https://vercel.com) | Free Hobby |

---

## Step 1 — Push Code to GitHub

Make sure your latest code is pushed:

```bash
git add -A
git commit -m "prep: deployment config"
git push origin main
```

---

## Step 2 — Deploy Backend on Render (Free)

1. Go to [render.com](https://dashboard.render.com/) → **New** → **Blueprint**.
2. Connect your GitHub repo: `Geetansh124/Agent-Pilot`.
3. Render reads `render.yaml` automatically and creates the **docupilot-api** service.
4. **Set secret environment variables** in the Render dashboard → Service → **Environment** tab:

   | Key | Value | Required |
   |-----|-------|----------|
   | `NVIDIA_API_KEY` | Your NVIDIA API key | ✅ Yes |
   | `HF_API_TOKEN` | Your HuggingFace token | ✅ Yes |
   | `FRONTEND_ORIGIN` | *(set after Step 3)* | ✅ Yes |
   | `ALPHAVANTAGE_API_KEY` | Your AlphaVantage key | Optional |

5. Click **Save Changes** — Render will build and deploy.
6. Note your backend URL: `https://docupilot-api.onrender.com`

> **Note:** Render free tier spins down after 15 min of inactivity. First request after sleep takes ~30–60s.

---

## Step 3 — Deploy Frontend on Vercel (Free)

1. Go to [vercel.com](https://vercel.com/dashboard) → **Add New** → **Project**.
2. Import your GitHub repo: `Geetansh124/Agent-Pilot`.
3. Configure:
   - **Framework Preset**: Next.js
   - **Root Directory**: `frontend`
4. **Environment Variables** → add:

   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_API_URL` | `https://docupilot-api.onrender.com` |

5. Click **Deploy**.
6. Note your frontend URL: `https://your-project.vercel.app`

---

## Step 4 — Connect Frontend ↔ Backend (CORS)

1. Go back to **Render** → your `docupilot-api` service → **Environment**.
2. Set `FRONTEND_ORIGIN` to your Vercel URL:
   ```
   https://your-project.vercel.app
   ```
3. Save → Render auto-redeploys with the updated CORS origin.

---

## Step 5 — Verify

1. Open your Vercel frontend URL in a browser.
2. Create a new chat thread and send a message.
3. Upload a PDF and ask questions about it.

If the backend returns errors, check Render logs: **Dashboard → docupilot-api → Logs**.

---

## Optional: AWS Storage (S3 + DynamoDB)

If you want cloud document persistence, add these secrets in Render:

| Key | Value |
|-----|-------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key |

The bucket (`docupilot-327514289233-us-east-1`) and table (`docupilot-documents`) are already configured in `render.yaml`.
