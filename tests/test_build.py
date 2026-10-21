import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa: E402

FIXTURE = (ROOT / "tests" / "fixtures" / "sample.md").read_text(encoding="utf-8")


class ParseReadmeTests(unittest.TestCase):
    def setUp(self):
        self.apis, self.stats = build.parse_readme(FIXTURE)
        self.by_name = {a["name"]: a for a in self.apis}

    def test_only_standard_tables_are_parsed(self):
        self.assertEqual(
            sorted(self.by_name),
            [
                "Axolotl", "Blank Cells", "Cat Facts", "Dog CEO", "Double Trailing", "No Closing Pipe",
                "Old Weather", "Open-Meteo", "OpenWeatherMap", "Trailing Empty",
            ],
        )

    def test_trailing_empty_cells_are_tolerated(self):
        for name in ("Trailing Empty", "Double Trailing"):
            self.assertIn(name, self.by_name)
        self.assertEqual(self.by_name["Trailing Empty"]["cors"], "Yes")
        self.assertEqual(self.by_name["Double Trailing"]["auth"], "OAuth")

    def test_missing_closing_pipe_uses_first_four_cells_and_is_counted_ragged(self):
        row = self.by_name["No Closing Pipe"]
        self.assertEqual((row["auth"], row["https"], row["cors"]), ("apiKey", True, "No"))
        self.assertEqual(self.stats["ragged"], 1)

    def test_promo_and_mcp_tables_are_skipped(self):
        self.assertNotIn("IPstack", self.by_name)
        self.assertNotIn("IPstack MCP", self.by_name)
        self.assertNotIn("Filesystem", self.by_name)

    def test_category_comes_from_nearest_heading(self):
        self.assertEqual(self.by_name["Axolotl"]["category"], "Animals")
        self.assertEqual(self.by_name["Open-Meteo"]["category"], "Weather")

    def test_name_url_description(self):
        a = self.by_name["Axolotl"]
        self.assertEqual(a["url"], "https://theaxolotlapi.netlify.app/")
        self.assertEqual(a["description"], "Collection of axolotl pictures and facts")

    def test_auth_is_normalised(self):
        self.assertEqual(self.by_name["Axolotl"]["auth"], "No")
        self.assertEqual(self.by_name["Cat Facts"]["auth"], "No")  # backticked `No`
        self.assertEqual(self.by_name["OpenWeatherMap"]["auth"], "apiKey")
        self.assertEqual(self.by_name["Old Weather"]["auth"], "OAuth")

    def test_https_is_bool_or_none(self):
        self.assertIs(self.by_name["Axolotl"]["https"], True)
        self.assertIs(self.by_name["Old Weather"]["https"], False)
        self.assertIsNone(self.by_name["Blank Cells"]["https"])

    def test_cors_is_yes_no_or_unknown(self):
        self.assertEqual(self.by_name["Dog CEO"]["cors"], "Yes")
        self.assertEqual(self.by_name["Axolotl"]["cors"], "No")
        self.assertEqual(self.by_name["Cat Facts"]["cors"], "Unknown")
        self.assertEqual(self.by_name["Old Weather"]["cors"], "Unknown")  # "–"
        self.assertEqual(self.by_name["Blank Cells"]["cors"], "Unknown")  # empty

    def test_malformed_row_is_counted_not_parsed(self):
        self.assertEqual(self.stats["malformed"], 1)
        self.assertNotIn("Too Few Cells", self.by_name)

    def test_row_after_table_ends_is_ignored(self):
        self.assertNotIn("Not In A Table", self.by_name)

    def test_stats_report_categories(self):
        self.assertEqual(self.stats["categories"], 2)
        self.assertEqual(self.stats["parsed"], 10)


class SanityCheckTests(unittest.TestCase):
    def test_passes_for_healthy_numbers(self):
        build.check_sanity({"parsed": 2100, "malformed": 2, "categories": 50})

    def test_fails_when_too_few_apis(self):
        with self.assertRaises(SystemExit):
            build.check_sanity({"parsed": 40, "malformed": 0, "categories": 3})

    def test_fails_when_many_rows_malformed(self):
        with self.assertRaises(SystemExit):
            build.check_sanity({"parsed": 2000, "malformed": 100, "categories": 50})


