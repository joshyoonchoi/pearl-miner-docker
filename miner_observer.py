#!/usr/bin/env python3
"""Read-only local status API and dashboard for the Pearl miner container."""

import datetime as dt
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional


PORT = int(os.environ.get("PEARL_OBSERVER_PORT", "8340"))
WALLET = os.environ.get("PEARL_WALLET_ADDRESS", "")
VLLM_URL = os.environ.get("PEARL_OBSERVER_VLLM_URL", "http://127.0.0.1:8000")
GATEWAY_URL = os.environ.get("PEARL_OBSERVER_GATEWAY_URL", "http://127.0.0.1:8339")
PEARLD_RPC_URL = os.environ.get("PEARLD_RPC_URL", "http://127.0.0.1:44107")
PEARLD_RPC_USER = os.environ.get("PEARLD_RPC_USER", "")
PEARLD_RPC_PASSWORD = os.environ.get("PEARLD_RPC_PASSWORD", "")
HTTP_TIMEOUT = float(os.environ.get("PEARL_OBSERVER_TIMEOUT", "2.5"))
STARTED_AT = time.time()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_text(url: str, timeout: float = HTTP_TIMEOUT) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"user-agent": "pearl-miner-observer/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "status": response.status,
                "text": response.read().decode("utf-8", "replace"),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "text": exc.read().decode("utf-8", "replace"),
            "error": None,
        }
    except Exception as exc:
        return {"status": None, "text": "", "error": repr(exc)}


def fetch_json(url: str, timeout: float = HTTP_TIMEOUT) -> Dict[str, Any]:
    result = fetch_text(url, timeout)
    if result["error"]:
        return {"status": result["status"], "error": result["error"]}
    try:
        payload = json.loads(result["text"] or "{}")
    except json.JSONDecodeError as exc:
        return {"status": result["status"], "error": f"json_decode_error: {exc}"}
    if not isinstance(payload, dict):
        return {"status": result["status"], "error": "json_response_not_object"}
    payload["_http_status"] = result["status"]
    return payload


def metric_sum(metrics: str, name: str) -> Optional[float]:
    total = 0.0
    found = False
    prefix = name + "{"
    for line in metrics.splitlines():
        if line.startswith("#"):
            continue
        if not line.startswith(prefix) and not line.startswith(name + " "):
            continue
        try:
            total += float(line.rsplit(" ", 1)[1])
            found = True
        except (IndexError, ValueError):
            pass
    return total if found else None


def metric_last(metrics: str, name: str) -> Optional[float]:
    value = None
    prefix = name + "{"
    for line in metrics.splitlines():
        if line.startswith("#"):
            continue
        if not line.startswith(prefix) and not line.startswith(name + " "):
            continue
        try:
            value = float(line.rsplit(" ", 1)[1])
        except (IndexError, ValueError):
            pass
    return value


def interesting_metric_lines(metrics: str) -> List[str]:
    needles = ("proof", "block", "template", "mining", "submit", "accept", "reject")
    rows = []
    for line in metrics.splitlines():
        lowered = line.lower()
        if line.startswith("#"):
            continue
        if any(needle in lowered for needle in needles):
            rows.append(line)
    return rows[:80]


def run_json(cmd: List[str]) -> Dict[str, Any]:
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=3, check=False)
    except Exception as exc:
        return {"ok": False, "error": repr(exc)}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()[-500:],
    }


def process_status(name: str) -> Dict[str, Any]:
    result = run_json(["pgrep", "-fa", name])
    lines = [line for line in result.get("stdout", "").splitlines() if line]
    return {"running": bool(lines), "matches": lines[:5]}


