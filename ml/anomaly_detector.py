import time
import logging
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from prometheus_client import start_http_server, Gauge, Counter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROMETHEUS_URL = "http://prometheus:9090"
INTERVAL       = 60
LOOKBACK_HOURS = 2

# ── Output Metrics (labeled per monitored server instance) ────────────────────
anomaly_score    = Gauge("ml_anomaly_score",     "Isolation Forest score",       ["instance"])
anomaly_detected = Gauge("ml_anomaly_detected",  "1 = anomaly, 0 = normal",      ["instance"])
disk_full_days   = Gauge("ml_disk_full_in_days", "Days until disk full (-1=none)", ["instance"])
ml_runs_total    = Counter("ml_runs_total",      "Total ML runs")
ml_errors_total  = Counter("ml_errors_total",    "Total ML errors")


def get_instances() -> list[str]:
    """Return all collector instances currently up in Prometheus."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": 'up{job="quickpalm-collector"}'},
            timeout=5,
        )
        results = resp.json()["data"]["result"]
        return [r["metric"]["instance"] for r in results if "instance" in r["metric"]]
    except Exception as e:
        log.warning(f"Could not discover instances: {e}")
        return []


def query_range(metric: str, instance: str, hours: int = LOOKBACK_HOURS) -> pd.DataFrame:
    end   = datetime.utcnow()
    start = end - timedelta(hours=hours)
    params = {
        "query": f'{metric}{{instance="{instance}"}}',
        "start": start.isoformat() + "Z",
        "end":   end.isoformat() + "Z",
        "step":  "15s",
    }
    resp = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if not data["data"]["result"]:
        return pd.DataFrame()

    values = data["data"]["result"][0]["values"]
    df = pd.DataFrame(values, columns=["timestamp", "value"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df["value"]     = df["value"].astype(float)
    return df


def run_isolation_forest(instance: str) -> None:
    try:
        cpu  = query_range("node_cpu_percent",  instance)
        ram  = query_range("node_ram_percent",  instance)
        load = query_range("node_load_1m",      instance)

        if cpu.empty or ram.empty or load.empty:
            log.warning(f"[{instance}] Not enough data for anomaly detection")
            return

        for frame in [cpu, ram, load]:
            frame["timestamp"] = frame["timestamp"].dt.round("15s")

        df = cpu.rename(columns={"value": "cpu"})
        df = df.merge(ram.rename(columns={"value": "ram"}),   on="timestamp", how="inner")
        df = df.merge(load.rename(columns={"value": "load"}), on="timestamp", how="inner")

        if len(df) < 10:
            log.warning(f"[{instance}] Only {len(df)} points — waiting for more data")
            return

        X            = df[["cpu", "ram", "load"]].values
        model        = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
        model.fit(X)
        latest_score = model.score_samples(X[-1:].reshape(1, -1))[0]
        is_anomaly   = int(model.predict(X[-1:].reshape(1, -1))[0] == -1)

        anomaly_score.labels(instance=instance).set(round(latest_score, 4))
        anomaly_detected.labels(instance=instance).set(is_anomaly)

        status = "ANOMALY" if is_anomaly else "Normal"
        log.info(f"[{instance}] Isolation Forest → {status} (score={latest_score:.4f}, "
                 f"CPU={X[-1][0]:.1f}%, RAM={X[-1][1]:.1f}%)")

    except Exception as e:
        ml_errors_total.inc()
        log.error(f"[{instance}] Isolation Forest error: {e}")


def run_disk_forecast(instance: str) -> None:
    try:
        df = query_range("node_disk_percent", instance, hours=24)

        if df.empty or len(df) < 30:
            log.warning(f"[{instance}] Not enough disk data ({len(df)} points)")
            disk_full_days.labels(instance=instance).set(-1)
            return

        t0    = df["timestamp"].iloc[0].timestamp()
        X     = np.array([(ts.timestamp() - t0) for ts in df["timestamp"]]).reshape(-1, 1)
        y     = df["value"].values
        model = LinearRegression()
        model.fit(X, y)
        slope = model.coef_[0]

        if slope <= 0:
            log.info(f"[{instance}] Disk forecast → No upward trend")
            disk_full_days.labels(instance=instance).set(-1)
            return

        current = y[-1]
        if current >= 95:
            log.warning(f"[{instance}] Disk already above 95%!")
            disk_full_days.labels(instance=instance).set(0)
            return

        seconds_until_full = (95 - model.predict(X[-1:])[0]) / slope
        days_left = max(0, int(seconds_until_full / 86400))
        disk_full_days.labels(instance=instance).set(days_left)
        log.info(f"[{instance}] Disk forecast → full in ~{days_left} days "
                 f"(current={current:.1f}%, trend=+{slope*86400:.3f}%/day)")

    except Exception as e:
        ml_errors_total.inc()
        log.error(f"[{instance}] Disk forecast error: {e}")
        disk_full_days.labels(instance=instance).set(-1)


def main():
    start_http_server(8001)
    log.info("ML Service started on :8001")
    log.info(f"Running every {INTERVAL}s | Lookback: {LOOKBACK_HOURS}h")

    while True:
        ml_runs_total.inc()
        instances = get_instances()

        if not instances:
            log.warning("No collector instances found — retrying next cycle")
        else:
            log.info(f"── ML run: {len(instances)} instance(s): {instances} ──")
            for instance in instances:
                run_isolation_forest(instance)
                run_disk_forecast(instance)

        log.info("── ML run complete ──")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
