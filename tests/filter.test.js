const test = require("node:test");
const assert = require("node:assert");
const F = require("../site/filter.js");

const APIS = [
  { name: "Axolotl", url: "https://a.example", description: "Pictures and facts", category: "Animals", auth: "No", https: true, cors: "No" },
  { name: "Cat Facts", url: "https://b.example", description: "Daily cat facts", category: "Animals", auth: "No", https: true, cors: "Unknown" },
  { name: "Open-Meteo", url: "https://c.example", description: "Weather forecast", category: "Weather", auth: "No", https: true, cors: "Yes" },
  { name: "OpenWeatherMap", url: "https://d.example", description: "Weather data", category: "Weather", auth: "apiKey", https: true, cors: "Unknown" },
  { name: "Old Weather", url: "http://e.example", description: "Plain HTTP weather", category: "Weather", auth: "OAuth", https: false, cors: "Unknown" },
  { name: "Blank", url: "https://f.example", description: "No https info", category: "Misc", auth: "No", https: null, cors: "Unknown" },
];

const names = (list) => list.map((a) => a.name);
const state = (overrides) => ({ ...F.DEFAULT_STATE, ...overrides });

test("no filters returns everything in original order", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({}))), names(APIS));
});

test("search matches name, description and category, case-insensitively", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ q: "CAT" }))), ["Cat Facts"]);
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ q: "forecast" }))), ["Open-Meteo"]);
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ q: "animals" }))), ["Axolotl", "Cat Facts"]);
});

test("every search word must match", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ q: "weather data" }))), ["OpenWeatherMap"]);
  assert.deepStrictEqual(F.filterApis(APIS, state({ q: "weather cat" })), []);
});

test("category filter is exact", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ category: "Weather" }))), ["Open-Meteo", "OpenWeatherMap", "Old Weather"]);
});

test("no-key only keeps auth 'No'", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ noKey: true, category: "Weather" }))), ["Open-Meteo"]);
});

test("https only drops http and unknown", () => {
  const result = names(F.filterApis(APIS, state({ https: true })));
  assert.ok(!result.includes("Old Weather"));
  assert.ok(!result.includes("Blank"));
});

test("browser-friendly keeps only CORS 'Yes'", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ cors: true }))), ["Open-Meteo"]);
});

test("filters combine", () => {
  assert.deepStrictEqual(names(F.filterApis(APIS, state({ q: "weather", noKey: true, https: true, cors: true }))), ["Open-Meteo"]);
});

test("hash round-trips and omits defaults", () => {
  assert.strictEqual(F.toHash(F.DEFAULT_STATE), "");
  const s = state({ q: "weather map", category: "Weather", noKey: true, https: true, cors: true });
  assert.deepStrictEqual(F.parseHash(F.toHash(s)), s);
});

test("parseHash tolerates junk and empty input", () => {
  assert.deepStrictEqual(F.parseHash(""), F.DEFAULT_STATE);
  assert.deepStrictEqual(F.parseHash("#nonsense=1&nokey=maybe"), F.DEFAULT_STATE);
});

test("categoryCounts is sorted with counts", () => {
  assert.deepStrictEqual(F.categoryCounts(APIS), [
    { name: "Animals", count: 2 },
    { name: "Misc", count: 1 },
    { name: "Weather", count: 3 },
  ]);
});

test("safeUrl allows http(s) and rejects script and data URLs", () => {
  assert.strictEqual(F.safeUrl("https://example.com/x"), "https://example.com/x");
  assert.strictEqual(F.safeUrl("http://example.com/"), "http://example.com/");
  assert.strictEqual(F.safeUrl("javascript:alert(1)"), null);
  assert.strictEqual(F.safeUrl("data:text/html,<script>alert(1)</script>"), null);
  assert.strictEqual(F.safeUrl("not a url"), null);
});

const withHealth = (api, health, error = "dns", since = "2026-10-20") => ({ ...api, health, health_error: error, health_since: since });

test("hideDead is off by default", () => {
  assert.strictEqual(F.DEFAULT_STATE.hideDead, false);
});

test("hideDead hides dead links only, not ones that merely failed the latest check", () => {
  const apis = [
    withHealth(APIS[0], "dead"),
    withHealth(APIS[1], "failing"),
    APIS[2],
  ];
  assert.deepStrictEqual(names(F.filterApis(apis, state({ hideDead: true }))), ["Cat Facts", "Open-Meteo"]);
  assert.deepStrictEqual(names(F.filterApis(apis, state({}))), ["Axolotl", "Cat Facts", "Open-Meteo"]);
});

test("hideDead round-trips through the URL hash as hidedead=1", () => {
  const s = state({ hideDead: true, noKey: true });
  assert.ok(F.toHash(s).includes("hidedead=1"));
  assert.deepStrictEqual(F.parseHash(F.toHash(s)), s);
});

test("healthBadge is null for a link with no flag", () => {
  assert.strictEqual(F.healthBadge(APIS[0]), null);
});

test("healthBadge wording follows the failure class for dead links", () => {
  const expected = {
    dns: "May be gone",
    gone: "May be gone",
    refused: "May be gone",
    tls: "Certificate problem",
    timeout: "Not responding",
    error: "Not responding",
    network: "Not responding",
  };
  for (const [error, text] of Object.entries(expected)) {
    const badge = F.healthBadge(withHealth(APIS[0], "dead", error));
    assert.strictEqual(badge.text, text, error);
    assert.strictEqual(badge.kind, "bad", error);
  }
});

test("healthBadge for a link that only failed the latest check is a quiet warning", () => {
  const badge = F.healthBadge(withHealth(APIS[0], "failing", "timeout", "2026-10-22"));
  assert.strictEqual(badge.text, "Failed latest check");
  assert.strictEqual(badge.kind, "warn");
});

test("healthBadge tooltip says since when and why", () => {
  const dead = F.healthBadge(withHealth(APIS[0], "dead", "dns", "2026-10-20"));
  assert.match(dead.title, /2026-10-20/);
  assert.match(dead.title, /domain/i);
  const gone = F.healthBadge(withHealth(APIS[0], "dead", "gone", "2026-10-20"));
  assert.match(gone.title, /404|410/);
});

test("healthBadge copes with an unknown failure class", () => {
  const badge = F.healthBadge(withHealth(APIS[0], "dead", "something-new"));
  assert.strictEqual(badge.text, "Not responding");
});
