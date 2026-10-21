(function () {
  var F = window.ApiFilter;
  var PAGE_SIZE = 100;

  var el = {
    q: document.getElementById("q"),
    category: document.getElementById("category"),
    noKey: document.getElementById("nokey"),
    https: document.getElementById("https"),
    cors: document.getElementById("cors"),
    hideDead: document.getElementById("hidedead"),
    reset: document.getElementById("reset"),
    status: document.getElementById("status"),
    results: document.getElementById("results"),
    more: document.getElementById("more"),
    footer: document.getElementById("footer"),
  };

  var apis = [];
  var matches = [];
  var shown = 0;

  function readControls() {
    return {
      q: el.q.value.trim(),
      category: el.category.value,
      noKey: el.noKey.checked,
      https: el.https.checked,
      cors: el.cors.checked,
      hideDead: el.hideDead.checked,
    };
  }

  function writeControls(state) {
    el.q.value = state.q;
    el.category.value = state.category;
    el.noKey.checked = state.noKey;
    el.https.checked = state.https;
    el.cors.checked = state.cors;
    el.hideDead.checked = state.hideDead;
  }

  function badge(text, kind) {
    var span = document.createElement("span");
    span.className = "badge" + (kind ? " " + kind : "");
    span.textContent = text;
    return span;
  }

  function card(api) {
    var li = document.createElement("li");

    var name = document.createElement("div");
    name.className = "name";
    var href = F.safeUrl(api.url);
    if (href) {
      var link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = api.name;
      name.appendChild(link);
    } else {
      name.textContent = api.name;
    }

    var desc = document.createElement("p");
    desc.className = "desc";
    desc.textContent = api.description;

    var badges = document.createElement("div");
    badges.className = "badges";
    var health = F.healthBadge(api);
    if (health) {
      var healthEl = badge(health.text, health.kind);
      healthEl.title = health.title;
      badges.appendChild(healthEl);
    }
    badges.appendChild(badge(api.category));
    badges.appendChild(api.auth === "No" ? badge("No key", "good") : badge("Key: " + api.auth, "warn"));
    if (api.https === true) badges.appendChild(badge("HTTPS", "good"));
    else if (api.https === false) badges.appendChild(badge("HTTP only", "warn"));
    if (api.cors === "Yes") badges.appendChild(badge("CORS", "good"));

    li.appendChild(name);
    li.appendChild(desc);
    li.appendChild(badges);
    return li;
  }

  function renderMore() {
    var end = Math.min(shown + PAGE_SIZE, matches.length);
    var fragment = document.createDocumentFragment();
    for (var i = shown; i < end; i++) fragment.appendChild(card(matches[i]));
    el.results.appendChild(fragment);
    shown = end;
    el.more.hidden = shown >= matches.length;
    el.status.textContent = matches.length === 0
      ? "No APIs match. Try fewer filters."
      : "Showing " + shown + " of " + matches.length + " APIs";
  }

  function update(fromHash) {
    var state = fromHash ? F.parseHash(location.hash) : readControls();
    if (fromHash) writeControls(state);
    else history.replaceState(null, "", location.pathname + location.search + F.toHash(state));

    matches = F.filterApis(apis, state);
    shown = 0;
    el.results.textContent = "";
    renderMore();
  }

  function init(data) {
    apis = data.apis;

    F.categoryCounts(apis).forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry.name;
      option.textContent = entry.name + " (" + entry.count + ")";
      el.category.appendChild(option);
    });

    if (data.source_commit) {
      var short = data.source_commit.slice(0, 7);
      el.footer.append("Built from public-apis at commit ");
      var link = document.createElement("a");
      link.href = "https://github.com/public-apis/public-apis/commit/" + data.source_commit;
      link.textContent = short;
      el.footer.appendChild(link);
      el.footer.append(". " + data.count + " APIs.");
    }

    if (data.health_checked) {
      var dead = 0;
      apis.forEach(function (api) { if (api.health === "dead") dead++; });
      el.footer.append(" Links last checked " + data.health_checked + (dead ? ", " + dead + " possibly dead." : "."));
    }

    ["input", "change"].forEach(function (type) {
      el.q.addEventListener(type, function () { update(false); });
    });
    [el.category, el.noKey, el.https, el.cors, el.hideDead].forEach(function (control) {
      control.addEventListener("change", function () { update(false); });
    });
    el.reset.addEventListener("click", function () {
      writeControls(F.DEFAULT_STATE);
      update(false);
    });
    el.more.addEventListener("click", renderMore);
    window.addEventListener("hashchange", function () { update(true); });

    update(true);
  }

  fetch("apis.json")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(init)
    .catch(function () {
      el.status.textContent = "Couldn't load apis.json. Run python3 scripts/build.py first.";
    });
})();
