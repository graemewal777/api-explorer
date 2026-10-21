#!/usr/bin/env python3
"""Probe API URLs and classify what comes back.

Uses the curl binary: it uses the system certificate store, which Python's own
ssl module does not always have (python.org builds on macOS ship without one,
and flag nearly every HTTPS site as broken).

Classes: ok, blocked (reachable but refuses bots: not a failure), and the
failure classes gone, error, dns, refused, timeout, tls, network.
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from collections import Counter, namedtuple
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

USER_AGENT = "api-explorer-healthcheck/1.0 (+https://github.com/graemewal777/api-explorer)"
TIMEOUT = 10
MAX_REDIRECTS = 5
RETRY_DELAY = 2.0

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "health.json"

FAILURE_CAP = 5
WORKERS = 25
HOST_SPACING = 0.5

# Sites that are essentially always up. If two of these fail, the run's own
# network or certificates are broken and nothing it says about other sites can be trusted.
CANARIES = [
    "https://github.com/",
    "https://example.com/",
    "https://www.wikipedia.org/",
    "https://www.python.org/",
    "https://www.cloudflare.com/",
]
CANARY_MAX_FAILURES = 2

OK = "ok"
BLOCKED = "blocked"
FAILURE_CLASSES = {"gone", "error", "dns", "refused", "timeout", "tls", "network"}

CURL_FAILURES = {
    6: "dns",
    7: "refused",
    28: "timeout",
    35: "tls",
    51: "tls",
    58: "tls",
    59: "tls",
    60: "tls",
    77: "tls",
    83: "tls",
}

Result = namedtuple("Result", "url outcome status exit_code")


def classify(exit_code, status, headers):
    """Map a curl exit code, final HTTP status and final response headers to a class."""
    if exit_code != 0:
        return CURL_FAILURES.get(exit_code, "network")

    server = headers.get("server", "").lower()
    cloudflare_challenge = headers.get("cf-mitigated", "").lower() == "challenge" or (
        status in (403, 503) and "cloudflare" in server
    )

    if cloudflare_challenge or status == 999:  # 999: a non-standard "request denied"
        return BLOCKED
    if 200 <= status < 400:
        return OK
    if status in (404, 410):
        return "gone"
    if 400 <= status < 500:
        return BLOCKED  # 401, 403, 429 and friends: the server answered, we can't tell the page is gone
    return "error"


def _parse(stdout):
    """Return (final_status, final_headers) from `-D -` output plus our status marker."""
    head, _, marker = stdout.rpartition("__STATUS__")
    try:
        status = int(marker.strip())
    except ValueError:
        status = 0

    lines = head.splitlines()
    start = max((i for i, line in enumerate(lines) if line.startswith("HTTP/")), default=None)
    headers = {}
    if start is not None:
        for line in lines[start + 1:]:
            if not line.strip():
                break
            key, sep, value = line.partition(":")
            if sep:
                headers[key.strip().lower()] = value.strip()
    return status, headers


def _curl(url, head, timeout):
    command = [
        "curl", "-sS", "-o", "/dev/null", "-D", "-",
        "-L", "--max-redirs", str(MAX_REDIRECTS),
        "--proto", "=http,https", "--proto-redir", "=http,https",
        "--max-time", str(timeout),
        "-A", USER_AGENT,
        "-w", "\n__STATUS__%{http_code}",
    ]
    if head:
        command.append("-I")
    command += ["--", url]

    try:
        completed = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        return 28, 0, {}
    except FileNotFoundError:
        raise RuntimeError("curl was not found; the health check needs it installed")

    status, headers = _parse(completed.stdout)
    return completed.returncode, status, headers


def _probe_once(url, timeout):
    # Many servers reject HEAD or answer it differently, so any non-ok HEAD gets a GET.
    exit_code, status, headers = _curl(url, head=True, timeout=timeout)
    outcome = classify(exit_code, status, headers)
    if outcome != OK:
        exit_code, status, headers = _curl(url, head=False, timeout=timeout)
        outcome = classify(exit_code, status, headers)
    return Result(url, outcome, status, exit_code)


def probe(url, timeout=TIMEOUT, retries=1, retry_delay=RETRY_DELAY):
    """Probe one URL. A failure is retried before it is believed."""
    result = _probe_once(url, timeout)
    for _ in range(retries):
        if result.outcome not in FAILURE_CLASSES:
            break
        time.sleep(retry_delay)
        result = _probe_once(url, timeout)
    return result


# ---- state -----------------------------------------------------------------

def empty_state():
    return {"last_run": None, "failing": {}}


def _valid_state(state):
    if not isinstance(state, dict) or not isinstance(state.get("failing"), dict):
        return False
    if state.get("last_run") is not None and not isinstance(state["last_run"], str):
        return False
    for url, entry in state["failing"].items():
        if not isinstance(url, str) or not isinstance(entry, dict):
            return False
        if not isinstance(entry.get("failures"), int) or not isinstance(entry.get("first_failed"), str) or not isinstance(entry.get("error"), str):
            return False
    return True


def load_state(path):
    """Missing file means a first run. A damaged file stops the run: guessing would reset every counter."""
    path = Path(path)
    if not path.exists():
        return empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON ({error}); fix or delete it") from error
    if not _valid_state(state):
        raise ValueError(f"{path} does not look like a health state file; fix or delete it")
    return state


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(state, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def update_state(old, results, today, current_urls):
    """Return the new state. `results` maps url -> Result for the URLs probed this run.

    Failing URLs count up (capped); ok and blocked URLs are cleared. A URL that was not
    probed keeps its old entry, and a URL that has left the list is dropped.
    """
    current = set(current_urls)
    failing = {}
    for url, entry in old["failing"].items():
        if url in current and url not in results:
            failing[url] = dict(entry)

    for url, result in results.items():
        if url not in current or result.outcome not in FAILURE_CLASSES:
            continue
        previous = old["failing"].get(url)
        failing[url] = {
            "failures": min((previous["failures"] if previous else 0) + 1, FAILURE_CAP),
            "first_failed": previous["first_failed"] if previous else today,
            "error": result.outcome,
        }
    return {"last_run": today, "failing": failing}


# ---- running ---------------------------------------------------------------

def _host(url):
    return urlparse(url).netloc.lower()


def interleave_by_host(urls):
    """Unique URLs, round-robin across hosts, so no single host's pile-up stalls the worker pool."""
    by_host = {}
    for url in dict.fromkeys(urls):
        by_host.setdefault(_host(url), []).append(url)
    queues = list(by_host.values())
    ordered = []
    for position in range(max((len(queue) for queue in queues), default=0)):
        ordered += [queue[position] for queue in queues if position < len(queue)]
    return ordered


