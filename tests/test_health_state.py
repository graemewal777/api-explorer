import copy
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import healthcheck  # noqa: E402
from healthcheck import Result  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample.md"


def res(url, outcome, status=200):
    return Result(url, outcome, status, 0)


class UpdateStateTests(unittest.TestCase):
    URLS = ["https://a.example/", "https://b.example/", "https://c.example/"]

    def update(self, old, results, today="2026-10-22", urls=None):
        return healthcheck.update_state(old, results, today, urls or self.URLS)

    def test_first_failure_creates_an_entry(self):
        state = self.update(healthcheck.empty_state(), {"https://a.example/": res("https://a.example/", "dns", 0)})
        self.assertEqual(state["failing"]["https://a.example/"], {"failures": 1, "first_failed": "2026-10-22", "error": "dns"})
        self.assertEqual(state["last_run"], "2026-10-22")

    def test_consecutive_failure_increments_and_keeps_first_failed(self):
        old = {"last_run": "2026-10-21", "failing": {"https://a.example/": {"failures": 1, "first_failed": "2026-10-21", "error": "dns"}}}
        state = self.update(old, {"https://a.example/": res("https://a.example/", "timeout", 0)})
        self.assertEqual(state["failing"]["https://a.example/"], {"failures": 2, "first_failed": "2026-10-21", "error": "timeout"})

    def test_ok_and_blocked_both_clear_the_entry(self):
        old = {"last_run": "x", "failing": {
            "https://a.example/": {"failures": 2, "first_failed": "d", "error": "dns"},
            "https://b.example/": {"failures": 4, "first_failed": "d", "error": "gone"},
        }}
        state = self.update(old, {
            "https://a.example/": res("https://a.example/", "ok"),
            "https://b.example/": res("https://b.example/", "blocked", 403),
        })
        self.assertEqual(state["failing"], {})

    def test_failure_count_is_capped(self):
        old = {"last_run": "x", "failing": {"https://a.example/": {"failures": healthcheck.FAILURE_CAP, "first_failed": "d", "error": "gone"}}}
        state = self.update(old, {"https://a.example/": res("https://a.example/", "gone", 404)})
        self.assertEqual(state["failing"]["https://a.example/"]["failures"], healthcheck.FAILURE_CAP)

    def test_url_that_was_not_probed_keeps_its_old_entry(self):
        entry = {"failures": 2, "first_failed": "2026-10-20", "error": "dns"}
        old = {"last_run": "x", "failing": {"https://c.example/": entry}}
        state = self.update(old, {"https://a.example/": res("https://a.example/", "ok")})
        self.assertEqual(state["failing"], {"https://c.example/": entry})

    def test_url_no_longer_in_the_list_is_pruned(self):
        old = {"last_run": "x", "failing": {"https://removed.example/": {"failures": 3, "first_failed": "d", "error": "gone"}}}
        state = self.update(old, {"https://a.example/": res("https://a.example/", "ok")})
        self.assertEqual(state["failing"], {})

    def test_input_state_is_not_mutated(self):
        old = {"last_run": "2026-10-21", "failing": {"https://a.example/": {"failures": 1, "first_failed": "d", "error": "dns"}}}
        snapshot = copy.deepcopy(old)
        self.update(old, {"https://a.example/": res("https://a.example/", "dns", 0)})
        self.assertEqual(old, snapshot)

    def test_all_ok_run_on_empty_state(self):
        state = self.update(healthcheck.empty_state(), {u: res(u, "ok") for u in self.URLS})
        self.assertEqual(state, {"last_run": "2026-10-22", "failing": {}})


class StateFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "data" / "health.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_is_an_empty_state(self):
        self.assertEqual(healthcheck.load_state(self.path), healthcheck.empty_state())

    def test_round_trip(self):
        state = {"last_run": "2026-10-22", "failing": {"https://a.example/": {"failures": 2, "first_failed": "2026-10-21", "error": "dns"}}}
        healthcheck.save_state(self.path, state)
        self.assertEqual(healthcheck.load_state(self.path), state)

    def test_output_is_deterministic_sorted_and_newline_terminated(self):
        failing_a = {"failures": 1, "first_failed": "d", "error": "dns"}
        one = {"last_run": "d", "failing": {"https://b/": failing_a, "https://a/": failing_a}}
        two = {"failing": {"https://a/": failing_a, "https://b/": failing_a}, "last_run": "d"}
        healthcheck.save_state(self.path, one)
        first = self.path.read_bytes()
        healthcheck.save_state(self.path, two)
        self.assertEqual(self.path.read_bytes(), first)
        self.assertTrue(first.endswith(b"\n"))
        text = first.decode()
        self.assertLess(text.index("https://a/"), text.index("https://b/"))

    def test_corrupt_file_stops_the_run_instead_of_resetting_every_counter(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ not json")
        with self.assertRaises(ValueError):
            healthcheck.load_state(self.path)

    def test_file_with_the_wrong_shape_is_rejected(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"failing": ["nope"]}))
        with self.assertRaises(ValueError):
            healthcheck.load_state(self.path)