class ApplyHealthTests(unittest.TestCase):
    def setUp(self):
        self.apis = [
            {"name": "A", "url": "https://a.example/", "category": "X"},
            {"name": "B", "url": "https://b.example/", "category": "X"},
            {"name": "C", "url": "https://c.example/", "category": "Y"},
        ]
        self.health = {
            "last_run": "2026-10-22",
            "failing": {
                "https://a.example/": {"failures": 1, "first_failed": "2026-10-22", "error": "dns"},
                "https://b.example/": {"failures": 3, "first_failed": "2026-10-20", "error": "gone"},
                "https://removed.example/": {"failures": 5, "first_failed": "2026-10-01", "error": "dns"},
            },
        }

    def test_dead_threshold_is_three_failed_runs_in_a_row(self):
        self.assertEqual(build.DEAD_AFTER, 3)

    def test_below_threshold_is_failing_and_at_threshold_is_dead(self):
        flagged = {a["name"]: a for a in build.apply_health(self.apis, self.health)}
        self.assertEqual(flagged["A"]["health"], "failing")
        self.assertEqual(flagged["B"]["health"], "dead")

    def test_error_class_and_first_failed_are_carried(self):
        flagged = {a["name"]: a for a in build.apply_health(self.apis, self.health)}
        self.assertEqual((flagged["B"]["health_error"], flagged["B"]["health_since"]), ("gone", "2026-10-20"))

    def test_unflagged_api_gets_no_health_keys(self):
        flagged = {a["name"]: a for a in build.apply_health(self.apis, self.health)}
        self.assertFalse(any(key.startswith("health") for key in flagged["C"]))

    def test_entries_for_urls_not_in_the_list_are_ignored(self):
        flagged = build.apply_health(self.apis, self.health)
        self.assertEqual(len(flagged), 3)

    def test_no_health_data_changes_nothing(self):
        self.assertEqual(build.apply_health(self.apis, None), self.apis)

    def test_input_is_not_mutated(self):
        build.apply_health(self.apis, self.health)
        self.assertFalse(any("health" in a for a in self.apis))


class HealthBuildTests(unittest.TestCase):
    def setUp(self):
        import json
        import tempfile
        from unittest import mock

        self.json = json
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.health_path = self.tmp / "health.json"
        self.out = self.tmp / "apis.json"
        # The fixture is tiny and has one deliberately malformed row, so relax the real-data sanity limits.
        for name, value in (("MIN_APIS", 1), ("MAX_MALFORMED_RATIO", 1.0)):
            patcher = mock.patch.object(build, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.dir.cleanup)

    def run_build(self):
        build.main(["--readme", str(ROOT / "tests" / "fixtures" / "sample.md"), "--out", str(self.out), "--health", str(self.health_path)])
        return self.json.loads(self.out.read_text(encoding="utf-8"))

    def test_flags_and_last_checked_reach_the_output(self):
        self.health_path.write_text(self.json.dumps({
            "last_run": "2026-10-22",
            "failing": {"https://catfact.ninja": {"failures": 3, "first_failed": "2026-10-20", "error": "dns"}},
        }))
        data = self.run_build()
        self.assertEqual(data["health_checked"], "2026-10-22")
        flagged = [a for a in data["apis"] if "health" in a]
        self.assertEqual([(a["name"], a["health"]) for a in flagged], [("Cat Facts", "dead")])

    def test_missing_health_file_means_no_flags(self):
        data = self.run_build()
        self.assertIsNone(data["health_checked"])
        self.assertFalse(any("health" in a for a in data["apis"]))

    def test_damaged_health_file_fails_the_build_loudly(self):
        self.health_path.write_text("{ not json")
        with self.assertRaises(SystemExit) as raised:
            self.run_build()
        self.assertIn("health", str(raised.exception.code).lower())  # a message, not argparse's exit code 2
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
