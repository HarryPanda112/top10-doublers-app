<<<<<<< HEAD
# Top-10 Doublers — Streamlit + Firebase prototype

## What it does
- Loads Dhan token & optional NewsAPI key securely from Firestore (collection `config`, document `keys`)
- Fetches historical data (Dhan if token present, else yfinance fallback)
- Computes indicators and ranks stocks by probability to reach 200% (heuristic score)
- Exports `top_stocks_TIMESTAMP.xlsx` with Top-10 per horizon

## Setup

1. Clone this folder to your machine.

2. Create virtual env & install:
=======
# top10-doublers-app
Top-10 Doublers is a Streamlit app that identifies top Indian stocks likely to double over 6 to 48 months. It fetches historical data using Dhan API or yfinance, calculates indicators and scores, then ranks stocks by probability. Results are shown interactively with downloadable Excel reports for easy analysis.
>>>>>>> f27f5a114bf5b83a07b9536278310b3be3519a42
