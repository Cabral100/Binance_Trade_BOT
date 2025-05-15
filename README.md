# 🔁 Automated Trading Bot - SOL/USDT (Binance)

This project is an automated trading bot for the **SOL/USDT** pair on Binance. It uses several technical indicators to make buy and sell decisions, including RSI, MACD, Exponential Moving Averages (EMA), Bollinger Bands, and Stochastic Oscillator.

## 📌 Features

- 🔄 Automatically fetches historical market data via the Binance API
- 📊 Computes technical indicators using the `ta` library
- 🧠 Trade decision logic based on multiple technical signals
- 💸 Executes market buy and sell orders on Binance Spot
- 📝 Logs trading actions and strategy decisions

## 📈 Technical Indicators Used

- **RSI (Relative Strength Index)** — Detects overbought/oversold conditions
- **MACD (Moving Average Convergence Divergence)** — Measures momentum shifts
- **EMA (Exponential Moving Averages)** — Captures short-term and long-term trends
- **Bollinger Bands** — Identifies price volatility and potential breakout zones
- **Stochastic Oscillator** — Highlights trend reversals and momentum

## ⚙️ Requirements

- Python 3.8+
- Binance API key and secret
- `.env` file configured with your credentials:
  ```env
  API_KEY=your_api_key
  API_SECRET=your_api_secret
