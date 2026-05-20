"""
PSE Daily Stock Newsletter
- Stock data: phisix-api3.appspot.com
- Price history: accumulated daily in data/history.csv
- Insights: Claude Haiku API
- Delivery: Resend

Setup:
  1. pip install google-genai matplotlib requests resend yfinance
  2. Sign up at resend.com and create an API key.
  3. Set environment variables (or edit the CONFIG section below).
  4. Run: python newsletter.py
"""

import base64
import csv
import io
import json
import os
import re
import urllib.request
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

# ─── CONFIG ──────────────────────────────────────────────────────────────────

# Get your API key at resend.com → API Keys
RESEND_API_KEY    = os.environ.get("RESEND_API_KEY", "")
# Use your verified domain, e.g. "PSE Newsletter <newsletter@yourdomain.com>"
# On the free tier without a domain, use "onboarding@resend.dev" (sends to your own email only)
EMAIL_FROM        = os.environ.get("EMAIL_FROM", "onboarding@resend.dev")
EMAIL_TO          = os.environ.get("EMAIL_TO", "your_email@gmail.com")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

STOCK_WATCHLIST = ["ALI", "AREIT", "BDO", "BPI", "JFC", "MBT", "MREIT", "RCR", "SMPH"]

TOP_N = 10

PSE_INDEX_TICKER = "PSEi.PS"
HISTORY_FILE = Path(__file__).parent / "data" / "history.csv"
HISTORY_DAYS = 60

# ─────────────────────────────────────────────────────────────────────────────


# ─── Data fetching ────────────────────────────────────────────────────────────

def fetch_pse_stocks() -> tuple[dict[str, dict], str]:
    raw = json.loads(
        urllib.request.urlopen("https://phisix-api3.appspot.com/stocks.json", timeout=15).read()
    )
    try:
        as_of = datetime.fromisoformat(raw.get("as_of", "")).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        as_of = raw.get("as_of", "")

    stocks: dict[str, dict] = {}
    for s in raw["stocks"]:
        price = s["price"]["amount"]
        pct = s["percentChange"]
        prev_close = price / (1 + pct / 100) if pct != -100 else price
        stocks[s["symbol"]] = {
            "symbol": s["symbol"],
            "name": s["name"],
            "price": price,
            "pct": pct,
            "change": price - prev_close,
            "volume": s["volume"],
        }
    return stocks, as_of


