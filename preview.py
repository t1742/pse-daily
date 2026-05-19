"""Generates a sample newsletter HTML and opens it in the browser."""
import warnings, webbrowser, os
from newsletter import fetch_pse_stocks, fetch_index, build_html
warnings.filterwarnings("ignore")

print("Fetching PSE stocks...")
all_stocks, as_of = fetch_pse_stocks()

print("Fetching PSEi index...")
index = fetch_index()

print("Building HTML...")
html = build_html(index, all_stocks, as_of)

out = os.path.join(os.path.dirname(__file__), "sample_newsletter.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Saved to {out}")
webbrowser.open(f"file:///{out}")
