"""
FinPulse Backend — FastAPI + yfinance + RSS News
Deploy on Railway.app or Render.com (free tier)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yfinance as yf
import feedparser
import os
import re
from datetime import datetime, timezone
from typing import Optional

app = FastAPI(title="FinPulse API", version="1.0.0")

# ── CORS: allow your Netlify frontend to call this backend ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your Netlify URL in production e.g. ["https://your-app.netlify.app"]
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Serve frontend if index.html exists in same folder ──
if os.path.exists("index.html"):
    @app.get("/")
    def serve_frontend():
        return FileResponse("index.html")


# ──────────────────────────────────────────
# FREE RSS NEWS FEEDS (no API key needed)
# ──────────────────────────────────────────
NEWS_FEEDS = [
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US", "source": "Yahoo Finance"},
    {"url": "https://www.investing.com/rss/news.rss",                                         "source": "Investing.com"},
    {"url": "https://feeds.reuters.com/reuters/businessNews",                                  "source": "Reuters"},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",                          "source": "CNBC"},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories",                            "source": "MarketWatch"},
    {"url": "https://www.ft.com/?format=rss",                                                  "source": "FT"},
]

def get_tag(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    if any(w in text for w in ["bitcoin","crypto","ethereum","btc","eth","blockchain"]):
        return "Crypto"
    if any(w in text for w in ["gold","oil","silver","commodity","commodities","opec","brent","wti"]):
        return "Commodities"
    if any(w in text for w in ["gdp","inflation","fed","central bank","interest rate","recession","unemployment","economy","fiscal","monetary"]):
        return "Economy"
    if any(w in text for w in ["china","india","europe","uk","japan","germany","france","saudi","uae","middle east","emerging","global","world"]):
        return "Global"
    if any(w in text for w in ["earnings","revenue","profit","quarterly","eps","beats","misses","guidance"]):
        return "Earnings"
    if any(w in text for w in ["nasdaq","s&p","dow","market","stocks","shares","rally","selloff","ipo","index"]):
        return "Markets"
    return "Stocks"

def time_ago(published) -> str:
    try:
        import time
        ts = published
        if hasattr(ts, 'tm_year'):
            pub = datetime(*ts[:6], tzinfo=timezone.utc)
        else:
            pub = datetime.now(timezone.utc)
        diff = datetime.now(timezone.utc) - pub
        h = int(diff.total_seconds() // 3600)
        if h == 0:
            m = int(diff.total_seconds() // 60)
            return f"{m}m ago"
        if h < 24:
            return f"{h}h ago"
        return f"{h//24}d ago"
    except:
        return "recently"

def clean(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200] + "..." if len(text) > 200 else text


# ──────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────

@app.get("/api/news")
def get_market_news(limit: int = 20):
    """
    Fetch global finance & market news from free RSS feeds.
    No API key required.
    """
    articles = []
    for feed_info in NEWS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:5]:
                title   = clean(entry.get("title", ""))
                summary = clean(entry.get("summary", entry.get("description", "")))
                if not title:
                    continue
                articles.append({
                    "title":   title,
                    "summary": summary,
                    "source":  feed_info["source"],
                    "time":    time_ago(entry.get("published_parsed")),
                    "link":    entry.get("link", ""),
                    "tag":     get_tag(title, summary),
                })
        except Exception:
            continue

    # Deduplicate by title similarity
    seen, unique = set(), []
    for a in articles:
        key = a["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return {"news": unique[:limit], "count": len(unique[:limit])}


@app.get("/api/stock/{symbol}")
def get_stock(symbol: str):
    """
    Fetch live stock data using yfinance (free, no API key).
    Returns price, change, stats, company info and recent news.
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        info   = ticker.info or {}

        # Price data
        price        = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev_close   = info.get("previousClose") or info.get("regularMarketPreviousClose") or price
        change       = round(price - prev_close, 2)
        change_pct   = round((change / prev_close) * 100, 2) if prev_close else 0

        # Format large numbers
        def fmt(n):
            if not n: return "N/A"
            if n >= 1e12: return f"${n/1e12:.2f}T"
            if n >= 1e9:  return f"${n/1e9:.2f}B"
            if n >= 1e6:  return f"${n/1e6:.2f}M"
            return f"{n:,.0f}"

        # Stock-specific news from yfinance
        raw_news = ticker.news or []
        news_items = []
        for n in raw_news[:4]:
            content = n.get("content", {})
            news_items.append({
                "title":   content.get("title", n.get("title", "")),
                "source":  content.get("provider", {}).get("displayName", "Yahoo Finance") if isinstance(content.get("provider"), dict) else "Yahoo Finance",
                "time":    "recent",
                "summary": clean(content.get("summary", n.get("summary", ""))),
            })

        # Historical OHLCV for chart
        period_map = {"1D": "1d", "5D": "5d", "1M": "1mo", "3M": "3mo", "1Y": "1y"}
        interval_map = {"1D": "5m", "5D": "30m", "1M": "1d", "3M": "1d", "1Y": "1wk"}

        def get_history(range_key):
            try:
                hist = ticker.history(
                    period=period_map[range_key],
                    interval=interval_map[range_key],
                    auto_adjust=True
                )
                if hist.empty:
                    return []
                bars = []
                for ts, row in hist.iterrows():
                    if range_key == "1D":
                        lbl = ts.strftime("%H:%M")
                    elif range_key == "1Y":
                        lbl = ts.strftime("%b %y")
                    else:
                        lbl = ts.strftime("%b %d")
                    bars.append({
                        "t": lbl,
                        "o": round(float(row["Open"]),  2),
                        "h": round(float(row["High"]),  2),
                        "l": round(float(row["Low"]),   2),
                        "c": round(float(row["Close"]), 2),
                        "v": int(row["Volume"]),
                    })
                return bars
            except:
                return []

        # Build response
        return {
            "symbol":        info.get("symbol", symbol.upper()),
            "name":          info.get("longName") or info.get("shortName") or symbol,
            "price":         round(price, 2),
            "change":        change,
            "changePercent": change_pct,
            "open":          round(info.get("open") or info.get("regularMarketOpen") or 0, 2),
            "high":          round(info.get("dayHigh") or info.get("regularMarketDayHigh") or 0, 2),
            "low":           round(info.get("dayLow")  or info.get("regularMarketDayLow")  or 0, 2),
            "volume":        fmt(info.get("volume") or info.get("regularMarketVolume")),
            "avgVolume":     fmt(info.get("averageVolume")),
            "marketCap":     fmt(info.get("marketCap")),
            "pe":            round(info.get("trailingPE") or 0, 2),
            "eps":           round(info.get("trailingEps") or 0, 2),
            "week52High":    round(info.get("fiftyTwoWeekHigh") or 0, 2),
            "week52Low":     round(info.get("fiftyTwoWeekLow")  or 0, 2),
            "dividend":      str(round(info.get("dividendYield") or 0, 4) * 100) + "%" if info.get("dividendYield") else "N/A",
            "beta":          round(info.get("beta") or 0, 2),
            "sector":        info.get("sector", ""),
            "exchange":      info.get("exchange", ""),
            "description":   (info.get("longBusinessSummary") or "")[:300],
            "news":          news_items,
            "history": {
                "1D":  get_history("1D"),
                "5D":  get_history("5D"),
                "1M":  get_history("1M"),
                "3M":  get_history("3M"),
                "1Y":  get_history("1Y"),
            }
        }

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for {symbol}: {str(e)}")


