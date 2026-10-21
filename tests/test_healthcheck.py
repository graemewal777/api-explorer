import socket
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import healthcheck  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    flaky_hits = 0

    def log_message(self, *args):
        pass

    def _send(self, status, headers=None, location=None):
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _route(self, is_head):
        path = self.path
        if path == "/ok":
            self._send(200)
        elif path == "/gone":
            self._send(404)
        elif path == "/410":
            self._send(410)
        elif path == "/boom":
            self._send(500)
        elif path == "/forbidden":
            self._send(403)
        elif path == "/teapot":
            self._send(418)
        elif path == "/head405":
            self._send(405 if is_head else 200)
        elif path == "/redirect":
            self._send(302, location="/ok")
        elif path == "/redirect-to-gone":
            self._send(302, location="/gone")
        elif path == "/loop":
            self._send(302, location="/loop")
        elif path == "/slow":
            time.sleep(3)
            self._send(200)
        elif path == "/cf403":
            self._send(403, {"Server": "cloudflare"})
        elif path == "/cf503":
            self._send(503, {"Server": "cloudflare"})
        elif path == "/cf-challenge":
            self._send(200, {"cf-mitigated": "challenge"})
        elif path == "/cf521":
            self._send(521, {"Server": "cloudflare"})
        elif path == "/plain503":
            self._send(503)
        elif path == "/flaky":
            Handler.flaky_hits += 1
            self._send(500 if Handler.flaky_hits <= 2 else 200)
        else:
            self._send(404)

    def do_HEAD(self):
        self._route(True)

    def do_GET(self):
        self._route(False)


class ClassifyTests(unittest.TestCase):
    def test_table(self):
        cases = [
            (0, 200, {}, "ok"),
            (0, 204, {}, "ok"),
            (0, 304, {}, "ok"),
            (0, 401, {}, "blocked"),
            (0, 403, {}, "blocked"),
            (0, 429, {}, "blocked"),
            (0, 999, {}, "blocked"),
            (0, 400, {}, "blocked"),
            (0, 418, {}, "blocked"),
            (0, 451, {}, "blocked"),
            (0, 404, {}, "gone"),
            (0, 410, {}, "gone"),
            (0, 500, {}, "error"),
            (0, 502, {}, "error"),
            (0, 503, {}, "error"),
            (0, 403, {"server": "cloudflare"}, "blocked"),
            (0, 503, {"server": "cloudflare"}, "blocked"),
            (0, 521, {"server": "cloudflare"}, "error"),
            (0, 200, {"cf-mitigated": "challenge"}, "blocked"),
            (6, 0, {}, "dns"),
            (7, 0, {}, "refused"),
            (28, 0, {}, "timeout"),
            (60, 0, {}, "tls"),
            (35, 0, {}, "tls"),
            (47, 0, {}, "network"),
            (56, 0, {}, "network"),
            (3, 0, {}, "network"),
            (99, 0, {}, "network"),
        ]
        for exit_code, status, headers, expected in cases:
            with self.subTest(exit_code=exit_code, status=status, headers=headers):
                self.assertEqual(healthcheck.classify(exit_code, status, headers), expected)

    def test_failure_classes_are_exactly_the_non_ok_non_blocked_ones(self):
        self.assertEqual(
            healthcheck.FAILURE_CLASSES,
            {"gone", "error", "dns", "refused", "timeout", "tls", "network"},
        )
        self.assertNotIn("ok", healthcheck.FAILURE_CLASSES)
        self.assertNotIn("blocked", healthcheck.FAILURE_CLASSES)


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def probe(self, path, **kwargs):
        kwargs.setdefault("retry_delay", 0)
        kwargs.setdefault("timeout", 5)
        return healthcheck.probe(self.base + path, **kwargs)

    def test_ok(self):
        result = self.probe("/ok")
        self.assertEqual((result.outcome, result.status), ("ok", 200))

    def test_redirect_to_ok_is_ok(self):
        self.assertEqual(self.probe("/redirect").outcome, "ok")

    def test_redirect_to_gone_is_gone(self):
        self.assertEqual(self.probe("/redirect-to-gone").outcome, "gone")

    def test_404_and_410_are_gone(self):
        self.assertEqual(self.probe("/gone").outcome, "gone")
        self.assertEqual(self.probe("/410").outcome, "gone")

    def test_500_is_error(self):
        self.assertEqual(self.probe("/boom", retries=0).outcome, "error")

    def test_bot_blocking_is_blocked_not_a_failure(self):
        for path in ("/forbidden", "/teapot", "/cf403", "/cf503", "/cf-challenge"):
            with self.subTest(path=path):
                result = self.probe(path)
                self.assertEqual(result.outcome, "blocked")
                self.assertNotIn(result.outcome, healthcheck.FAILURE_CLASSES)

    def test_cloudflare_origin_down_is_a_real_failure(self):
        self.assertEqual(self.probe("/cf521", retries=0).outcome, "error")
        self.assertEqual(self.probe("/plain503", retries=0).outcome, "error")

    def test_head_rejected_but_get_works_is_ok(self):
        self.assertEqual(self.probe("/head405").outcome, "ok")

    def test_redirect_loop_is_network_failure(self):
        self.assertEqual(self.probe("/loop", retries=0).outcome, "network")

    def test_slow_endpoint_times_out(self):
        result = self.probe("/slow", timeout=1, retries=0)
        self.assertEqual(result.outcome, "timeout")

    def test_one_retry_rescues_a_flaky_endpoint(self):
        Handler.flaky_hits = 0
        self.assertEqual(self.probe("/flaky", retries=1).outcome, "ok")

    def test_without_retry_the_flaky_endpoint_fails(self):
        Handler.flaky_hits = 0
        self.assertEqual(self.probe("/flaky", retries=0).outcome, "error")

    def test_closed_port_is_refused(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        result = healthcheck.probe(f"http://127.0.0.1:{port}/", retries=0, timeout=5)
        self.assertEqual(result.outcome, "refused")

    def test_unresolvable_host_is_dns(self):
        result = healthcheck.probe("http://does-not-exist.invalid/", retries=0, timeout=5)
        self.assertEqual(result.outcome, "dns")

    def test_non_http_urls_are_never_fetched(self):
        for url in ("file:///etc/hosts", "ftp://127.0.0.1/x", "gopher://127.0.0.1/x"):
            with self.subTest(url=url):
                self.assertEqual(healthcheck.probe(url, retries=0, timeout=3).outcome, "network")

    def test_url_that_looks_like_a_curl_option_is_treated_as_a_hostname(self):
        # Read as an option, curl would print its version and exit 0. Read as a URL
        # (what the `--` guard guarantees) it is a hostname that does not resolve.
        result = healthcheck.probe("--version", retries=0, timeout=3)
        self.assertEqual(result.outcome, "dns")


if __name__ == "__main__":
    unittest.main()
