import json
import os
import requests
from datetime import datetime, timezone

# ─────────────────────────────────────────
# 资产配置：Yahoo Finance tickers
# ─────────────────────────────────────────
YAHOO_ASSETS = [
    # 股票指数
    {"key": "sp500",   "ticker": "^GSPC",   "name": "S&P 500",   "sub": "USA",        "section": "equities"},
    {"key": "nasdaq",  "ticker": "^IXIC",   "name": "NASDAQ",    "sub": "USA Tech",   "section": "equities"},
    {"key": "nikkei",  "ticker": "^N225",   "name": "Nikkei 225","sub": "Japan",      "section": "equities"},
    {"key": "csi1000", "ticker": "000852.SS","name": "CSI 1000",  "sub": "China",      "section": "equities"},
    {"key": "hsi",     "ticker": "^HSI",    "name": "Hang Seng", "sub": "Hong Kong",  "section": "equities"},
    {"key": "dax",     "ticker": "^GDAXI",  "name": "DAX",       "sub": "Germany",    "section": "equities"},
    # 债券收益率
    {"key": "ust10",   "ticker": "^TNX",    "name": "US 10Y Yield","sub": "Treasury", "section": "bonds"},
    {"key": "ust2",    "ticker": "^IRX",    "name": "US 2Y Yield", "sub": "Treasury", "section": "bonds"},
    {"key": "bund",    "ticker": "^TNX",    "name": "DE 10Y Bund", "sub": "Germany",  "section": "bonds"},  # fallback
    # 商品
    {"key": "gold",    "ticker": "GC=F",    "name": "Gold",      "sub": "XAU/USD",    "section": "commodities"},
    {"key": "silver",  "ticker": "SI=F",    "name": "Silver",    "sub": "XAG/USD",    "section": "commodities"},
    {"key": "wti",     "ticker": "CL=F",    "name": "WTI Crude", "sub": "Oil",        "section": "commodities"},
    {"key": "brent",   "ticker": "BZ=F",    "name": "Brent Crude","sub": "Oil",       "section": "commodities"},
    {"key": "copper",  "ticker": "HG=F",    "name": "Copper",    "sub": "LME",        "section": "commodities"},
    {"key": "natgas",  "ticker": "NG=F",    "name": "Natural Gas","sub": "NYMEX",     "section": "commodities"},
    # 外汇
    {"key": "eurusd",  "ticker": "EURUSD=X","name": "EUR/USD",   "sub": "Euro / Dollar","section": "fx"},
    {"key": "usdjpy",  "ticker": "JPY=X",   "name": "USD/JPY",   "sub": "Dollar / Yen", "section": "fx"},
    {"key": "gbpusd",  "ticker": "GBPUSD=X","name": "GBP/USD",   "sub": "Cable",        "section": "fx"},
    {"key": "dxy",     "ticker": "DX-Y.NYB","name": "DXY",       "sub": "Dollar Index", "section": "fx"},
    {"key": "usdcny",  "ticker": "CNY=X",   "name": "USD/CNY",   "sub": "Offshore CNH", "section": "fx"},
    {"key": "usdchf",  "ticker": "CHFUSD=X","name": "USD/CHF",   "sub": "Swissie",      "section": "fx"},
]

