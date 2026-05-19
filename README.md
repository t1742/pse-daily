# PSE Daily Newsletter

A daily email newsletter for Philippine Stock Exchange (PSE) stocks. Runs automatically every weekday at 3:35 PM PHT (5 minutes after market close) via GitHub Actions.

## What's in the newsletter

- **PSE Composite Index** — index value, daily change, and 60-day chart
- **Stock Watchlist** — your tracked stocks with price, change, 60-day sparkline chart, and AI-generated insight
- **Top 10 Gainers & Losers** — biggest movers of the day with insights

## Setup

### 1. Fork or clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/pse-daily.git
cd pse-daily
```

### 2. Install dependencies (for local use)

```bash
pip install -r requirements.txt
```

### 3. Set up Resend

The newsletter sends via [Resend](https://resend.com) — no MFA issues, no App Passwords.

1. Sign up at [resend.com](https://resend.com)
2. Go to **API Keys** and create a new key
3. Copy the key (starts with `re_`)

**From address:** Without a custom domain, use `onboarding@resend.dev` as `EMAIL_FROM` — Resend allows this on the free tier when sending to your own verified email. To use your own address (e.g. `newsletter@yourdomain.com`), add and verify a domain in the Resend dashboard.

### 4. Get a Gemini API key (for AI insights — free)

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **Get API key** and create a new key
3. Copy the key

Free tier: 1,500 requests/day — more than enough. The newsletter still works without this key, it just skips the insight text.

### 5. Add GitHub Secrets

In your repo go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `RESEND_API_KEY` | Resend API key from step 3 (starts with `re_`) |
| `EMAIL_FROM` | Sender address — use `onboarding@resend.dev` or your verified domain |
| `EMAIL_TO` | Where to deliver the newsletter |
| `GEMINI_API_KEY` | Gemini API key from step 4 |

### 6. Trigger a test run

Go to **Actions → PSE Daily Newsletter → Run workflow** to send a test email immediately.

After that it runs automatically every weekday at 3:35 PM PHT.

---

## Customise your watchlist

Open `newsletter.py` and edit the `STOCK_WATCHLIST` near the top:

```python
STOCK_WATCHLIST = ["ALI", "AREIT", "BDO", "BPI", "JFC", "MBT", "MREIT", "RCR", "SMPH"]
```

Use PSE ticker symbols (e.g. `"SM"`, `"TEL"`, `"BPI"`). You can verify a ticker exists by checking [phisix-api3.appspot.com/stocks.json](https://phisix-api3.appspot.com/stocks.json).

---

## Preview locally

To generate and open the newsletter in your browser without sending an email:

```bash
python preview.py
```

This saves the output to `sample_newsletter.html` and opens it automatically.

---

## How it works

| Component | Source |
|---|---|
| Stock prices & % change | [phisix-api3.appspot.com](https://phisix-api3.appspot.com) |
| PSE Composite Index | Yahoo Finance |
| 60-day price history | Accumulated daily in `data/history.csv` |
| AI insights | Claude Haiku (Anthropic API) |
| Email delivery | Gmail SMTP |

**Price history** builds up automatically — GitHub Actions commits an updated `data/history.csv` to the repo after each run. Charts will be sparse for the first few weeks and fill out to 60 days over time.

---

## Files

```
newsletter.py          # main script
preview.py             # local preview (no email)
requirements.txt       # Python dependencies
data/history.csv       # accumulated daily closing prices
.github/workflows/
  newsletter.yml       # GitHub Actions schedule
```
