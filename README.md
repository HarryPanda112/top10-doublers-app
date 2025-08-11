# Top-10 Doublers — Streamlit + Firebase prototype

## What it does
- Loads Dhan token & optional NewsAPI key securely from Firestore (collection `config`, document `keys`)
- Fetches historical data (Dhan if token present, else yfinance fallback)
- Computes indicators and ranks stocks by probability to reach 200% (heuristic score)
- Exports `top_stocks_TIMESTAMP.xlsx` with Top-10 per horizon

## Setup

1. Clone this folder to your machine.

2. Create virtual env & install:
