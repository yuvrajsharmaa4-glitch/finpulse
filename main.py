"""
FinPulse Backend — FastAPI + Alpha Vantage + RSS News
Deploy on Railway.app (free tier)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import feedparser
import requests
import os
import re
from datetime import datetime, timezone

app = FastAPI(title="FinPulse API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

if os.path.exists("index.html"):
    @app.get("/")
    def serve_frontend():
        return FileResponse("index.html")

# Alpha Vantage API key
AV_KEY = "FO31V9J6JUUBYGP5"
AV_BASE = "https://www.alphavantage.co/query"

# News RSS feeds (free, no key needed)
NEWS_FEEDS = [
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US", "source": "Yahoo Finance"},
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters"},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "source": "CNBC"},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories", "source": "MarketWatch"},
]

def get_tag(title: str, summary: str) -> str:
    text = (title + " " + summary).lower()
    if any(w in text for w in ["bitcoin","crypto","ethereum","btc","eth","blockchain"]):
        return "Crypto"
    if any(w in text for w in ["gold","oil","silver","commodity","commodities","opec"]):
        return "Commodities"
    if any(w in text for w in ["gdp","inflation","fed","central bank","interest rate","recession","economy"]):
        return "Economy"
    if any(w in text for w in ["china","india","europe","uk","japan","germany","saudi","global","world"]):
        return "Global"
    if any(w in text for w in ["earnings","revenue","profit","quarterly","eps"]):
        return "Earnings"
    if any(w in text for w in ["nasdaq","s&p","dow","market","rally","selloff"]):
        return "Markets"
    return "Stocks"

def time_ago(published) -> str:
    try:
        if hasattr(published, 'tm_year'):
            pub = datetime(*published[:6], tzinfo=timezone.utc)
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

def fmt(n):
    try:
        n = float(n)
        if n >= 1e12: return f"${n/1e12:.2f}T"
        if n >= 1e9:  return f"${n/1e9:.2f}B"
        if n >= 1e6:  return f"${n/1e6:.2f}M"
        return f"{n:,.0f}"
    except:
        return "N/A"

@app.get("/api/health")
def health():
    return {"status": "ok", "message": "FinPulse API is running"}

@app.get("/api/news")
def get_market_news(limit: int = 20):
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
    seen, unique = set(), []
    for a in articles:
        key = a["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    return {"news": unique[:limit], "count": len(unique[:limit])}

@app.get("/api/stock/{symbol}")
def get_stock(symbol: str):
    sym = symbol.upper()
    try:
        # Get quote data
        quote_r = requests.get(AV_BASE, params={
            "function": "GLOBAL_QUOTE",
            "symbol": sym,
            "apikey": AV_KEY
        }, timeout=15)
        quote_data = quote_r.json().get("Global Quote", {})

        if not quote_data or not quote_data.get("05. price"):
            raise HTTPException(status_code=404, detail=f"No data found for {sym}. Check the ticker symbol.")

        price      = round(float(quote_data.get("05. price", 0)), 2)
        prev_close = round(float(quote_data.get("08. previous close", price)), 2)
        change     = round(float(quote_data.get("09. change", 0)), 2)
        change_pct = round(float(quote_data.get("10. change percent", "0%").replace("%", "")), 2)
        open_p     = round(float(quote_data.get("02. open", 0)), 2)
        high       = round(float(quote_data.get("03. high", 0)), 2)
        low        = round(float(quote_data.get("04. low", 0)), 2)
        volume     = fmt(quote_data.get("06. volume", 0))

        # Get company overview
        overview_r = requests.get(AV_BASE, params={
            "function": "OVERVIEW",
            "symbol": sym,
            "apikey": AV_KEY
        }, timeout=15)
        ov = overview_r.json() or {}

        name        = ov.get("Name", sym)
        sector      = ov.get("Sector", "")
        exchange    = ov.get("Exchange", "")
        description = (ov.get("Description", ""))[:300]
        market_cap  = fmt(ov.get("MarketCapitalization", 0))
        pe          = ov.get("PERatio", "N/A")
        eps         = ov.get("EPS", "N/A")
        week52_high = ov.get("52WeekHigh", "N/A")
        week52_low  = ov.get("52WeekLow", "N/A")
        dividend    = ov.get("DividendYield", "N/A")
        beta        = ov.get("Beta", "N/A")
        avg_volume  = fmt(ov.get("10DayAverageTradingVolume", 0))

        # Get daily history for charts (last 100 days)
        history_r = requests.get(AV_BASE, params={
            "function": "TIME_SERIES_DAILY",
            "symbol": sym,
            "outputsize": "compact",
            "apikey": AV_KEY
        }, timeout=15)
        daily_data = history_r.json().get("Time Series (Daily)", {})

        def build_history(days):
            bars = []
            sorted_dates = sorted(daily_data.keys())[-days:]
            for date_str in sorted_dates:
                d = daily_data[date_str]
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                bars.append({
                    "t": dt.strftime("%b %d"),
                    "o": round(float(d["1. open"]), 2),
                    "h": round(float(d["2. high"]), 2),
                    "l": round(float(d["3. low"]), 2),
                    "c": round(float(d["4. close"]), 2),
                    "v": int(d["5. volume"]),
                })
            return bars

        history_1m = build_history(30)
        history_3m = build_history(66)
        history_1y = build_history(252)

        # Intraday for 1D
        intra_r = requests.get(AV_BASE, params={
            "function": "TIME_SERIES_INTRADAY",
            "symbol": sym,
            "interval": "15min",
            "apikey": AV_KEY
        }, timeout=15)
        intra_data = intra_r.json().get("Time Series (15min)", {})
        history_1d = []
        for ts_str in sorted(intra_data.keys())[-26:]:
            d = intra_data[ts_str]
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            history_1d.append({
                "t": dt.strftime("%H:%M"),
                "o": round(float(d["1. open"]), 2),
                "h": round(float(d["2. high"]), 2),
                "l": round(float(d["3. low"]), 2),
                "c": round(float(d["4. close"]), 2),
                "v": int(d["5. volume"]),
            })

        # News from Alpha Vantage
        news_r = requests.get(AV_BASE, params={
            "function": "NEWS_SENTIMENT",
            "tickers": sym,
            "limit": 4,
            "apikey": AV_KEY
        }, timeout=15)
        news_items = []
        for item in news_r.json().get("feed", [])[:4]:
            news_items.append({
                "title":   item.get("title", ""),
                "source":  item.get("source", ""),
                "time":    item.get("time_published", "")[:10],
                "summary": item.get("summary", "")[:200],
            })

        return {
            "symbol":        sym,
            "name":          name,
            "price":         price,
            "change":        change,
            "changePercent": change_pct,
            "open":          open_p,
            "high":          high,
            "low":           low,
            "volume":        volume,
            "avgVolume":     avg_volume,
            "marketCap":     market_cap,
            "pe":            pe,
            "eps":           eps,
            "week52High":    week52_high,
            "week52Low":     week52_low,
            "dividend":      dividend,
            "beta":          beta,
            "sector":        sector,
            "exchange":      exchange,
            "description":   description,
            "news":          news_items,
            "history": {
                "1D":  history_1d,
                "5D":  build_history(5),
                "1M":  history_1m,
                "3M":  history_3m,
                "1Y":  history_1y,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for {sym}: {str(e)}")

@app.get("/api/market")
def get_market_overview():
    symbols = {
        "S&P 500": "SPY", "NASDAQ": "QQQ", "Dow Jones": "DIA",
        "Gold": "GLD", "Oil WTI": "USO", "BTC/USD": "BTC-USD",
        "NVIDIA": "NVDA", "Apple": "AAPL", "Tesla": "TSLA",
        "Microsoft": "MSFT", "Amazon": "AMZN", "Meta": "META",
    }
    result = []
    for name, sym in symbols.items():
        try:
            r = requests.get(AV_BASE, params={
                "function": "GLOBAL_QUOTE",
                "symbol": sym,
                "apikey": AV_KEY
            }, timeout=10)
            q = r.json().get("Global Quote", {})
            price     = round(float(q.get("05. price", 0)), 2)
            chg_pct   = round(float(q.get("10. change percent", "0%").replace("%", "")), 2)
            direction = "u" if chg_pct >= 0 else "d"
            chg_str   = f"+{chg_pct:.2f}%" if chg_pct >= 0 else f"{chg_pct:.2f}%"
            result.append({"name": name, "symbol": sym, "price": price, "change": chg_str, "direction": direction})
        except:
            result.append({"name": name, "symbol": sym, "price": "—", "change": "—", "direction": "u"})
    return {"markets": result}

@app.get("/api/movers")
def get_movers():
    symbols = ["AAPL","MSFT","NVDA","TSLA","AMZN","GOOGL","META","NFLX","AMD","JPM"]
    gainers, losers = [], []
    for sym in symbols:
        try:
            r = requests.get(AV_BASE, params={
                "function": "GLOBAL_QUOTE",
                "symbol": sym,
                "apikey": AV_KEY
            }, timeout=10)
            q = r.json().get("Global Quote", {})
            price   = round(float(q.get("05. price", 0)), 2)
            chg_pct = round(float(q.get("10. change percent", "0%").replace("%", "")), 2)
            entry   = {"symbol": sym, "name": sym, "price": price, "changePct": chg_pct}
            gainers.append(entry) if chg_pct >= 0 else losers.append(entry)
        except:
            continue
    gainers.sort(key=lambda x: x["changePct"], reverse=True)
    losers.sort(key=lambda x: x["changePct"])
    return {"gainers": gainers[:6], "losers": losers[:6]}