class InterleaveTests(unittest.TestCase):
    def test_round_robin_across_hosts_and_dedup(self):
        urls = ["https://a.example/1", "https://a.example/2", "https://a.example/3", "https://b.example/1", "https://c.example/1", "https://a.example/1"]
        self.assertEqual(
            healthcheck.interleave_by_host(urls),
            ["https://a.example/1", "https://b.example/1", "https://c.example/1", "https://a.example/2", "https://a.example/3"],
        )


class RunTests(unittest.TestCase):
    def test_every_unique_url_gets_a_result(self):
        urls = ["https://a.example/1", "https://b.example/1", "https://a.example/1"]
        results = healthcheck.run(urls, probe_fn=lambda u: res(u, "ok"), workers=4, host_spacing=0)
        self.assertEqual(sorted(results), ["https://a.example/1", "https://b.example/1"])

    def test_one_request_at_a_time_per_host_but_hosts_run_in_parallel(self):
        lock = threading.Lock()
        active = {}
        peak_per_host = {}
        peak_total = [0]

        def fake_probe(url):
            host = url.split("/")[2]
            with lock:
                active[host] = active.get(host, 0) + 1
                peak_per_host[host] = max(peak_per_host.get(host, 0), active[host])
                peak_total[0] = max(peak_total[0], sum(active.values()))
            time.sleep(0.05)
            with lock:
                active[host] -= 1
            return res(url, "ok")

        urls = [f"https://{h}.example/{i}" for h in "abc" for i in range(4)]
        healthcheck.run(urls, probe_fn=fake_probe, workers=12, host_spacing=0)
        self.assertEqual(max(peak_per_host.values()), 1)
        self.assertGreater(peak_total[0], 1)

    def test_same_host_requests_are_spaced(self):
        starts = []
        lock = threading.Lock()

        def fake_probe(url):
            with lock:
                starts.append(time.monotonic())
            return res(url, "ok")

        healthcheck.run(["https://a.example/1", "https://a.example/2", "https://a.example/3"], probe_fn=fake_probe, workers=3, host_spacing=0.15)
        starts.sort()
        gaps = [later - earlier for earlier, later in zip(starts, starts[1:])]
        self.assertTrue(all(gap >= 0.14 for gap in gaps), gaps)


class CanaryTests(unittest.TestCase):
    CANARIES = ["https://one.example/", "https://two.example/", "https://three.example/", "https://four.example/", "https://five.example/"]

    def probe_failing(self, failing):
        return lambda url: res(url, "dns" if url in failing else "ok", 0)

    def test_all_reachable(self):
        self.assertTrue(healthcheck.canaries_ok(self.probe_failing(set()), self.CANARIES))

    def test_one_failure_is_tolerated(self):
        self.assertTrue(healthcheck.canaries_ok(self.probe_failing({self.CANARIES[0]}), self.CANARIES))

    def test_two_failures_trip_the_guard(self):
        self.assertFalse(healthcheck.canaries_ok(self.probe_failing(set(self.CANARIES[:2])), self.CANARIES))

    def test_a_blocked_canary_still_counts_as_reachable(self):
        probe = lambda url: res(url, "blocked", 403)  # noqa: E731
        self.assertTrue(healthcheck.canaries_ok(probe, self.CANARIES))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name) / "health.json"
        self.urls, _ = __import__("build").parse_readme(FIXTURE.read_text(encoding="utf-8"))
        self.urls = sorted({a["url"] for a in self.urls})

    def tearDown(self):
        self.dir.cleanup()

    def main(self, outcomes, *extra, canary_ok=True):
        def fake_probe(url):
            if url in healthcheck.CANARIES:
                return res(url, "ok" if canary_ok else "dns", 0)
            return res(url, outcomes.get(url, "ok"), 0)

        argv = ["--readme", str(FIXTURE), "--state", str(self.state), "--workers", "2", "--spacing", "0", "--min-urls", "1", *extra]
        return healthcheck.main(argv, probe_fn=fake_probe, today="2026-10-22")

    def test_failures_accumulate_over_runs_then_recover(self):
        bad = self.urls[0]
        self.main({bad: "dns"})
        self.assertEqual(healthcheck.load_state(self.state)["failing"][bad]["failures"], 1)
        self.main({bad: "dns"})
        self.assertEqual(healthcheck.load_state(self.state)["failing"][bad]["failures"], 2)
        self.main({})
        self.assertEqual(healthcheck.load_state(self.state)["failing"], {})

    def test_canary_failure_aborts_and_leaves_state_untouched(self):
        # Seeded in compact JSON, a format save_state would rewrite, so any write at all shows up as changed bytes.
        seeded = {"last_run": "2026-10-21", "failing": {self.urls[0]: {"failures": 2, "first_failed": "2026-10-20", "error": "dns"}}}
        self.state.write_text(json.dumps(seeded))
        before = self.state.read_bytes()
        with self.assertRaises(SystemExit) as raised:
            self.main({self.urls[0]: "ok"}, canary_ok=False)
        self.assertNotEqual(raised.exception.code, 0)
        self.assertEqual(self.state.read_bytes(), before)

    def test_dry_run_writes_nothing(self):
        self.main({self.urls[0]: "dns"}, "--dry-run")
        self.assertFalse(self.state.exists())

    def test_limit_probes_a_subset_and_never_writes_state(self):
        self.main({}, "--limit", "2")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
