"""
PSE Daily Stock Newsletter
Fetches PSE stock data from phisix-api3.appspot.com and sends an HTML email.

Setup:
  1. pip install yfinance
  2. Enable 2-Step Verification on your Google account.
  3. Go to https://myaccount.google.com/apppasswords and create an App Password.
  4. Fill in the CONFIG section below.
  5. Run: python newsletter.py
"""

import json
import smtplib
import urllib.request
import warnings
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import os

import yfinance as yf

warnings.filterwarnings("ignore")

# ─── CONFIG ──────────────────────────────────────────────────────────────────

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
# Reads from environment variables (set as GitHub Secrets in CI, or export locally).
# Fallback to placeholder strings so the file is valid when not yet configured.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "your_email@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "your_email@gmail.com")

# Stock watchlist — PSE ticker symbols
STOCK_WATCHLIST = ["ALI", "AREIT", "BDO", "BPI", "JFC", "MBT", "MREIT", "RCR", "SMPH"]

# How many top gainers/losers to show
TOP_N = 5

PSE_INDEX_TICKER = "PSEi.PS"

# ─────────────────────────────────────────────────────────────────────────────


def fetch_pse_stocks() -> tuple[dict[str, dict], str]:
    """Fetch all PSE stocks. Returns (stocks_by_symbol, as_of_str)."""
    raw = json.loads(
        urllib.request.urlopen("https://phisix-api3.appspot.com/stocks.json", timeout=15).read()
    )
    as_of_raw = raw.get("as_of", "")
    try:
        as_of = datetime.fromisoformat(as_of_raw).strftime("%b %d, %Y %I:%M %p")
    except Exception:
        as_of = as_of_raw

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


def fetch_index() -> dict | None:
    """Fetch PSEi index data from Yahoo Finance."""
    try:
        info = yf.Ticker(PSE_INDEX_TICKER).fast_info
        price = info.last_price
        prev = info.previous_close
        if price is None or prev is None or prev == 0:
            return None
        change = price - prev
        return {"price": price, "change": change, "pct": (change / prev) * 100}
    except Exception:
        return None


# ─── HTML helpers ─────────────────────────────────────────────────────────────

def _color(pct: float) -> str:
    return "#16a34a" if pct >= 0 else "#dc2626"


def _arrow(pct: float) -> str:
    return "▲" if pct >= 0 else "▼"


def _sign(val: float) -> str:
    return "+" if val >= 0 else ""


def _stock_row(d: dict, rank: int | None = None) -> str:
    color = _color(d["pct"])
    rank_cell = f"<td style='padding:7px 10px;color:#9ca3af;font-size:13px;'>{rank}</td>" if rank is not None else ""
    return (
        f"<tr style='border-bottom:1px solid #f3f4f6;'>"
        f"{rank_cell}"
        f"<td style='padding:7px 10px;'>"
        f"<div style='font-weight:700;font-size:13px;'>{d['symbol']}</div>"
        f"<div style='font-size:11px;color:#6b7280;overflow:hidden;text-overflow:ellipsis;"
        f"white-space:nowrap;max-width:160px;'>{d['name']}</div>"
        f"</td>"
        f"<td style='padding:7px 10px;text-align:right;font-size:13px;'>₱{d['price']:,.2f}</td>"
        f"<td style='padding:7px 10px;text-align:right;color:{color};font-weight:700;font-size:13px;'>"
        f"{_arrow(d['pct'])} {_sign(d['change'])}{d['change']:,.2f}</td>"
        f"<td style='padding:7px 10px;text-align:right;color:{color};font-weight:700;font-size:13px;'>"
        f"{_sign(d['pct'])}{d['pct']:.2f}%</td>"
        f"</tr>"
    )