def fetch_index_history() -> tuple[list[str], list[float]]:
    """Fetch 60-day PSEi closing prices + dates from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{PSE_INDEX_TICKER}?interval=1d&range=2mo"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        result = r.json()["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        pairs = [(ts, c) for ts, c in zip(timestamps, closes) if c is not None]
        dates = [datetime.fromtimestamp(ts).strftime("%b %d") for ts, _ in pairs]
        prices = [c for _, c in pairs]
        return dates, prices
    except Exception:
        return [], []


def fetch_index() -> dict | None:
    try:
        info = yf.Ticker(PSE_INDEX_TICKER).fast_info
        price, prev = info.last_price, info.previous_close
        if not price or not prev:
            return None
        change = price - prev
        return {"price": price, "change": change, "pct": (change / prev) * 100}
    except Exception:
        return None


# ─── Price history (accumulated daily) ───────────────────────────────────────

def update_history(stocks: dict[str, dict]) -> None:
    """Append today's prices for ALL PSE stocks to data/history.csv, keeping last 90 rows."""
    today = datetime.now().strftime("%Y-%m-%d")
    HISTORY_FILE.parent.mkdir(exist_ok=True)

    all_symbols = sorted(stocks.keys())

    rows: list[dict] = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, newline="") as f:
            rows = list(csv.DictReader(f))

    if rows and rows[-1].get("date") == today:
        return

    row = {"date": today, **{sym: stocks[sym]["price"] for sym in all_symbols}}
    rows.append(row)
    rows = rows[-HISTORY_DAYS:]

    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date"] + all_symbols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_history(symbol: str) -> tuple[list[str], list[float]]:
    """Return (dates, prices) for symbol from history CSV."""
    if not HISTORY_FILE.exists():
        return [], []
    with open(HISTORY_FILE, newline="") as f:
        rows = list(csv.DictReader(f))
    dates, prices = [], []
    for row in rows:
        try:
            prices.append(float(row.get(symbol, "")))
            dates.append(datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d"))
        except (ValueError, TypeError):
            pass
    return dates, prices


# ─── Chart generation ─────────────────────────────────────────────────────────

def _encode_fig(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def make_sparkline(symbol: str) -> bytes | None:
    dates, prices = load_history(symbol)
    if len(prices) < 2:
        return None

    color = "#16a34a" if prices[-1] >= prices[0] else "#dc2626"
    xs = range(len(prices))
    fig, ax = plt.subplots(figsize=(2.8, 0.9))
    ax.plot(xs, prices, color=color, linewidth=1.5)
    ax.fill_between(xs, prices, min(prices), alpha=0.12, color=color)
    ax.set_xlim(0, len(prices) - 1)
    ax.set_xticks([0, len(prices) - 1])
    ax.set_xticklabels([dates[0], dates[-1]], fontsize=6, color="#9ca3af")
    ax.tick_params(axis="x", length=0, pad=2)
    ax.yaxis.set_visible(False)
    ax.spines[:].set_visible(False)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    plt.tight_layout(pad=0.2)
    return _encode_fig(fig)


def make_index_chart(dates: list[str], prices: list[float]) -> bytes | None:
    if len(prices) < 2:
        return None
    color = "#16a34a" if prices[-1] >= prices[0] else "#dc2626"
    xs = range(len(prices))
    fig, ax = plt.subplots(figsize=(5.8, 1.5))
    ax.plot(xs, prices, color=color, linewidth=1.8)
    ax.fill_between(xs, prices, min(prices), alpha=0.10, color=color)
    ax.set_xlim(0, len(prices) - 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    n = len(dates)
    tick_idx = [0] + [int(n * i / 4) for i in range(1, 4)] + [n - 1]
    tick_idx = sorted(set(tick_idx))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([dates[i] for i in tick_idx], fontsize=7, color="#9ca3af")
    ax.tick_params(axis="x", length=0, pad=3)
    ax.tick_params(axis="y", labelsize=7, length=2)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#e5e7eb")
    ax.grid(axis="y", color="#f3f4f6", linewidth=0.8)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    plt.tight_layout(pad=0.3)
    return _encode_fig(fig)


def bytes_to_data_uri(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


# ─── AI insights ─────────────────────────────────────────────────────────────

def generate_index_insight(index: dict) -> str:
    if not GROQ_API_KEY or not index:
        return ""
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%B %d, %Y")
    direction = "up" if index["pct"] >= 0 else "down"
    prompt = (
        f"You are a Philippine stock market analyst writing for a daily email newsletter. "
        f"Today is {today}. The PSE Composite Index closed at {index['price']:,.2f}, "
        f"{direction} {abs(index['change']):,.2f} points ({index['pct']:+.2f}%) for the day. "
        f"Write 2–3 sentences explaining the likely drivers behind today's overall market movement. "
        f"Consider: regional market trends, US market overnight performance, peso/dollar movement, "
        f"BSP monetary policy stance, foreign fund flows, and any broad macro factors relevant to "
        f"the Philippine market. Be specific and analytical, not generic."
    )
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  Index insight failed: {e}")
        return ""


def generate_insights(stocks: list[dict]) -> dict[str, str]:
    if not GROQ_API_KEY:
        print("  Skipping insights: GROQ_API_KEY not set")
        return {}
    if not stocks:
        return {}

    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%B %d, %Y")
    stock_lines = "\n".join(
        f"- {s['symbol']} ({s['name']}): {s['pct']:+.2f}%, price ₱{s['price']:,.2f}"
        for s in stocks
    )
    prompt = (
        f"You are a Philippine stock market analyst writing for a daily email newsletter. "
        f"Today is {today}. For each PSE-listed stock below, write 2–3 sentences explaining "
        f"the likely reason for today's price movement. Go beyond the obvious — explain the "
        f"underlying cause: e.g. for REITs mention interest rate sensitivity and yield "
        f"expectations; for banks mention lending margins or macro conditions; for property "
        f"mention demand drivers or rate environment; for mining mention commodity prices. "
        f"Be specific to the sector and Philippine market context. "
        f"Do not speculate on unverified company-specific news.\n\n"
        f"Stocks:\n{stock_lines}\n\n"
        f"Return a JSON object only — keys are stock symbols, values are insight strings. "
        f"No markdown, no extra text."
    )
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        text = response.choices[0].message.content.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        print(f"  Insight parsing failed — unexpected response format. First 200 chars: {text[:200]!r}")
    except Exception as e:
        print(f"  Insight generation failed: {e}")
    return {}


# ─── HTML helpers ─────────────────────────────────────────────────────────────

def _color(pct: float) -> str:
    return "#16a34a" if pct >= 0 else "#dc2626"

def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"

def _sign(val: float) -> str:
    return "+" if val >= 0 else ""

def _img(src: str, width: int, height: int) -> str:
    return (
        f"<img src='{src}' width='{width}' height='{height}' "
        f"style='display:block;' alt='' />"
    )

def _stock_row(d: dict, insight: str | None = None, chart_src: str | None = None,
               rank: int | None = None) -> str:
    color = _color(d["pct"])
    rank_cell = (
        f"<td style='padding:7px 10px;color:#9ca3af;font-size:13px;vertical-align:top;'>{rank}</td>"
        if rank is not None else ""
    )
    insight_html = (
        f"<div style='font-size:11px;color:#6b7280;font-style:italic;margin-top:3px;line-height:1.4;'>"
        f"{insight}</div>"
        if insight else ""
    )
    chart_cell = (
        f"<td style='padding:7px 10px;vertical-align:middle;'>{_img(chart_src, 140, 36)}</td>"
        if chart_src else ""
    )
    return (
        f"<tr style='border-bottom:1px solid #f3f4f6;'>"
        f"{rank_cell}"
        f"<td style='padding:7px 10px;vertical-align:top;'>"
        f"<div style='font-weight:700;font-size:13px;'>{d['symbol']}</div>"
        f"<div style='font-size:11px;color:#9ca3af;overflow:hidden;text-overflow:ellipsis;"
        f"white-space:nowrap;max-width:180px;'>{d['name']}</div>"
        f"{insight_html}"
        f"</td>"
        f"<td style='padding:7px 10px;text-align:right;font-size:13px;vertical-align:top;'>"
        f"₱{d['price']:,.2f}</td>"
        f"<td style='padding:7px 10px;text-align:right;color:{color};font-weight:700;"
        f"font-size:13px;vertical-align:top;'>"
        f"{_arrow(d['pct'])} {_sign(d['change'])}{d['change']:,.2f}</td>"
        f"<td style='padding:7px 10px;text-align:right;color:{color};font-weight:700;"
        f"font-size:13px;vertical-align:top;'>"
        f"{_sign(d['pct'])}{d['pct']:.2f}%</td>"
        f"{chart_cell}"
        f"</tr>"
    )


def _stock_table(rows_html: str, include_rank: bool = False, include_chart_col: bool = False) -> str:
    rank_th = (
        "<th style='padding:6px 10px;text-align:left;color:#9ca3af;font-weight:500;font-size:12px;'>#</th>"
        if include_rank else ""
    )
    chart_th = (
        "<th style='padding:6px 10px;text-align:left;color:#9ca3af;font-weight:500;font-size:12px;'>90d</th>"
        if include_chart_col else ""
    )
    return (
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead><tr style='background:#f9fafb;'>"
        f"{rank_th}"
        f"<th style='padding:6px 10px;text-align:left;color:#9ca3af;font-weight:500;font-size:12px;'>Stock</th>"
        f"<th style='padding:6px 10px;text-align:right;color:#9ca3af;font-weight:500;font-size:12px;'>Price</th>"
        f"<th style='padding:6px 10px;text-align:right;color:#9ca3af;font-weight:500;font-size:12px;'>Change</th>"
        f"<th style='padding:6px 10px;text-align:right;color:#9ca3af;font-weight:500;font-size:12px;'>%</th>"
        f"{chart_th}"
        f"</tr></thead><tbody>{rows_html}</tbody></table>"
    )


def _section(title: str, content: str) -> str:
    return (
        f"<div style='margin-bottom:28px;'>"
        f"<h2 style='margin:0 0 12px;font-size:15px;font-weight:700;color:#111827;"
        f"border-bottom:2px solid #e5e7eb;padding-bottom:8px;text-transform:uppercase;"
        f"letter-spacing:0.05em;'>{title}</h2>"
        f"{content}"
        f"</div>"
    )


# ─── HTML assembly ────────────────────────────────────────────────────────────

def build_html(
    index: dict | None,
    all_stocks: dict[str, dict],
    insights: dict[str, str],
    sparklines: dict[str, str | None],
    as_of: str,
    index_chart_src: str | None = None,
    index_insight: str = "",
) -> str:
    today = datetime.now().strftime("%B %d, %Y")

    # ── PSEi banner ──
    if index:
        idx_color = _color(index["pct"])
        idx_chart_html = (
            f"<div style='margin-top:10px;'>{_img(index_chart_src, 620, 84)}</div>"
            if index_chart_src else ""
        )
        idx_insight_html = (
            f"<div style='font-size:12px;color:#4b5563;margin-top:10px;line-height:1.6;'>"
            f"{index_insight}</div>"
            if index_insight else ""
        )
        index_banner = (
            f"<div style='background:#f9fafb;border-bottom:1px solid #e5e7eb;padding:14px 28px;'>"
            f"<div style='display:flex;align-items:center;gap:16px;flex-wrap:wrap;'>"
            f"<span style='font-size:12px;color:#6b7280;text-transform:uppercase;"
            f"letter-spacing:0.05em;'>PSE Composite Index</span>"
            f"<span style='font-size:20px;font-weight:800;color:#111827;'>{index['price']:,.2f}</span>"
            f"<span style='font-size:14px;font-weight:700;color:{idx_color};'>"
            f"{_arrow(index['pct'])} {_sign(index['change'])}{index['change']:,.2f}"
            f"&nbsp;({_sign(index['pct'])}{index['pct']:.2f}%)</span>"
            f"</div>"
            f"{idx_chart_html}"
            f"{idx_insight_html}"
            f"</div>"
        )
    else:
        index_banner = ""

    # ── Watchlist ──
    wl_stocks = [all_stocks[s] for s in STOCK_WATCHLIST if s in all_stocks]
    has_charts = any(sparklines.get(s) for s in STOCK_WATCHLIST)
    wl_rows = "".join(
        _stock_row(d, insights.get(d["symbol"]), sparklines.get(d["symbol"]))
        for d in wl_stocks
    )
    watchlist_html = (
        _stock_table(wl_rows, include_chart_col=has_charts)
        if wl_stocks
        else "<p style='color:#6b7280;font-size:13px;'>No data available.</p>"
    )

    # ── Top movers ──
    sorted_by_pct = sorted(all_stocks.values(), key=lambda x: x["pct"], reverse=True)
    gainers, losers = sorted_by_pct[:TOP_N], sorted_by_pct[-TOP_N:][::-1]

    movers_have_charts = any(sparklines.get(d["symbol"]) for d in gainers + losers)
    gainers_rows = "".join(
        _stock_row(d, insights.get(d["symbol"]), sparklines.get(d["symbol"]), rank=i + 1)
        for i, d in enumerate(gainers)
    )
    losers_rows = "".join(
        _stock_row(d, insights.get(d["symbol"]), sparklines.get(d["symbol"]), rank=i + 1)
        for i, d in enumerate(losers)
    )

    movers_html = (
        f"<h3 style='margin:0 0 8px;font-size:13px;font-weight:600;color:#16a34a;'>Top Gainers</h3>"
        f"{_stock_table(gainers_rows, include_rank=True, include_chart_col=movers_have_charts)}"
        f"<h3 style='margin:24px 0 8px;font-size:13px;font-weight:600;color:#dc2626;'>Top Losers</h3>"
        f"{_stock_table(losers_rows, include_rank=True, include_chart_col=movers_have_charts)}"
    )

    return (
        f"<!DOCTYPE html><html><body style='margin:0;padding:20px;background:#f3f4f6;'>"
        f"<div style='font-family:Inter,Arial,sans-serif;max-width:700px;margin:0 auto;"
        f"color:#111827;background:#ffffff;border-radius:10px;overflow:hidden;"
        f"box-shadow:0 1px 3px rgba(0,0,0,0.1);'>"
        f"<div style='background:#1e3a5f;color:white;padding:24px 28px;'>"
        f"<div style='font-size:22px;font-weight:800;letter-spacing:-0.02em;'>PSE Daily Newsletter</div>"
        f"<div style='font-size:13px;opacity:0.7;margin-top:4px;'>{today} &nbsp;·&nbsp; data as of {as_of}</div>"
        f"</div>"
        + index_banner
        + f"<div style='padding:28px;'>"
        + _section("Stock Watchlist", watchlist_html)
        + _section("Top Movers", movers_html)
        + f"<div style='font-size:11px;color:#9ca3af;margin-top:16px;border-top:1px solid #f3f4f6;"
        f"padding-top:14px;'>Stock data: phisix-api3.appspot.com. "
        f"Charts show accumulated closing prices (grows to 90 days over time). "
        f"Insights are AI-generated — not financial advice.</div>"
        f"</div></div></body></html>"
    )


# ─── Email ────────────────────────────────────────────────────────────────────

def send_email(html: str, attachments: list[dict]) -> None:
    import resend
    resend.api_key = RESEND_API_KEY
    today = datetime.now().strftime("%b %d, %Y")
    params: dict = {
        "from": EMAIL_FROM,
        "to": [EMAIL_TO],
        "subject": f"PSE Daily Newsletter — {today}",
        "html": html,
    }
    if attachments:
        params["attachments"] = attachments
    resend.Emails.send(params)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching PSE stocks...")
    all_stocks, as_of = fetch_pse_stocks()

    print("Fetching PSEi index...")
    index = fetch_index()
    index_history = fetch_index_history()  # returns (dates, prices)

    print("Updating price history...")
    update_history(all_stocks)

    print("Generating sparklines...")
    sorted_by_pct = sorted(all_stocks.values(), key=lambda x: x["pct"], reverse=True)
    movers = sorted_by_pct[:TOP_N] + sorted_by_pct[-TOP_N:]
    symbols_needing_charts = {s for s in STOCK_WATCHLIST} | {d["symbol"] for d in movers}
    sparkline_bytes = {sym: make_sparkline(sym) for sym in symbols_needing_charts}
    filled = sum(1 for v in sparkline_bytes.values() if v)
    print(f"  {filled}/{len(symbols_needing_charts)} sparklines generated")

    stocks_for_insights = (
        [all_stocks[s] for s in STOCK_WATCHLIST if s in all_stocks] + movers
    )
    seen: set[str] = set()
    unique = [s for s in stocks_for_insights if not (s["symbol"] in seen or seen.add(s["symbol"]))]

    print(f"Generating insights for {len(unique)} stocks...")
    insights = generate_insights(unique)
    print("Generating index insight...")
    index_insight = generate_index_insight(index) if index else ""

    # Build CID attachments for inline images
    attachments: list[dict] = []
    sparklines_src: dict[str, str | None] = {}
    for sym, png in sparkline_bytes.items():
        if png:
            cid = f"sparkline_{sym}"
            sparklines_src[sym] = f"cid:{cid}"
            attachments.append({
                "content_id": cid,
                "filename": f"{sym}.png",
                "content": base64.b64encode(png).decode(),
                "disposition": "inline",
            })
        else:
            sparklines_src[sym] = None

    index_chart_src: str | None = None
    index_chart_png = make_index_chart(*index_history) if index_history[1] else None
    if index_chart_png:
        attachments.append({
            "content_id": "index_chart",
            "filename": "index_chart.png",
            "content": base64.b64encode(index_chart_png).decode(),
            "disposition": "inline",
        })
        index_chart_src = "cid:index_chart"

    print("Building newsletter...")
    html = build_html(index, all_stocks, insights, sparklines_src, as_of, index_chart_src, index_insight)

    print("Sending email...")
    send_email(html, attachments)
    print(f"Done! Newsletter sent to {EMAIL_TO}")


if __name__ == "__main__":
    main()
