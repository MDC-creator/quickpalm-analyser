import os
import re
import time
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://ollama:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL",   "llama3.2:1b")

app       = FastAPI(title="QuickPalm Analyser")
templates = Jinja2Templates(directory="templates")

# ── Prometheus helpers ────────────────────────────────────────────────────────

def _ifilter(instance: str | None) -> str:
    return f'{{instance="{instance}"}}' if instance else ""


def get_metric(query: str) -> str:
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5,
        )
        result = resp.json()["data"]["result"]
        if result:
            return result[0]["value"][1]
        return "N/A"
    except Exception:
        return "N/A"


def get_metric_range(query: str, start: float, end: float, step: str = "60s") -> list[dict]:
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
            timeout=10,
        )
        result = resp.json()["data"]["result"]
        if not result:
            return []
        return [{"time": v[0], "value": v[1]} for v in result[0]["values"]]
    except Exception:
        return []


def get_servers() -> list[str]:
    """Discover all monitored collector instances from Prometheus."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": 'up{job="quickpalm-collector"}'},
            timeout=5,
        )
        results = resp.json()["data"]["result"]
        return sorted(r["metric"].get("instance", "") for r in results if r["metric"].get("instance"))
    except Exception:
        return []


def summarise_range(values: list[dict], unit: str = "") -> str:
    if not values:
        return "no data"
    nums = [float(v["value"]) for v in values if v["value"] not in ("N/A", "NaN")]
    if not nums:
        return "no data"
    return f"min={min(nums):.1f}{unit} avg={sum(nums)/len(nums):.1f}{unit} max={max(nums):.1f}{unit}"


# ── Context builders ──────────────────────────────────────────────────────────

def build_server_context(instance: str | None = None) -> str:
    f = _ifilter(instance)
    cpu        = get_metric(f"node_cpu_percent{f}")
    ram        = get_metric(f"node_ram_percent{f}")
    disk       = get_metric(f"node_disk_percent{f}")
    load_1m    = get_metric(f"node_load_1m{f}")
    anomaly    = get_metric(f"ml_anomaly_detected{f}")
    anom_score = get_metric(f"ml_anomaly_score{f}")
    disk_days  = get_metric(f"ml_disk_full_in_days{f}")

    anomaly_text = "YES — unusual behavior detected" if anomaly == "1" else "No — everything normal"
    disk_forecast = (
        f"Disk will be full in ~{disk_days} days (at current trend)"
        if disk_days not in ("N/A", "-1", "-1.0")
        else "No critical disk trend detected"
    )
    label = f" [{instance}]" if instance else ""

    return f"""
LIVE SERVER METRICS{label}:
- CPU Usage:       {cpu}%
- RAM Usage:       {ram}%
- Disk Usage:      {disk}%
- Load Average 1m: {load_1m}
- ML Anomaly:      {anomaly_text}
- Anomaly Score:   {anom_score}
- Disk Forecast:   {disk_forecast}
""".strip()


_HISTORY_PATTERNS = [
    (r"\blast\s+(\d+)\s+hour", lambda m: int(m.group(1)) * 3600),
    (r"\blast\s+hour\b",       lambda m: 3600),
    (r"\blast\s+(\d+)\s+min",  lambda m: int(m.group(1)) * 60),
    (r"\byesterday\b",         lambda m: 86400),
    (r"\blast\s+24\s*h",       lambda m: 86400),
    (r"\blast\s+(\d+)\s+day",  lambda m: int(m.group(1)) * 86400),
    (r"\bthis\s+morning\b",    lambda m: 21600),
    (r"\btoday\b",             lambda m: 86400),
]


def detect_lookback(message: str) -> int | None:
    msg = message.lower()
    for pattern, calc in _HISTORY_PATTERNS:
        m = re.search(pattern, msg)
        if m:
            return calc(m)
    return None


def build_history_context(lookback_seconds: int, instance: str | None = None) -> str:
    now   = time.time()
    start = now - lookback_seconds
    step  = max(60, lookback_seconds // 60)
    f     = _ifilter(instance)

    cpu_h  = summarise_range(get_metric_range(f"node_cpu_percent{f}",  start, now, f"{step}s"), "%")
    ram_h  = summarise_range(get_metric_range(f"node_ram_percent{f}",  start, now, f"{step}s"), "%")
    disk_h = summarise_range(get_metric_range(f"node_disk_percent{f}", start, now, f"{step}s"), "%")
    load_h = summarise_range(get_metric_range(f"node_load_1m{f}",      start, now, f"{step}s"))

    hours  = lookback_seconds / 3600
    period = f"{hours:.0f}h" if hours >= 1 else f"{lookback_seconds//60}min"
    label  = f" [{instance}]" if instance else ""

    return f"""
HISTORICAL METRICS{label} (last {period}):
- CPU Usage:       {cpu_h}
- RAM Usage:       {ram_h}
- Disk Usage:      {disk_h}
- Load Average 1m: {load_h}
""".strip()


def build_system_prompt(context: str) -> str:
    return f"""You are QuickPalm Analyser, an intelligent server monitoring assistant.
You answer concisely and helpfully based on real server data.
You give concrete recommendations when something looks wrong.
Keep answers short — 2 to 4 sentences max.

{context}

Answer questions based on this data. If something is critical, say so clearly."""


# ── API ───────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    server: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/servers")
async def servers():
    return {"servers": get_servers()}


@app.get("/status")
async def status():
    context = build_server_context()
    ollama_ok = False
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        ollama_ok = r.status_code == 200
    except Exception:
        pass
    return {"metrics": context, "ollama_available": ollama_ok, "model": OLLAMA_MODEL}


@app.post("/chat")
async def chat(req: ChatRequest):
    instance = req.server or None
    lookback = detect_lookback(req.message)
    if lookback:
        context = build_server_context(instance) + "\n\n" + build_history_context(lookback, instance)
    else:
        context = build_server_context(instance)

    system_msg = build_system_prompt(context)
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": req.message,
        "system": system_msg,
        "stream": False,
    }

    def generate():
        try:
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
            resp.raise_for_status()
            yield resp.json().get("response", "No response received.")
        except requests.exceptions.ConnectionError:
            yield f"Ollama is not reachable. Make sure the model is loaded: ollama pull {OLLAMA_MODEL}"
        except Exception as e:
            yield f"Error: {e}"

    return StreamingResponse(generate(), media_type="text/plain")
