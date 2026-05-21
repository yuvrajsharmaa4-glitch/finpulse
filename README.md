# FinPulse — Deployment Guide

## Files in this folder
| File | Purpose |
|------|---------|
| main.py | FastAPI backend (stock data + news) |
| requirements.txt | Python packages |
| Procfile | Tells Railway/Render how to run the app |
| index.html | Frontend (upload to Netlify) |

---

## STEP 1 — Deploy Backend on Railway (free)

1. Go to https://railway.app and sign up (free)
2. Click "New Project" → "Deploy from GitHub"
3. Upload these files to a new GitHub repo, then connect it
   OR use Railway CLI:
   ```
   npm install -g @railway/cli
   railway login
   railway init
   railway up
   ```
4. Railway will auto-detect the Procfile and deploy
5. Go to your project → Settings → Networking → Generate Domain
6. Copy your domain e.g. https://finpulse-backend.railway.app

---

## STEP 2 — Update Frontend with your Backend URL

Open index.html and find this line near the top of the script:

```js
const API = "https://YOUR-BACKEND.railway.app";
```

Replace it with your actual Railway URL:

```js
const API = "https://finpulse-backend.railway.app";
```

---

## STEP 3 — Deploy Frontend on Netlify (free)

1. Go to https://app.netlify.com/drop
2. Drag and drop your index.html file
3. You instantly get a live URL like https://your-app.netlify.app
4. Share that link with anyone!

---

## API Endpoints (what the backend does)

| Endpoint | Description |
|----------|-------------|
| GET /api/stock/AAPL | Live price, stats, history, news for any ticker |
| GET /api/news | Finance & global news from RSS feeds |
| GET /api/market | Live indices (S&P, NASDAQ, DOW, Gold, etc.) |
| GET /api/movers | Top gainers and losers |
| GET /api/health | Check if backend is running |

Test your backend at: https://your-backend.railway.app/docs

---

## Data Sources (all FREE, no API key needed)
- Stock data: yfinance (Yahoo Finance)
- Market news: RSS feeds from Reuters, CNBC, MarketWatch, FT
- No paid subscriptions required

---

## Optional: Run Locally First

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://localhost:8000 in your browser.
Test the API at http://localhost:8000/docs

For local frontend, change:
```js
const API = "http://localhost:8000";
```
