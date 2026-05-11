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
from pathlib import Path
from typing import Any, Dict, List, Optional


PORT = int(os.environ.get("PEARL_OBSERVER_PORT", "8340"))
WALLET = os.environ.get("PEARL_WALLET_ADDRESS", "")
VLLM_URL = os.environ.get("PEARL_OBSERVER_VLLM_URL", "http://127.0.0.1:8000")
GATEWAY_URL = os.environ.get("PEARL_OBSERVER_GATEWAY_URL", "http://127.0.0.1:8339")
PEARLD_RPC_URL = os.environ.get("PEARLD_RPC_URL", "http://127.0.0.1:44107")
PEARLD_RPC_USER = os.environ.get("PEARLD_RPC_USER", "")
PEARLD_RPC_PASSWORD = os.environ.get("PEARLD_RPC_PASSWORD", "")
HTTP_TIMEOUT = float(os.environ.get("PEARL_OBSERVER_TIMEOUT", "2.5"))
LOG_DIR = Path(os.environ.get("PEARL_LOG_DIR", "/app/chain-data/logs"))
STARTED_AT = time.time()
LOG_FILES = {
    "pearld": "pearld.log",
    "gateway": "pearl-gateway.log",
    "vllm": "vllm.log",
    "worker": "pearl-worker.log",
    "observer": "miner-observer.log",
}
AUDIT_PATTERNS = {
    "block_found": "Block found",
    "creating_proof": "creating proof",
    "received_plain_proof": "Received PlainProof",
    "submitting_block": "Submitting block",
    "block_accepted_by_node": "Block accepted by node",
    "already_submitted": "already_submitted",
    "block_rejected": "Block rejected",
    "error_submitting": "Error submitting",
    "request_errors": "Error:",
    "timeouts": "Timeout",
    "template_refreshed": "Template refreshed",
    "pearl_kernel_mining_layers": "Using PearlKernel (mining_enabled=True)",
    "pearl_kernel_non_mining_layers": "Using PearlKernel (mining_enabled=False)",
    "mining_state_initialized_typo": "Mining state initalized",
    "mining_state_initialized": "Mining state initialized",
}
LOG_EVENT_NAMES = (
    "block_found",
    "creating_proof",
    "received_plain_proof",
    "submitting_block",
    "block_accepted_by_node",
    "already_submitted",
    "block_rejected",
    "error_submitting",
)
DEFAULT_LOG_EVENTS_LIMIT = 500
MAX_LOG_EVENTS_LIMIT = 5000


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


def redact_process_line(line: str) -> str:
    secret_prefixes = ("--rpcpass=", "--password=", "--token=", "--api-key=", "--apikey=")
    parts = []
    for part in line.split():
        lowered = part.lower()
        if any(lowered.startswith(prefix) for prefix in secret_prefixes):
            key = part.split("=", 1)[0]
            parts.append(key + "=REDACTED")
        else:
            parts.append(part)
    return " ".join(parts)


def process_status(name: str) -> Dict[str, Any]:
    result = run_json(["pgrep", "-fa", name])
    lines = [redact_process_line(line) for line in result.get("stdout", "").splitlines() if line]
    return {"running": bool(lines), "matches": lines[:5]}


def process_env(name: str) -> Dict[str, Any]:
    result = run_json(["pgrep", "-f", name])
    pids = [pid for pid in result.get("stdout", "").splitlines() if pid.strip().isdigit()]
    if not pids:
        return {"pid": None, "env": {}, "error": result.get("stderr") or result.get("error")}
    pid = pids[0].strip()
    path = Path("/proc") / pid / "environ"
    try:
        raw = path.read_bytes().decode("utf-8", "replace")
    except Exception as exc:
        return {"pid": pid, "env": {}, "error": repr(exc)}
    safe_prefixes = ("MINER_", "PEARL_", "VLLM_", "CUDA_")
    secret_fragments = ("TOKEN", "PASSWORD", "PASS", "KEY", "SECRET")
    env: Dict[str, str] = {}
    for item in raw.split("\0"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if not key.startswith(safe_prefixes):
            continue
        if any(fragment in key for fragment in secret_fragments):
            value = "SET" if value else ""
        env[key] = value
    return {"pid": pid, "env": dict(sorted(env.items())), "error": None}


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


def read_tail(path: Path, limit_bytes: int = 2_000_000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit_bytes), os.SEEK_SET)
            return handle.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return ""
    except Exception as exc:
        return f"__read_error__ {exc!r}"


