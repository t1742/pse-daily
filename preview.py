"""Generates a sample newsletter HTML and opens it in the browser."""
import os, warnings, webbrowser
from newsletter import (
    fetch_pse_stocks, fetch_index, fetch_index_history,
    update_history, generate_insights, generate_index_insight,
    make_sparkline, make_index_chart,
    bytes_to_data_uri, build_html, STOCK_WATCHLIST, TOP_N,
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
sparkline_bytes = {sym: make_sparkline(sym) for sym in symbols_needing_charts}
sparklines_src = {
    sym: (bytes_to_data_uri(png) if png else None)
    for sym, png in sparkline_bytes.items()
}
filled = sum(1 for v in sparklines_src.values() if v)
print(f"  {filled}/{len(symbols_needing_charts)} sparklines generated")

stocks_for_insights = (
    [all_stocks[s] for s in STOCK_WATCHLIST if s in all_stocks] + movers
)
seen: set[str] = set()
unique = [s for s in stocks_for_insights if not (s["symbol"] in seen or seen.add(s["symbol"]))]

print(f"Generating insights for {len(unique)} stocks...")
insights = generate_insights(unique)

index_chart_src = None
index_chart_png = make_index_chart(*index_history) if index_history[1] else None
if index_chart_png:
    index_chart_src = bytes_to_data_uri(index_chart_png)

print("Generating index insight...")
index_insight = generate_index_insight(index) if index else ""

print("Building HTML...")
html = build_html(index, all_stocks, insights, sparklines_src, as_of, index_chart_src, index_insight)

out = os.path.join(os.path.dirname(__file__), "sample_newsletter.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Saved to {out}")
webbrowser.open(f"file:///{out}")
