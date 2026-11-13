#!/usr/bin/env python3
"""Hourly market scan: fetch prices/volumes, compute divergence and anomaly signals, write a JSON snapshot."""

import json
import os
import sys
import time
from datetime import datetime

ASSETS = {
    "benchmarks": ["SPY", "VTI"],
    "sentinels": ["IHE", "JEDI", "NCLD"],
}

BASE_DIR = os.environ.get("PRUDENTIA_MONITOR_DIR", os.path.expanduser("~/prudentia_monitor"))
DATA_DIR = os.path.join(BASE_DIR, "data")


def fetch_market_data(assets: dict[str, list[str]]) -> dict:
    import yfinance as yf

    data: dict = {}
    all_tickers = assets["benchmarks"] + assets["sentinels"]
    for ticker in all_tickers:
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1h")
        except Exception as exc:
            data[ticker] = {"error": str(exc), "timestamp": datetime.now().isoformat()}
            continue
        if hist is None or hist.empty:
            data[ticker] = {"error": "no data", "timestamp": datetime.now().isoformat()}
            continue
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest
        avg_volume = float(hist["Volume"].mean()) if len(hist) > 1 else float(latest["Volume"])
        close = float(latest["Close"])
        prev_close = float(prev["Close"])
        data[ticker] = {
            "price": round(close, 2),
            "volume": int(latest["Volume"]),
            "avg_volume_5d": round(avg_volume, 0),
            "price_change_pct": round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
            "timestamp": datetime.now().isoformat(),
        }
        time.sleep(0.5)
    return data


def calculate_correlation(data: dict, benchmarks: list[str], sentinels: list[str]) -> dict:
    correlations: dict = {}
    ref = data.get(benchmarks[0], {})
    ref_change = ref.get("price_change_pct", 0)
    for sentinel in sentinels:
        info = data.get(sentinel)
        if not info or "price_change_pct" not in info or not ref_change:
            continue
        divergence = round(abs(info["price_change_pct"] - ref_change), 2)
        correlations[sentinel] = {
            "vs_" + benchmarks[0]: "DIVERGENT" if divergence > 2 else "TRACKING",
            "divergence_magnitude": divergence,
        }
    return correlations


def detect_signals(data: dict) -> dict:
    signals = {"void_gaps": [], "volume_anomalies": [], "divergence_alerts": []}
    for ticker, info in data.items():
        if "price_change_pct" not in info:
            continue
        move = info["price_change_pct"]
        volume = info.get("volume", 0)
        avg_volume = info.get("avg_volume_5d", volume)
        if abs(move) > 1 and avg_volume and volume < 0.5 * avg_volume:
            signals["void_gaps"].append(
                {"ticker": ticker, "price_change": move, "volume": volume, "avg_volume": round(avg_volume, 0)}
            )
        if avg_volume and volume > 1.5 * avg_volume:
            signals["volume_anomalies"].append(
                {"ticker": ticker, "volume": volume, "avg_volume": round(avg_volume, 0)}
            )
    return signals


def add_divergence_alerts(signals: dict, correlations: dict) -> dict:
    for sentinel, corr in correlations.items():
        if corr.get("vs_SPY") == "DIVERGENT":
            signals["divergence_alerts"].append(
                {"sentinel": sentinel, "divergence_magnitude": corr["divergence_magnitude"]}
            )
    return signals


def main() -> dict:
    market_data = fetch_market_data(ASSETS)
    correlations = calculate_correlation(market_data, ASSETS["benchmarks"], ASSETS["sentinels"])
    signals = add_divergence_alerts(detect_signals(market_data), correlations)
    data_quality = "LIVE" if all("price" in v for v in market_data.values()) else "STALE"
    report = {
        "timestamp": datetime.now().isoformat(),
        "market_data": market_data,
        "correlations": correlations,
        "signals": signals,
        "data_quality": data_quality,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f"scan_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Scan complete: {filepath}")
    print(f"Data quality: {data_quality}")
    print(f"Void gaps: {len(signals['void_gaps'])}, volume anomalies: {len(signals['volume_anomalies'])}, divergence alerts: {len(signals['divergence_alerts'])}")
    return report


if __name__ == "__main__":
    sys.exit(0 if main()["data_quality"] == "LIVE" else 1)
