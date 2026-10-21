#!/usr/bin/env python3
"""Probe API URLs and classify what comes back.

Uses the curl binary: it uses the system certificate store, which Python's own
ssl module does not always have (python.org builds on macOS ship without one,
and flag nearly every HTTPS site as broken).

Classes: ok, blocked (reachable but refuses bots: not a failure), and the
failure classes gone, error, dns, refused, timeout, tls, network.
"""
import subprocess
import time
from collections import namedtuple

USER_AGENT = "api-explorer-healthcheck/1.0 (+https://github.com/graemewal777/api-explorer)"
TIMEOUT = 10
MAX_REDIRECTS = 5
RETRY_DELAY = 2.0

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
