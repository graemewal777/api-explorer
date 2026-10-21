(function () {
  var DEFAULT_STATE = { q: "", category: "", noKey: false, https: false, cors: false };

  function parseHash(hash) {
    var params = new URLSearchParams(String(hash || "").replace(/^#/, ""));
    return {
      q: params.get("q") || "",
      category: params.get("category") || "",
      noKey: params.get("nokey") === "1",
      https: params.get("https") === "1",
      cors: params.get("cors") === "1",
    };
  }

  function toHash(state) {
    var params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.category) params.set("category", state.category);
    if (state.noKey) params.set("nokey", "1");
    if (state.https) params.set("https", "1");
    if (state.cors) params.set("cors", "1");
    var text = params.toString();
    return text ? "#" + text : "";
  }

  function filterApis(apis, state) {
    var terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    return apis.filter(function (api) {
      if (state.category && api.category !== state.category) return false;
      if (state.noKey && api.auth !== "No") return false;
      if (state.https && api.https !== true) return false;
      if (state.cors && api.cors !== "Yes") return false;
      if (!terms.length) return true;
      var haystack = (api.name + " " + api.description + " " + api.category).toLowerCase();
      return terms.every(function (term) { return haystack.indexOf(term) !== -1; });
    });
  }

  function categoryCounts(apis) {
    var counts = {};
    apis.forEach(function (api) { counts[api.category] = (counts[api.category] || 0) + 1; });
    return Object.keys(counts).sort().map(function (name) { return { name: name, count: counts[name] }; });
  }

  // The data comes from a list anyone can edit upstream, so only ever link to http(s).
  function safeUrl(url) {
    try {
      var parsed = new URL(url);
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null;
    } catch (error) {
      return null;
    }
  }

  var api = {
    DEFAULT_STATE: DEFAULT_STATE,
    parseHash: parseHash,
    toHash: toHash,
    filterApis: filterApis,
    categoryCounts: categoryCounts,
    safeUrl: safeUrl,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    window.ApiFilter = api;
  }
})();
