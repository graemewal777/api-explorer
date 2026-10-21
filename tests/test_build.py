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


if __name__ == "__main__":
    unittest.main()