@app.get("/api/market")
def get_market_overview():
    """
    Fetch live prices for major indices and assets.
    """
    symbols = {
        "S&P 500":    "^GSPC",
        "NASDAQ":     "^IXIC",
        "Dow Jones":  "^DJI",
        "Russell 2K": "^RUT",
        "VIX":        "^VIX",
        "Gold":       "GC=F",
        "Oil WTI":    "CL=F",
        "BTC/USD":    "BTC-USD",
        "EUR/USD":    "EURUSD=X",
        "10Y Yield":  "^TNX",
        "GBP/USD":    "GBPUSD=X",
        "Silver":     "SI=F",
    }
    result = []
    for name, sym in symbols.items():
        try:
            t    = yf.Ticker(sym)
            info = t.fast_info
            price      = round(float(info.last_price or 0), 2)
            prev       = round(float(info.previous_close or price), 2)
            chg_pct    = round(((price - prev) / prev) * 100, 2) if prev else 0
            direction  = "u" if chg_pct >= 0 else "d"
            chg_str    = f"+{chg_pct:.2f}%" if chg_pct >= 0 else f"{chg_pct:.2f}%"
            result.append({"name": name, "symbol": sym, "price": price, "change": chg_str, "direction": direction})
        except:
            result.append({"name": name, "symbol": sym, "price": "—", "change": "—", "direction": "u"})
    return {"markets": result}


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "FinPulse API is running"}


@app.get("/api/movers")
def get_movers():
    """Top gainers and losers from a watchlist of popular stocks."""
    symbols = ["AAPL","MSFT","NVDA","TSLA","AMZN","GOOGL","META","NFLX","AMD","JPM","BRKB","DIS","PYPL","INTC","CRM"]
    gainers, losers = [], []
    for sym in symbols:
        try:
            t    = yf.Ticker(sym)
            info = t.fast_info
            price   = round(float(info.last_price or 0), 2)
            prev    = round(float(info.previous_close or price), 2)
            chg_pct = round(((price - prev) / prev) * 100, 2) if prev else 0
            name    = t.info.get("shortName", sym)
            entry   = {"symbol": sym, "name": name, "price": price, "changePct": chg_pct}
            gainers.append(entry) if chg_pct >= 0 else losers.append(entry)
        except:
            continue
    gainers.sort(key=lambda x: x["changePct"], reverse=True)
    losers.sort(key=lambda x: x["changePct"])
    return {"gainers": gainers[:6], "losers": losers[:6]}