def gpu_status() -> Dict[str, Any]:
    result = run_json(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus = []
    for line in result.get("stdout", "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 6:
            gpus.append(
                {
                    "name": parts[0],
                    "util_percent": number(parts[1]),
                    "memory_used_mib": number(parts[2]),
                    "memory_total_mib": number(parts[3]),
                    "temperature_c": number(parts[4]),
                    "power_w": number(parts[5]),
                }
            )
    return {"ok": result.get("ok", False), "gpus": gpus, "error": result.get("stderr") or result.get("error")}


def number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def vllm_status() -> Dict[str, Any]:
    health = fetch_text(VLLM_URL.rstrip("/") + "/health")
    models = fetch_json(VLLM_URL.rstrip("/") + "/v1/models")
    metrics = fetch_text(VLLM_URL.rstrip("/") + "/metrics")
    data: Dict[str, Any] = {
        "health_status": health["status"],
        "health_error": health["error"],
        "models_status": models.get("_http_status"),
        "models_error": models.get("error"),
        "metrics_status": metrics["status"],
        "metrics_error": metrics["error"],
    }
    if isinstance(models.get("data"), list):
        data["models"] = [
            item.get("id")
            for item in models["data"]
            if isinstance(item, dict) and item.get("id")
        ]
    if metrics["text"]:
        data.update(
            {
                "prompt_tokens_total": metric_sum(metrics["text"], "vllm:prompt_tokens_total"),
                "generation_tokens_total": metric_sum(
                    metrics["text"], "vllm:generation_tokens_total"
                ),
                "request_success_total": metric_sum(metrics["text"], "vllm:request_success_total"),
                "requests_running": metric_sum(metrics["text"], "vllm:num_requests_running"),
                "requests_waiting": metric_sum(metrics["text"], "vllm:num_requests_waiting"),
                "kv_cache_usage": metric_last(metrics["text"], "vllm:kv_cache_usage_perc"),
            }
        )
    return data


def gateway_status() -> Dict[str, Any]:
    metrics = fetch_text(GATEWAY_URL.rstrip("/") + "/metrics")
    data: Dict[str, Any] = {
        "metrics_status": metrics["status"],
        "metrics_error": metrics["error"],
    }
    if metrics["text"]:
        data["interesting_lines"] = interesting_metric_lines(metrics["text"])
    return data


def pearld_rpc(method: str, params: Optional[List[Any]] = None) -> Dict[str, Any]:
    if not PEARLD_RPC_USER or not PEARLD_RPC_PASSWORD:
        return {"error": "rpc_credentials_not_available"}
    body = json.dumps({"jsonrpc": "1.0", "id": method, "method": method, "params": params or []}).encode()
    password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_manager.add_password(None, PEARLD_RPC_URL, PEARLD_RPC_USER, PEARLD_RPC_PASSWORD)
    opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_manager))
    request = urllib.request.Request(
        PEARLD_RPC_URL,
        data=body,
        headers={"content-type": "text/plain"},
        method="POST",
    )
    try:
        with opener.open(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:
        return {"error": repr(exc)}
    if payload.get("error"):
        return {"error": payload.get("error")}
    return {"result": payload.get("result")}


def pearld_status() -> Dict[str, Any]:
    info = pearld_rpc("getinfo")
    height = pearld_rpc("getblockcount")
    template = pearld_rpc("getblocktemplate")
    return {
        "getinfo_error": info.get("error"),
        "height": height.get("result"),
        "height_error": height.get("error"),
        "template_available": "result" in template and template.get("result") is not None,
        "template_error": template.get("error"),
    }


def wallet_status() -> Dict[str, Any]:
    if not WALLET:
        return {"error": "wallet_not_set"}
    url = "https://lordofpearls.xyz/api/wallet?addr=" + urllib.parse.quote(WALLET, safe="")
    payload = fetch_json(url, timeout=4)
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    return {
        "status": payload.get("_http_status"),
        "error": payload.get("error"),
        "blocks_alltime": totals.get("blocks_mined_alltime"),
        "rewards_alltime": totals.get("rewards_earned_alltime"),
        "orphans_alltime": totals.get("orphans_count"),
        "rewards_lost": totals.get("rewards_lost"),
        "snapshot_age_seconds": totals.get("snapshot_age_seconds"),
    }


def public_network_status() -> Dict[str, Any]:
    payload = fetch_json("https://lordofpearls.xyz/api/public", timeout=4)
    network = payload.get("network") if isinstance(payload.get("network"), dict) else {}
    return {
        "status": payload.get("_http_status"),
        "error": payload.get("error"),
        "height": network.get("blocks"),
        "difficulty": network.get("difficulty"),
        "networkhashps": network.get("networkhashps"),
        "avg_block_time_s": network.get("avg_block_time_s"),
        "last_block_time": network.get("last_block_time"),
    }


def status_snapshot() -> Dict[str, Any]:
    return {
        "collected_at": now_iso(),
        "observer_uptime_seconds": round(time.time() - STARTED_AT, 1),
        "wallet": WALLET,
        "config": {
            "workers": os.environ.get("PEARL_WORKERS"),
            "max_tokens": os.environ.get("PEARL_MAX_TOKENS", "1"),
            "word_list": os.environ.get("PEARL_WORD_LIST"),
            "max_model_len": os.environ.get("PEARL_MAX_MODEL_LEN"),
            "gpu_util": os.environ.get("PEARL_GPU_UTIL"),
            "dp_size": os.environ.get("PEARL_DP_SIZE"),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "processes": {
            "pearld": process_status("pearld"),
            "pearl_gateway": process_status("pearl-gateway"),
            "vllm": process_status("vllm"),
            "worker": process_status("pearl_worker.py"),
        },
        "gpu": gpu_status(),
        "pearld": pearld_status(),
        "gateway": gateway_status(),
        "vllm": vllm_status(),
        "wallet_stats": wallet_status(),
        "network": public_network_status(),
    }


DASHBOARD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pearl Miner</title>
<style>
:root {
  color-scheme: dark;
  --bg: #101318;
  --panel: #171c23;
  --line: #2b3440;
  --text: #e6edf3;
  --muted: #9aa6b2;
  --good: #4ade80;
  --warn: #fbbf24;
  --bad: #fb7185;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--panel);
}
h1 { margin: 0; font-size: 22px; }
h2 { margin: 0 0 10px; font-size: 14px; color: var(--muted); text-transform: uppercase; }
main { padding: 20px 24px 28px; }
.muted { color: var(--muted); }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.card, section {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}
.label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
.value { font-size: 22px; font-weight: 700; margin-top: 4px; overflow-wrap: anywhere; }
.good { color: var(--good); }
.warn { color: var(--warn); }
.bad { color: var(--bad); }
table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 8px;
}
th, td {
  border-bottom: 1px solid var(--line);
  padding: 8px 6px;
  text-align: left;
  vertical-align: top;
}
pre {
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
}
@media (max-width: 760px) {
  header { display: block; }
  table { display: block; overflow-x: auto; }
}
</style>
</head>
<body>
<header>
  <div>
    <h1>Pearl Miner</h1>
    <div class="muted">Read-only status from this container</div>
  </div>
  <div class="muted" id="updated">Loading...</div>
</header>
<main>
  <div class="grid" id="cards"></div>
  <section>
    <h2>Processes</h2>
    <table><tbody id="processes"></tbody></table>
  </section>
  <section>
    <h2>Gateway Mining Metrics</h2>
    <pre id="gateway"></pre>
  </section>
</main>
<script>
const fmt = (value) => value === null || value === undefined || value === "" ? " -" : Number(value).toLocaleString(undefined, {maximumFractionDigits: 2});
const raw = (value) => value === null || value === undefined || value === "" ? " -" : String(value);
const card = (label, value, cls="") => `<div class="card"><div class="label">${label}</div><div class="value ${cls}">${value}</div></div>`;
const okClass = (ok) => ok ? "good" : "bad";
async function load() {
  const response = await fetch("/api/status", {cache: "no-store"});
  const data = await response.json();
  const v = data.vllm || {};
  const w = data.wallet_stats || {};
  const p = data.pearld || {};
  const gpu = ((data.gpu || {}).gpus || [])[0] || {};
  document.getElementById("updated").textContent = `Updated ${data.collected_at}`;
  document.getElementById("cards").innerHTML = [
    card("vLLM", raw(v.health_status), okClass(v.health_status === 200)),
    card("Requests", `${fmt(v.requests_running)}/${fmt(v.requests_waiting)}`),
    card("Prompt Tokens", fmt(v.prompt_tokens_total)),
    card("KV Cache", v.kv_cache_usage == null ? " -" : `${fmt(v.kv_cache_usage * 100)}%`),
    card("GPU", gpu.util_percent == null ? " -" : `${fmt(gpu.util_percent)}%`, Number(gpu.util_percent || 0) >= 80 ? "good" : "warn"),
    card("Height", raw(p.height), p.template_available ? "good" : "warn"),
    card("Paid Blocks", fmt(w.blocks_alltime), Number(w.blocks_alltime || 0) > 0 ? "good" : ""),
    card("Orphans", fmt(w.orphans_alltime), Number(w.orphans_alltime || 0) > 0 ? "warn" : "")
  ].join("");
  document.getElementById("processes").innerHTML = Object.entries(data.processes || {}).map(([name, info]) =>
    `<tr><td>${name}</td><td class="${okClass(info.running)}">${info.running ? "running" : "down"}</td><td>${(info.matches || []).join("<br>")}</td></tr>`
  ).join("");
  document.getElementById("gateway").textContent = ((data.gateway || {}).interesting_lines || []).join("\\n") || raw((data.gateway || {}).metrics_error);
}
load().catch((err) => { document.getElementById("updated").textContent = String(err); });
setInterval(load, 10000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/dashboard.html"):
            self.write(200, DASHBOARD, "text/html")
            return
        if self.path == "/health":
            self.write(200, "ok\n", "text/plain")
            return
        if self.path == "/api/status":
            self.write(200, json.dumps(status_snapshot(), sort_keys=True), "application/json")
            return
        self.write(404, "not found\n", "text/plain")

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def write(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", f"{content_type}; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Pearl observer listening on :{PORT}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