def recent_matching_lines(texts: Dict[str, str], needles: List[str], limit: int = 80) -> List[Dict[str, str]]:
    recent = []
    lowered_needles = [needle.lower() for needle in needles]
    for source, text in texts.items():
        for line in text.splitlines()[-2500:]:
            lowered = line.lower()
            if any(needle in lowered for needle in lowered_needles):
                recent.append({"source": source, "line": line[-700:]})
    return recent[-limit:]


def mining_diagnostics(texts: Dict[str, str]) -> Dict[str, Any]:
    combined = "\n".join(texts.values())
    lowered = combined.lower()
    vllm_text = texts.get("vllm", "")
    worker_text = texts.get("worker", "")
    return {
        "counts": {
            "pearl_kernel_mining_layers": lowered.count(
                "using pearlkernel (mining_enabled=true)"
            ),
            "pearl_kernel_non_mining_layers": lowered.count(
                "using pearlkernel (mining_enabled=false)"
            ),
            "mining_state_initialized": lowered.count("mining state initalized")
            + lowered.count("mining state initialized"),
            "noisy_gemm_mentions": lowered.count("noisygemm")
            + lowered.count("noisy gemm")
            + lowered.count("noisy_gemm"),
            "chunked_prefill_mentions": lowered.count("chunked prefill")
            + lowered.count("chunked_prefill"),
        },
        "vllm_env": process_env("vllm serve"),
        "worker_env": process_env("pearl_worker.py"),
        "vllm_recent": recent_matching_lines(
            {"vllm": vllm_text},
            [
                "Using PearlKernel",
                "mining_enabled",
                "Mining state",
                "NoisyGEMM",
                "noisy gemm",
                "chunked prefill",
                "chunked_prefill",
            ],
            limit=40,
        ),
        "worker_recent_stats": [
            line[-500:] for line in worker_text.splitlines() if "[Stats]" in line
        ][-8:],
    }


def log_status() -> Dict[str, Any]:
    files = {name: LOG_DIR / filename for name, filename in LOG_FILES.items()}
    texts = {name: read_tail(path) for name, path in files.items()}

    combined = "\n".join(texts.values())
    counts = {
        name: combined.lower().count(pattern.lower())
        for name, pattern in AUDIT_PATTERNS.items()
    }
    recent_needles = (
        "block found",
        "proof",
        "submitting",
        "accepted",
        "already_submitted",
        "rejected",
        "error submitting",
        "template",
        "traceback",
        "exception",
    )
    recent = []
    for source, text in texts.items():
        for line in text.splitlines()[-1500:]:
            lowered = line.lower()
            if any(needle in lowered for needle in recent_needles):
                recent.append({"source": source, "line": line[-500:]})
    stats = {}
    for name, path in files.items():
        try:
            stat = path.stat()
            stats[name] = {
                "path": str(path),
                "bytes": stat.st_size,
                "mtime": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
            }
        except FileNotFoundError:
            stats[name] = {"path": str(path), "missing": True}
    return {
        "dir": str(LOG_DIR),
        "files": stats,
        "counts": counts,
        "mining_diagnostics": mining_diagnostics(texts),
        "recent": recent[-80:],
    }


def _line_has_any_event(line: str) -> bool:
    lowered = line.lower()
    return any(pattern.lower() in lowered for pattern in AUDIT_PATTERNS.values())


