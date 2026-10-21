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