# 加密货币用 CoinGecko（更准）
CRYPTO_ASSETS = [
    {"key": "btc",  "cg_id": "bitcoin",  "name": "Bitcoin",  "sub": "BTC/USD"},
    {"key": "eth",  "cg_id": "ethereum", "name": "Ethereum", "sub": "ETH/USD"},
    {"key": "sol",  "cg_id": "solana",   "name": "Solana",   "sub": "SOL/USD"},
    {"key": "bnb",  "cg_id": "binancecoin","name": "BNB",    "sub": "BNB/USD"},
    {"key": "xrp",  "cg_id": "ripple",   "name": "XRP",      "sub": "XRP/USD"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fmt_price(val, ticker):
    """根据资产类型格式化价格"""
    if val is None:
        return "N/A"
    # 外汇和债券保留4位小数
    if any(x in ticker for x in ["=X", "=F", "^TNX", "^IRX", "^FVX"]):
        if val < 10:
            return f"{val:.4f}"
        return f"{val:.2f}"
    # 指数保留整数
    if val > 1000:
        return f"{val:,.0f}"
    return f"{val:.2f}"


def fmt_change(chg_pct, section):
    """格式化涨跌幅"""
    if chg_pct is None:
        return "N/A", True
    up = chg_pct >= 0
    sign = "+" if up else ""
    # 债券用 bp
    if section == "bonds":
        bp = round(chg_pct * 100)
        sign_bp = "+" if bp >= 0 else ""
        return f"{sign_bp}{bp}bp", up
    return f"{sign}{chg_pct:.2f}%", up


def fetch_yahoo_batch(tickers):
    """批量获取 Yahoo Finance 数据"""
    ticker_str = "%2C".join(tickers)
    url = (
        f"https://query1.finance.yahoo.com/v7/finance/quote"
        f"?symbols={ticker_str}&fields=regularMarketPrice,regularMarketChangePercent,"
        f"regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow,regularMarketChange"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        results = {}
        for item in data.get("quoteResponse", {}).get("result", []):
            symbol = item.get("symbol", "")
            results[symbol] = {
                "price": item.get("regularMarketPrice"),
                "chg_pct": item.get("regularMarketChangePercent"),
                "prev_close": item.get("regularMarketPreviousClose"),
                "high52": item.get("fiftyTwoWeekHigh"),
                "low52": item.get("fiftyTwoWeekLow"),
            }
        return results
    except Exception as e:
        print(f"Yahoo batch error: {e}")
        return {}


def fetch_coingecko():
    """获取加密货币数据"""
    ids = ",".join([a["cg_id"] for a in CRYPTO_ASSETS])
    url = (
        f"https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}&vs_currencies=usd"
        f"&include_24hr_change=true&include_24hr_vol=true"
        f"&include_7d_change=true"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        return resp.json()
    except Exception as e:
        print(f"CoinGecko error: {e}")
        return {}


def build_asset_item(asset_config, price_data, section):
    """构建单个资产的输出对象"""
    ticker = asset_config.get("ticker", "")
    d = price_data.get(ticker, {})
    price = d.get("price")
    chg_pct = d.get("chg_pct")
    high52 = d.get("high52")
    low52 = d.get("low52")

    price_str = fmt_price(price, ticker)
    chg_str, up = fmt_change(chg_pct, section)

    # 52周区间
    if high52 and low52:
        range52 = f"{fmt_price(low52, ticker)} – {fmt_price(high52, ticker)}"
    else:
        range52 = "N/A"

    return {
        "key": asset_config["key"],
        "name": asset_config["name"],
        "sub": asset_config["sub"],
        "price": price_str,
        "chg": chg_str,
        "up": up,
        "range52": range52,
        "raw_price": price,
        "raw_chg_pct": chg_pct,
    }


def fetch_assets():
    now = datetime.now(timezone.utc)
    print(f"Fetching assets at {now.isoformat()}")

    # ── Yahoo Finance ──
    tickers = [a["ticker"] for a in YAHOO_ASSETS]
    print(f"Fetching {len(tickers)} tickers from Yahoo Finance...")
    yahoo_data = fetch_yahoo_batch(tickers)
    print(f"Got {len(yahoo_data)} results")

    # ── CoinGecko ──
    print("Fetching crypto from CoinGecko...")
    cg_data = fetch_coingecko()

    # ── 整理分组 ──
    sections = {
        "equities":    {"title": "Equities 股票",      "items": []},
        "bonds":       {"title": "Bonds 债券",          "items": []},
        "commodities": {"title": "Commodities 商品",    "items": []},
        "crypto":      {"title": "Crypto 加密货币",     "items": []},
        "fx":          {"title": "FX 外汇",             "items": []},
    }

    # Yahoo 资产
    for asset in YAHOO_ASSETS:
        section = asset["section"]
        item = build_asset_item(asset, yahoo_data, section)
        sections[section]["items"].append(item)
        status = "✅" if item["raw_price"] else "⚠️"
        print(f"  {status} {asset['name']}: {item['price']} {item['chg']}")

    # 加密货币
    for asset in CRYPTO_ASSETS:
        cg = cg_data.get(asset["cg_id"], {})
        price = cg.get("usd")
        chg_pct = cg.get("usd_24h_change")
        up = (chg_pct or 0) >= 0
        sign = "+" if up else ""

        if price:
            if price >= 1000:
                price_str = f"${price:,.0f}"
            elif price >= 1:
                price_str = f"${price:.2f}"
            else:
                price_str = f"${price:.4f}"
        else:
            price_str = "N/A"

        chg_str = f"{sign}{chg_pct:.2f}%" if chg_pct is not None else "N/A"

        sections["crypto"]["items"].append({
            "key": asset["key"],
            "name": asset["name"],
            "sub": asset["sub"],
            "price": price_str,
            "chg": chg_str,
            "up": up,
            "range52": "N/A",
            "raw_price": price,
            "raw_chg_pct": chg_pct,
        })
        status = "✅" if price else "⚠️"
        print(f"  {status} {asset['name']}: {price_str} {chg_str}")

    # 输出结构
    output = {
        "updated_at": now.isoformat(),
        "updated_display": now.strftime("%b %d, %Y %H:%M UTC"),
        "sections": [
            sections["equities"],
            sections["bonds"],
            sections["commodities"],
            sections["crypto"],
            sections["fx"],
        ]
    }

    os.makedirs("data", exist_ok=True)
    with open("data/assets.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(s["items"]) for s in output["sections"])
    print(f"\n✅ Done: {total} assets saved to data/assets.json")
    print(f"   Updated: {output['updated_display']}")


if __name__ == "__main__":
    fetch_assets()
