#!/usr/bin/env python3
"""Daily intelligence brief: aggregate today's hourly scan JSONs into one report."""

import glob
import json
import os
from datetime import datetime

BASE_DIR = os.environ.get("PRUDENTIA_MONITOR_DIR", os.path.expanduser("~/prudentia_monitor"))
REPORT_DIR = os.path.join(BASE_DIR, "reports")


def compile_daily_data(today: str | None = None, base_dir: str = BASE_DIR) -> list[dict]:
    today = today or datetime.now().strftime("%Y%m%d")
    scan_files = sorted(glob.glob(os.path.join(base_dir, "data", f"scan_{today}_*.json")))
    snapshots = []
    for file in scan_files:
        with open(file) as f:
            snapshots.append(json.load(f))
    return snapshots


def analyze_trends(snapshots: list[dict]) -> dict:
    trends = {
        "spy_range": {"min": None, "max": None, "open": None, "close": None, "daily_change_pct": None},
        "signal_count": {"void_gaps": 0, "divergence_alerts": 0, "volume_anomalies": 0},
        "correlation_trajectory": [],
    }
    if not snapshots:
        return trends
    spy_prices = [s["market_data"]["SPY"]["price"] for s in snapshots if "SPY" in s.get("market_data", {})]
    if spy_prices:
        trends["spy_range"] = {
            "open": spy_prices[0],
            "close": spy_prices[-1],
            "min": min(spy_prices),
            "max": max(spy_prices),
            "daily_change_pct": round((spy_prices[-1] - spy_prices[0]) / spy_prices[0] * 100, 2) if spy_prices[0] else 0.0,
        }
    for snap in snapshots:
        signals = snap.get("signals", {})
        for key in trends["signal_count"]:
            trends["signal_count"][key] += len(signals.get(key, []))
        if "correlations" in snap:
            trends["correlation_trajectory"].append(snap["correlations"])
    return trends


def assess_system_state(snapshots: list[dict], trends: dict) -> dict:
    if not snapshots:
        return {"status": "NO_DATA", "score": 0, "indicators": [], "interpretation": "No hourly scans found for today."}
    score = 0
    indicators = []
    counts = trends["signal_count"]
    if counts["void_gaps"] >= 3:
        score += 2
        indicators.append("Multiple void gaps detected")
    if counts["divergence_alerts"] >= 2:
        score += 3
        indicators.append("Sentinel divergence from benchmark")
    spy_change = abs(trends["spy_range"]["daily_change_pct"] or 0)
    if spy_change > 2:
        score += 2
        indicators.append(f"High benchmark volatility ({spy_change}%)")
    elif spy_change < 0.5:
        score += 1
        indicators.append("Unusually flat benchmark tape (low volatility)")
    if score >= 5:
        status, interpretation = "CRITICAL", "Elevated stress signatures. Defensive posture warranted."
    elif score >= 3:
        status, interpretation = "NERVOUS", "Stress signatures present. Opportunistic entries only with tight stops."
    elif score >= 1:
        status, interpretation = "ACTIVE", "Normal signal activity. Standard monitoring."
    else:
        status, interpretation = "DORMANT", "Minimal signal footprint. Quiet tapes often precede moves."
    return {"status": status, "score": score, "indicators": indicators, "interpretation": interpretation}


def generate_recommendations(system_state: dict, trends: dict) -> dict:
    status = system_state["status"]
    if status == "CRITICAL":
        actions = ["Review non-essential positions", "Confirm hedge readiness", "Watch for capitulation signals tomorrow"]
        positioning = {"aggressive": 0, "defensive": 20, "cash": 80}
    elif status == "NERVOUS":
        actions = ["Consider trimming exposure", "Tighten stop-loss levels", "Keep dry powder ready"]
        positioning = {"aggressive": 10, "defensive": 40, "cash": 50}
    elif status == "ACTIVE":
        actions = ["Maintain current allocation", "Watch sentinel sectors for breakouts", "Set alerts on sentinel/benchmark correlation breaks"]
        positioning = {"aggressive": 30, "defensive": 30, "cash": 40}
    else:
        actions = ["Accumulate on weakness if aligned with plan", "Build tomorrow's watchlist", "Note that quiet periods often precede moves"]
        positioning = {"aggressive": 20, "defensive": 20, "cash": 60}
    return {
        "actions": actions,
        "positioning": positioning,
        "urgency": "HIGH" if status in ("CRITICAL", "NERVOUS") else "NORMAL",
        "disclaimer": "Analytical summary of public market data, not personalized investment advice.",
    }


def generate_brief(snapshots: list[dict] | None = None) -> dict:
    snapshots = snapshots if snapshots is not None else compile_daily_data()
    trends = analyze_trends(snapshots)
    system_state = assess_system_state(snapshots, trends)
    recommendations = generate_recommendations(system_state, trends)
    total_signals = sum(trends["signal_count"].values())
    brief = {
        "report_metadata": {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "generated_at": datetime.now().isoformat(),
            "hourly_scans_processed": len(snapshots),
            "report_version": "1.1",
        },
        "executive_summary": {
            "system_status": system_state["status"],
            "spy_daily_change_pct": trends["spy_range"]["daily_change_pct"],
            "total_signals_detected": total_signals,
            "primary_action": recommendations["actions"][0] if recommendations["actions"] else "HOLD",
        },
        "market_overview": {
            "spy": trends["spy_range"],
            "volume_analysis": "ELEVATED" if trends["signal_count"]["volume_anomalies"] > 5 else "NORMAL",
            "correlation_health": "DIVERGENT" if trends["signal_count"]["divergence_alerts"] > 0 else "TRACKING",
        },
        "system_state": system_state,
        "signal_inventory": trends["signal_count"],
        "tactical_recommendations": recommendations,
    }
    return brief


def main() -> dict:
    brief = generate_brief()
    os.makedirs(REPORT_DIR, exist_ok=True)
    filename = f"daily_brief_{datetime.now().strftime('%Y%m%d')}.json"
    filepath = os.path.join(REPORT_DIR, filename)
    with open(filepath, "w") as f:
        json.dump(brief, f, indent=2)
    print("=" * 60)
    print(f"DAILY INTELLIGENCE BRIEF {brief['report_metadata']['date']}")
    print(f"System status: {brief['executive_summary']['system_status']}")
    print(f"SPY daily change: {brief['executive_summary']['spy_daily_change_pct']}%")
    print(f"Total signals: {brief['executive_summary']['total_signals_detected']}")
    print(f"Primary action: {brief['executive_summary']['primary_action']}")
    for obs in brief["system_state"]["indicators"]:
        print(f"  - {obs}")
    print(f"Report saved: {filepath}")
    return brief


if __name__ == "__main__":
    main()
