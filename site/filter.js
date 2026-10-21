(function () {
  var DEFAULT_STATE = { q: "", category: "", noKey: false, https: false, cors: false, hideDead: false };

  function parseHash(hash) {
    var params = new URLSearchParams(String(hash || "").replace(/^#/, ""));
    return {
      q: params.get("q") || "",
      category: params.get("category") || "",
      noKey: params.get("nokey") === "1",
      https: params.get("https") === "1",
      cors: params.get("cors") === "1",
      hideDead: params.get("hidedead") === "1",
    };
  }

  function toHash(state) {
    var params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.category) params.set("category", state.category);
    if (state.noKey) params.set("nokey", "1");
    if (state.https) params.set("https", "1");
    if (state.cors) params.set("cors", "1");
    if (state.hideDead) params.set("hidedead", "1");
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
      if (state.hideDead && api.health === "dead") return false;
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

  var HEALTH_DETAIL = {
    dns: "the domain no longer resolves",
    gone: "the page returns 404 or 410",
    refused: "connections are refused",
    tls: "its security certificate is not valid",
    timeout: "it did not respond in time",
    error: "the server returns an error",
    network: "the connection fails",
  };
  var DEAD_TEXT = { dns: "May be gone", gone: "May be gone", refused: "May be gone", tls: "Certificate problem" };

  // Wording follows what actually failed. A link that has only failed the latest check is a quiet warning.
  function healthBadge(api) {
    if (api.health !== "dead" && api.health !== "failing") return null;
    var detail = HEALTH_DETAIL[api.health_error] || "it could not be reached";
    if (api.health === "dead") {
      return {
        text: DEAD_TEXT[api.health_error] || "Not responding",
        kind: "bad",
        title: "Failing checks since " + api.health_since + ": " + detail + ".",
      };
    }
    return {
      text: "Failed latest check",
      kind: "warn",
      title: "Failed the latest check (" + detail + "). Counted as possibly dead after three failed checks in a row.",
    };
  }

  var api = {
    DEFAULT_STATE: DEFAULT_STATE,
    parseHash: parseHash,
    toHash: toHash,
    filterApis: filterApis,
    categoryCounts: categoryCounts,
    safeUrl: safeUrl,
    healthBadge: healthBadge,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    window.ApiFilter = api;
  }
})();
