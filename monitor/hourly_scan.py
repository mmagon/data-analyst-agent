#!/usr/bin/env python3
"""Hourly market scan (Commit A hardened).

vs 60d0f7b: UTC timestamps; concurrent per-ticker fetch with ~10s timeout + 1 retry;
fetch errors are STALE data, not process failure; a report is ALWAYS written;
exit 0 whenever the report file was written (data_quality carried in JSON, fix #2);
durable run log appended to run_log.jsonl (fix #1); environment block logs the
installed yfinance version and this script's sha256.
"""

import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import os as _os
import sys as _sys

try:  # package import (tests, `python -m monitor.hourly_scan`)
    from monitor import config
    from monitor.config import utcnow
except ModuleNotFoundError:  # flat layout: run as `python3 hourly_scan.py` next to config.py
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import config
    from config import utcnow

ASSETS = {
    "benchmarks": ["SPY", "VTI"],
    "sentinels": ["IHE", "JEDI", "NCLD"],
}

FETCH_TIMEOUT_S = 10
FETCH_RETRIES = 1
RETRY_BACKOFF_S = 2.0


def _yf_version() -> str:
    try:
        return pkg_version("yfinance")
    except PackageNotFoundError:
        return "not-installed"


def _fetch_one(ticker: str) -> dict:
    """One bounded fetch attempt. Never raises: errors become STALE data."""
    import yfinance as yf

    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1h")
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "timestamp": utcnow().isoformat()}
    if hist is None or hist.empty:
        return {"error": "no data", "timestamp": utcnow().isoformat()}
    latest = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else latest
    avg_volume = float(hist["Volume"].mean()) if len(hist) > 1 else float(latest["Volume"])
    close = float(latest["Close"])
    prev_close = float(prev["Close"])
    return {
        "price": round(close, 2),
        "volume": int(latest["Volume"]),
        "avg_volume_5d": round(avg_volume, 0),
        "price_change_pct": round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
        "timestamp": utcnow().isoformat(),
    }


def fetch_market_data(assets: dict[str, list[str]]) -> dict:
    tickers = assets["benchmarks"] + assets["sentinels"]
    data: dict = {}
    with ThreadPoolExecutor(max_workers=min(8, len(tickers))) as pool:
        futures = {}
        for ticker in tickers:
            futures[ticker] = pool.submit(_fetch_one, ticker)
            time.sleep(0.25)  # gentle pacing against rate limits
        for ticker, fut in futures.items():
            attempts = 1
            try:
                data[ticker] = fut.result(timeout=FETCH_TIMEOUT_S)
            except Exception:
                # one retry, still bounded by the same timeout (fix #3)
                attempts = 2
                try:
                    data[ticker] = pool.submit(_fetch_one, ticker).result(timeout=FETCH_TIMEOUT_S)
                except Exception as exc:  # noqa: BLE001
                    data[ticker] = {
                        "error": f"timeout/failure after {attempts} attempts: {type(exc).__name__}: {exc}",
                        "timestamp": utcnow().isoformat(),
                    }
            data[ticker]["attempts"] = attempts
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
        "timestamp": utcnow().isoformat(),
        "market_data": market_data,
        "correlations": correlations,
        "signals": signals,
        "data_quality": data_quality,
        "environment": {
            "python": sys.version.split()[0],
            "yfinance": _yf_version(),
            "script_sha256": config.script_sha256(os.path.abspath(__file__)),
        },
    }
    os.makedirs(config.DATA_DIR, exist_ok=True)
    filename = f"scan_{utcnow().strftime('%Y%m%d_%H%M')}.json"
    filepath = os.path.join(config.DATA_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Scan complete: {filepath}")
    print(f"Data quality: {data_quality}")
    print(f"Void gaps: {len(signals['void_gaps'])}, volume anomalies: {len(signals['volume_anomalies'])}, divergence alerts: {len(signals['divergence_alerts'])}")
    return report


def log_run(exit_code: int, data_quality: str | None, error: str | None = None) -> None:
    """Append one heartbeat line per run (fix #1 / B9). Gap alert: no line for >90 min."""
    os.makedirs(config.BASE_DIR, exist_ok=True)
    line = {
        "ts_utc": utcnow().isoformat(),
        "run_id": uuid.uuid4().hex[:12],
        "script": os.path.basename(__file__),
        "script_sha256": config.script_sha256(os.path.abspath(__file__)),
        "exit_code": exit_code,
        "data_quality": data_quality,
        "error": error,
    }
    with open(config.RUN_LOG, "a") as f:
        f.write(json.dumps(line) + "\n")


if __name__ == "__main__":
    try:
        report = main()
    except Exception as exc:  # noqa: BLE001
        log_run(exit_code=2, data_quality=None, error=f"{type(exc).__name__}: {exc}")
        print(f"FATAL: could not write report: {exc}", file=sys.stderr)
        sys.exit(2)  # non-zero ONLY when the report could not be written at all (fix #2)
    log_run(exit_code=0, data_quality=report["data_quality"])
    sys.exit(0)  # report written; quality is in the JSON, not the exit code