def _stock_table(rows_html: str, include_rank: bool = False) -> str:
    rank_th = "<th style='padding:6px 10px;text-align:left;color:#9ca3af;font-weight:500;font-size:12px;'>#</th>" if include_rank else ""
    return (
        f"<table style='width:100%;border-collapse:collapse;'>"
        f"<thead><tr style='background:#f9fafb;'>"
        f"{rank_th}"
        f"<th style='padding:6px 10px;text-align:left;color:#9ca3af;font-weight:500;font-size:12px;'>Stock</th>"
        f"<th style='padding:6px 10px;text-align:right;color:#9ca3af;font-weight:500;font-size:12px;'>Price</th>"
        f"<th style='padding:6px 10px;text-align:right;color:#9ca3af;font-weight:500;font-size:12px;'>Change</th>"
        f"<th style='padding:6px 10px;text-align:right;color:#9ca3af;font-weight:500;font-size:12px;'>%</th>"
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
    as_of: str,
) -> str:
    today = datetime.now().strftime("%B %d, %Y")

    # Market overview
    if index:
        idx_color = _color(index["pct"])
        index_html = (
            f"<div style='background:#f9fafb;border-radius:8px;padding:20px;"
            f"display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;'>"
            f"<div>"
            f"<div style='font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em;'>"
            f"PSE Composite Index</div>"
            f"<div style='font-size:34px;font-weight:800;color:#111827;margin-top:2px;'>"
            f"{index['price']:,.2f}</div>"
            f"</div>"
            f"<div style='text-align:right;'>"
            f"<div style='font-size:24px;font-weight:700;color:{idx_color};'>"
            f"{_arrow(index['pct'])} {_sign(index['change'])}{index['change']:,.2f}</div>"
            f"<div style='font-size:15px;font-weight:600;color:{idx_color};'>"
            f"{_sign(index['pct'])}{index['pct']:.2f}%</div>"
            f"</div>"
            f"</div>"
        )
    else:
        index_html = "<p style='color:#6b7280;font-size:13px;'>Index data unavailable.</p>"

    # Top movers
    sorted_by_pct = sorted(all_stocks.values(), key=lambda x: x["pct"], reverse=True)
    gainers_rows = "".join(_stock_row(d, i + 1) for i, d in enumerate(sorted_by_pct[:TOP_N]))
    losers_rows = "".join(_stock_row(d, i + 1) for i, d in enumerate(sorted_by_pct[-TOP_N:][::-1]))
    movers_html = (
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:24px;'>"
        f"<div><h3 style='margin:0 0 8px;font-size:13px;font-weight:600;color:#16a34a;'>Top Gainers</h3>"
        f"{_stock_table(gainers_rows, include_rank=True)}</div>"
        f"<div><h3 style='margin:0 0 8px;font-size:13px;font-weight:600;color:#dc2626;'>Top Losers</h3>"
        f"{_stock_table(losers_rows, include_rank=True)}</div>"
        f"</div>"
    )

    # Stock watchlist
    wl_stocks = [all_stocks[s] for s in STOCK_WATCHLIST if s in all_stocks]
    watchlist_html = (
        _stock_table("".join(_stock_row(d) for d in wl_stocks))
        if wl_stocks
        else "<p style='color:#6b7280;font-size:13px;'>No data available.</p>"
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
        f"<div style='padding:28px;'>"
        + _section("Market Overview", index_html)
        + _section("Top Movers", movers_html)
        + _section("Stock Watchlist", watchlist_html)
        + f"<div style='font-size:11px;color:#9ca3af;margin-top:16px;border-top:1px solid #f3f4f6;"
        f"padding-top:14px;'>Data from phisix-api3.appspot.com &amp; Yahoo Finance. "
        f"For informational purposes only — not financial advice.</div>"
        f"</div></div></body></html>"
    )


# ─── Email ────────────────────────────────────────────────────────────────────

def send_email(html: str) -> None:
    today = datetime.now().strftime("%b %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"PSE Daily Newsletter — {today}"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Fetching PSE stocks...")
    all_stocks, as_of = fetch_pse_stocks()

    print("Fetching PSEi index...")
    index = fetch_index()

    print("Building newsletter...")
    html = build_html(index, all_stocks, as_of)

    print("Sending email...")
    send_email(html)
    print(f"Done! Newsletter sent to {EMAIL_TO}")


if __name__ == "__main__":
    main()
