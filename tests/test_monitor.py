import json
import sys
import types

import pytest


class _Row:
    def __init__(self, close: float, volume: int) -> None:
        self._data = {"Close": close, "Volume": volume}

    def __getitem__(self, key: str) -> float:
        return self._data[key]


class _ILoc:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def __getitem__(self, idx: int) -> _Row:
        return self._rows[idx]


class _VolumeSeries:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def mean(self) -> float:
        return sum(r["Volume"] for r in self._rows) / len(self._rows)


class _Hist:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows
        self.iloc = _ILoc(rows)
        self.empty = len(rows) == 0

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, key: str) -> _VolumeSeries:
        assert key == "Volume"
        return _VolumeSeries(self._rows)


def _install_fake_yfinance(monkeypatch: pytest.MonkeyPatch, prices: dict[str, list[tuple[float, int]]]) -> None:
    fake = types.ModuleType("yfinance")

    class _Ticker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

        def history(self, period: str, interval: str) -> _Hist:
            rows = [_Row(c, v) for c, v in prices.get(self.ticker, [])]
            return _Hist(rows)

    fake.Ticker = _Ticker
    monkeypatch.setitem(sys.modules, "yfinance", fake)


def test_hourly_scan_writes_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    prices = {
        "SPY": [(100.0, 5_000_000), (101.5, 4_800_000)],
        "VTI": [(50.0, 1_000_000), (50.4, 900_000)],
        "IHE": [(80.0, 200_000), (83.0, 40_000)],
        "JEDI": [(30.0, 200_000), (30.3, 210_000)],
        "NCLD": [(60.0, 300_000), (60.2, 290_000)],
    }
    _install_fake_yfinance(monkeypatch, prices)
    monkeypatch.setenv("PRUDENTIA_MONITOR_DIR", str(tmp_path))
    from monitor import hourly_scan

    report = hourly_scan.main()
    assert report["data_quality"] == "LIVE"
    assert report["market_data"]["SPY"]["price"] == 101.5
    assert report["market_data"]["SPY"]["price_change_pct"] == pytest.approx(1.5)
    ihe = report["market_data"]["IHE"]
    assert ihe["price_change_pct"] == pytest.approx(3.75)
    void_tickers = [s["ticker"] for s in report["signals"]["void_gaps"]]
    assert "IHE" in void_tickers
    assert any(a["sentinel"] == "IHE" for a in report["signals"]["divergence_alerts"])
    files = list((tmp_path / "data").glob("scan_*.json"))
    assert len(files) == 1
    on_disk = json.loads(files[0].read_text())
    assert on_disk["market_data"]["SPY"]["price"] == 101.5


def test_hourly_scan_handles_missing_data(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _install_fake_yfinance(monkeypatch, {"SPY": [(100.0, 1_000_000), (100.5, 1_000_000)]})
    monkeypatch.setenv("PRUDENTIA_MONITOR_DIR", str(tmp_path))
    from monitor import hourly_scan

    report = hourly_scan.main()
    assert report["data_quality"] == "STALE"
    assert "error" in report["market_data"]["VTI"]


def test_daily_brief_aggregates_scans(tmp_path) -> None:
    from monitor import daily_brief

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    today = "20260113"
    scans = [
        {"timestamp": "t1", "market_data": {"SPY": {"price": 100.0}}, "signals": {"void_gaps": [{"ticker": "IHE"}], "divergence_alerts": [], "volume_anomalies": []}, "correlations": {"IHE": {"vs_SPY": "TRACKING", "divergence_magnitude": 0.1}}},
        {"timestamp": "t2", "market_data": {"SPY": {"price": 103.0}}, "signals": {"void_gaps": [{"ticker": "IHE"}, {"ticker": "JEDI"}], "divergence_alerts": [{"sentinel": "IHE", "divergence_magnitude": 2.5}], "volume_anomalies": []}, "correlations": {"IHE": {"vs_SPY": "DIVERGENT", "divergence_magnitude": 2.5}}},
    ]
    for i, scan in enumerate(scans):
        (data_dir / f"scan_{today}_{i:02d}00.json").write_text(json.dumps(scan))
    snapshots = daily_brief.compile_daily_data(today=today, base_dir=str(tmp_path))
    assert len(snapshots) == 2
    brief = daily_brief.generate_brief(snapshots)
    assert brief["report_metadata"]["hourly_scans_processed"] == 2
    assert brief["executive_summary"]["spy_daily_change_pct"] == pytest.approx(3.0)
    assert brief["signal_inventory"]["void_gaps"] == 3
    assert brief["signal_inventory"]["divergence_alerts"] == 1
    assert brief["executive_summary"]["system_status"] == "NERVOUS"
    assert brief["market_overview"]["correlation_health"] == "DIVERGENT"
    assert "disclaimer" in brief["tactical_recommendations"]


def test_daily_brief_no_data(tmp_path) -> None:
    from monitor import daily_brief

    brief = daily_brief.generate_brief([])
    assert brief["executive_summary"]["system_status"] == "NO_DATA"
    assert brief["executive_summary"]["spy_daily_change_pct"] is None

def test_config_fails_fast_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from monitor import config

    monkeypatch.delenv("PRUDENTIA_MONITOR_DIR", raising=False)
    monkeypatch.delenv("PRUDENTIA_MONITOR_ALLOW_DEFAULT", raising=False)
    with pytest.raises(SystemExit):
        config._base_dir()


def test_scan_timestamps_are_utc(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    prices = {t: [(100.0, 1_000_000), (101.0, 1_000_000)] for t in ["SPY", "VTI", "IHE", "JEDI", "NCLD"]}
    _install_fake_yfinance(monkeypatch, prices)
    monkeypatch.setenv("PRUDENTIA_MONITOR_DIR", str(tmp_path))
    from monitor import hourly_scan

    report = hourly_scan.main()
    assert report["timestamp"].endswith("+00:00")  # timezone-aware UTC (fix B5)
    assert "environment" in report and "script_sha256" in report["environment"]


def test_positioning_is_labeled_framework_default() -> None:
    from monitor import daily_brief

    brief = daily_brief.generate_brief([])
    pos = brief["tactical_recommendations"]["positioning"]
    assert pos["kind"] == "FRAMEWORK_DEFAULT"
    assert pos["not_personal_advice"] is True
    assert isinstance(pos["value"], dict)
    assert brief["report_metadata"]["report_version"] == "1.3"