class _HostGate:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_finished = float("-inf")


def run(urls, probe_fn=probe, workers=WORKERS, host_spacing=HOST_SPACING, progress=None):
    """Probe every unique URL. At most one request at a time per host, spaced apart."""
    ordered = interleave_by_host(urls)
    gates = {_host(url): _HostGate() for url in ordered}
    done = [0]
    done_lock = threading.Lock()

    def task(url):
        gate = gates[_host(url)]
        with gate.lock:
            wait = gate.last_finished + host_spacing - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                result = probe_fn(url)
            finally:
                gate.last_finished = time.monotonic()
        if progress:
            with done_lock:
                done[0] += 1
                progress(done[0], len(ordered))
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(task, ordered))
    return {result.url: result for result in results}


def canaries_ok(probe_fn=probe, canaries=CANARIES):
    failures = [url for url in canaries if probe_fn(url).outcome in FAILURE_CLASSES]
    return len(failures) < CANARY_MAX_FAILURES


# ---- command line ----------------------------------------------------------

def main(argv=None, probe_fn=probe, today=None):
    import build  # here, not at the top: build.py imports this module for the state loader

    parser = argparse.ArgumentParser(description="Probe every API URL and update the failure state.")
    parser.add_argument("--readme", type=Path, default=build.README)
    parser.add_argument("--state", type=Path, default=STATE_PATH)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--spacing", type=float, default=HOST_SPACING, help="seconds between requests to the same host")
    parser.add_argument("--min-urls", type=int, default=build.MIN_APIS, help="refuse to run if the README yields fewer URLs")
    parser.add_argument("--limit", type=int, help="probe only this many URLs (implies --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="probe and report, but do not write the state file")
    args = parser.parse_args(argv)

    today = today or datetime.now(timezone.utc).date().isoformat()
    dry_run = args.dry_run or args.limit is not None

    old = load_state(args.state)  # first: a damaged file should fail in seconds, not after the probes

    apis, _ = build.parse_readme(args.readme.read_text(encoding="utf-8"))
    all_urls = sorted({api["url"] for api in apis})
    if len(all_urls) < args.min_urls:
        sys.exit(f"healthcheck aborted: only {len(all_urls)} URLs found (expected at least {args.min_urls}); the README format may have changed")

    if not canaries_ok(probe_fn):
        print("healthcheck aborted: canary guard tripped (known-good sites are failing from here). State left untouched.", file=sys.stderr)
        sys.exit(1)

    to_probe = interleave_by_host(all_urls)
    if args.limit is not None:
        to_probe = to_probe[: args.limit]

    def progress(done, total):
        if done % 250 == 0 or done == total:
            print(f"  probed {done}/{total}", file=sys.stderr)

    results = run(to_probe, probe_fn=probe_fn, workers=args.workers, host_spacing=args.spacing, progress=progress)
    new = update_state(old, results, today, all_urls)

    histogram = Counter(result.outcome for result in results.values())
    newly = sorted(set(new["failing"]) - set(old["failing"]))
    recovered = sorted((set(old["failing"]) - set(new["failing"])) & set(results))
    print(f"probed {len(results)} of {len(all_urls)} URLs: " + ", ".join(f"{name} {count}" for name, count in histogram.most_common()))
    print(f"failing now: {len(new['failing'])} ({len(newly)} new, {len(recovered)} recovered)")

    if dry_run:
        print("dry run: state file not written")
    else:
        save_state(args.state, new)
        print(f"wrote {args.state}")
    return new


if __name__ == "__main__":
    main()