def full_log_audit() -> Dict[str, Any]:
    started = time.time()
    totals = {name: 0 for name in AUDIT_PATTERNS}
    files: Dict[str, Any] = {}
    first_events: List[Dict[str, Any]] = []
    last_events: List[Dict[str, Any]] = []

    for source, filename in LOG_FILES.items():
        path = LOG_DIR / filename
        file_counts = {name: 0 for name in AUDIT_PATTERNS}
        line_count = 0
        file_first: List[Dict[str, Any]] = []
        file_last: List[Dict[str, Any]] = []
        error = None
        stat_payload: Dict[str, Any] = {"path": str(path)}

        try:
            stat = path.stat()
            stat_payload.update(
                {
                    "bytes": stat.st_size,
                    "mtime": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, 1):
                    line_count = line_number
                    lowered = line.lower()
                    matched = []
                    for name, pattern in AUDIT_PATTERNS.items():
                        count = lowered.count(pattern.lower())
                        if count:
                            file_counts[name] += count
                            totals[name] += count
                            matched.append(name)
                    if matched and _line_has_any_event(line):
                        event = {
                            "source": source,
                            "line_number": line_number,
                            "matched": matched,
                            "line": line.rstrip("\n")[-700:],
                        }
                        if len(file_first) < 10:
                            file_first.append(event)
                        file_last.append(event)
                        file_last = file_last[-10:]
        except FileNotFoundError:
            stat_payload["missing"] = True
        except Exception as exc:
            error = repr(exc)

        files[source] = {
            **stat_payload,
            "line_count": line_count,
            "counts": file_counts,
            "error": error,
            "first_events": file_first,
            "last_events": file_last,
        }
        first_events.extend(file_first)
        last_events.extend(file_last)
        last_events = last_events[-40:]

    proof_totals = {
        name: totals.get(name, 0)
        for name in (
            "block_found",
            "creating_proof",
            "received_plain_proof",
            "submitting_block",
            "block_accepted_by_node",
            "already_submitted",
            "block_rejected",
            "error_submitting",
        )
    }
    return {
        "collected_at": now_iso(),
        "duration_seconds": round(time.time() - started, 3),
        "log_dir": str(LOG_DIR),
        "totals": totals,
        "proof_totals": proof_totals,
        "files": files,
        "first_events": first_events[:40],
        "last_events": last_events,
    }


def parse_limit(query: Dict[str, List[str]], default: int, maximum: int) -> int:
    values = query.get("limit") or []
    if not values:
        return default
    try:
        limit = int(values[0])
    except Exception:
        return default
    return max(1, min(limit, maximum))


def log_events(limit: int = DEFAULT_LOG_EVENTS_LIMIT, include_all: bool = False) -> Dict[str, Any]:
    started = time.time()
    event_names = tuple(AUDIT_PATTERNS) if include_all else LOG_EVENT_NAMES
    totals = {name: 0 for name in event_names}
    files: Dict[str, Any] = {}
    events: List[Dict[str, Any]] = []

    for source, filename in LOG_FILES.items():
        path = LOG_DIR / filename
        file_counts = {name: 0 for name in event_names}
        line_count = 0
        error = None
        stat_payload: Dict[str, Any] = {"path": str(path)}

        try:
            stat = path.stat()
            stat_payload.update(
                {
                    "bytes": stat.st_size,
                    "mtime": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc)
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, 1):
                    line_count = line_number
                    lowered = line.lower()
                    matched = []
                    for name in event_names:
                        pattern = AUDIT_PATTERNS[name]
                        count = lowered.count(pattern.lower())
                        if count:
                            file_counts[name] += count
                            totals[name] += count
                            matched.append(name)
                    if matched:
                        events.append(
                            {
                                "source": source,
                                "line_number": line_number,
                                "matched": matched,
                                "line": line.rstrip("\n")[-1200:],
                            }
                        )
                        events = events[-limit:]
        except FileNotFoundError:
            stat_payload["missing"] = True
        except Exception as exc:
            error = repr(exc)

        files[source] = {
            **stat_payload,
            "line_count": line_count,
            "counts": file_counts,
            "error": error,
        }

    return {
        "collected_at": now_iso(),
        "duration_seconds": round(time.time() - started, 3),
        "log_dir": str(LOG_DIR),
        "limit": limit,
        "include_all": include_all,
        "event_names": list(event_names),
        "totals": totals,
        "files": files,
        "events": events,
    }


def status_snapshot() -> Dict[str, Any]:
    return {
        "collected_at": now_iso(),
        "observer_uptime_seconds": round(time.time() - STARTED_AT, 1),
        "wallet": WALLET,
        "config": {
            "network": os.environ.get("PEARL_NETWORK", "mainnet"),
            "pearld_rpc_port": os.environ.get("PEARLD_RPC_PORT", "44107"),
            "pearld_listen_port": os.environ.get("PEARLD_LISTEN_PORT"),
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
        "logs": log_status(),
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
  <section>
    <h2>Proof / Submission Logs</h2>
    <pre id="logs"></pre>
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
  const logCounts = ((data.logs || {}).counts || {});
  const gpu = ((data.gpu || {}).gpus || [])[0] || {};
  document.getElementById("updated").textContent = `Updated ${data.collected_at}`;
  document.getElementById("cards").innerHTML = [
    card("vLLM", raw(v.health_status), okClass(v.health_status === 200)),
    card("Requests", `${fmt(v.requests_running)}/${fmt(v.requests_waiting)}`),
    card("Prompt Tokens", fmt(v.prompt_tokens_total)),
    card("KV Cache", v.kv_cache_usage == null ? " -" : `${fmt(v.kv_cache_usage * 100)}%`),
    card("GPU", gpu.util_percent == null ? " -" : `${fmt(gpu.util_percent)}%`, Number(gpu.util_percent || 0) >= 80 ? "good" : "warn"),
    card("Height", raw(p.height), p.template_available ? "good" : "warn"),
    card("Found", fmt(logCounts.block_found), Number(logCounts.block_found || 0) > 0 ? "good" : ""),
    card("Proofs", fmt(logCounts.received_plain_proof), Number(logCounts.received_plain_proof || 0) > 0 ? "good" : ""),
    card("Submits", fmt(logCounts.submitting_block), Number(logCounts.submitting_block || 0) > 0 ? "good" : ""),
    card("Accepted", fmt(logCounts.block_accepted_by_node), Number(logCounts.block_accepted_by_node || 0) > 0 ? "good" : ""),
    card("Already", fmt(logCounts.already_submitted), Number(logCounts.already_submitted || 0) > 0 ? "warn" : ""),
    card("Rejected", fmt(logCounts.block_rejected), Number(logCounts.block_rejected || 0) > 0 ? "bad" : ""),
    card("Paid Blocks", fmt(w.blocks_alltime), Number(w.blocks_alltime || 0) > 0 ? "good" : ""),
    card("Orphans", fmt(w.orphans_alltime), Number(w.orphans_alltime || 0) > 0 ? "warn" : "")
  ].join("");
  document.getElementById("processes").innerHTML = Object.entries(data.processes || {}).map(([name, info]) =>
    `<tr><td>${name}</td><td class="${okClass(info.running)}">${info.running ? "running" : "down"}</td><td>${(info.matches || []).join("<br>")}</td></tr>`
  ).join("");
  document.getElementById("gateway").textContent = ((data.gateway || {}).interesting_lines || []).join("\\n") || raw((data.gateway || {}).metrics_error);
  document.getElementById("logs").textContent = (((data.logs || {}).recent || []).map((item) => `[${item.source}] ${item.line}`).join("\\n")) || "No proof/submission log lines yet.";
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
        if self.path == "/api/log-audit":
            self.write(200, json.dumps(full_log_audit(), sort_keys=True), "application/json")
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/log-events":
            query = urllib.parse.parse_qs(parsed.query)
            include_all = (query.get("include_all") or ["0"])[0] in ("1", "true", "yes")
            limit = parse_limit(query, DEFAULT_LOG_EVENTS_LIMIT, MAX_LOG_EVENTS_LIMIT)
            self.write(
                200,
                json.dumps(log_events(limit=limit, include_all=include_all), sort_keys=True),
                "application/json",
            )
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
