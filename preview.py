"""Generates a sample newsletter HTML and opens it in the browser."""
import os, warnings, webbrowser
from newsletter import (
    fetch_pse_stocks, fetch_index, fetch_index_history,
    update_history, generate_insights, make_sparkline,
    build_html, STOCK_WATCHLIST, TOP_N,
)
warnings.filterwarnings("ignore")

print("Fetching PSE stocks...")
all_stocks, as_of = fetch_pse_stocks()

print("Fetching PSEi index...")
index = fetch_index()
index_history = fetch_index_history()

print("Updating price history...")
update_history(all_stocks)

print("Generating sparklines...")
sorted_by_pct = sorted(all_stocks.values(), key=lambda x: x["pct"], reverse=True)
movers = sorted_by_pct[:TOP_N] + sorted_by_pct[-TOP_N:]
symbols_needing_charts = {s for s in STOCK_WATCHLIST} | {d["symbol"] for d in movers}
sparklines = {sym: make_sparkline(sym) for sym in symbols_needing_charts}
filled = sum(1 for v in sparklines.values() if v)
print(f"  {filled}/{len(symbols_needing_charts)} sparklines generated")

stocks_for_insights = (
    [all_stocks[s] for s in STOCK_WATCHLIST if s in all_stocks] + movers
)
seen: set[str] = set()
unique = [s for s in stocks_for_insights if not (s["symbol"] in seen or seen.add(s["symbol"]))]

print(f"Generating insights for {len(unique)} stocks...")
insights = generate_insights(unique)

print("Building HTML...")
html = build_html(index, index_history, all_stocks, insights, sparklines, as_of)

out = os.path.join(os.path.dirname(__file__), "sample_newsletter.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Saved to {out}")
webbrowser.open(f"file:///{out}")
