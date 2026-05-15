# Florida Stormwater Compliance Assistant API

AI-powered stormwater compliance guidance for Florida — FDEP NPDES (FLR10), MS4, ERP, site inspections, and BMP selection with Florida-specific hydrology and WMD rules.

**GitHub:** https://github.com/HeraDogAI/stormwater-api

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Status check |
| GET | `/health` | Health check |
| GET | `/topics` | Florida compliance topic areas |
| GET | `/wmds` | Water Management Districts + counties |
| POST | `/chat` | Ask a compliance question |

Interactive docs: `http://localhost:8000/docs`

---

## POST /chat

**Request:**
```json
{
  "message": "What BMPs do I need for a 5-acre construction site?",
  "county": "Brevard",
  "wmd": "SJRWMD",
  "history": []
}
```

**Response:**
```json
{
  "reply": "For a 5-acre site in Brevard County under SJRWMD...",
  "history": [
    { "role": "user", "content": "What BMPs do I need..." },
    { "role": "assistant", "content": "For a 5-acre site in Brevard..." }
  ]
}
```

Pass `history` from the previous response into the next request for multi-turn conversations.

---

## Local Setup

```bash
git clone https://github.com/HeraDogAI/stormwater-api.git
cd stormwater-api
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
uvicorn main:app --reload   # http://localhost:8000/docs
```

---

## Deploy to Railway via GitHub Actions

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/HeraDogAI/stormwater-api.git
git push -u origin main
```

### Step 2 — Create Railway project
1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Select `HeraDogAI/stormwater-api`
3. Railway auto-detects the Dockerfile — no extra config needed

### Step 3 — Set environment variables in Railway
In your Railway project → **Variables** tab, add:
```
ANTHROPIC_API_KEY   =  your_anthropic_key
APP_API_KEY         =  a_strong_random_string
ALLOWED_ORIGINS     =  https://yourdomain.com
```

### Step 4 — Add Railway token to GitHub Secrets
1. Railway → **Account Settings → Tokens → Create Token** → copy it
2. GitHub → `HeraDogAI/stormwater-api` → **Settings → Secrets → Actions → New secret**
   - Name: `RAILWAY_TOKEN`
   - Value: paste the token

### Step 5 — Done
Every push to `main` will:
1. Run syntax + import checks
2. Auto-deploy to Railway on success

---

## Example curl

```bash
curl -X POST https://your-app.railway.app/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_app_key" \
  -d '{
    "message": "How deep should silt fence be trenched in Florida?",
    "county": "Brevard",
    "wmd": "SJRWMD",
    "history": []
  }'
```
