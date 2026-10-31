"use strict";
(function () {
  var FIELDS = ["material_grade", "dimensions", "tolerance", "quantity", "finish", "certs", "delivery_date", "units"];
  var LABEL = { material_grade: "Material grade", dimensions: "Dimensions", tolerance: "Tolerance", quantity: "Quantity",
    finish: "Finish", certs: "Certifications", delivery_date: "Delivery date", units: "Units" };
  var SHORT = { material_grade: "Grade", dimensions: "Size", tolerance: "Tol.", quantity: "Qty", finish: "Finish",
    certs: "Certs", delivery_date: "Date", units: "Units" };
  var FAMILY = { service_center: "Service center", machine_shop: "Machine shop" };
  var AMBIG = { none: "", units_missing: "Test case: units not written", same_as_last_time: "Test case: refers to a past order",
    attachment_filename: "Test case: spec only in an attachment" };
  var narrow = window.matchMedia("(max-width: 899px)");

  var results = [], ev = null, meta = null, byId = {}, filter = "all", lastId = null;

  function h(tag, props) {
    var el = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      if (k === "class") el.className = props[k];
      else if (k === "text") el.textContent = props[k];
      else el.setAttribute(k, props[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      if (Array.isArray(c)) { c.forEach(function (x) { el.appendChild(typeof x === "string" ? document.createTextNode(x) : x); }); continue; }
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }
  function $(id) { return document.getElementById(id); }
  var money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  var dateFmt = new Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" });
  function pct(x) { var v = x * 100; return (v === 0 ? "0" : v === 100 ? "100" : v.toFixed(1)) + "%"; }
  function num(x) { return Number(x).toLocaleString("en-US", { maximumFractionDigits: 4 }); }
  function labels(list) { return list.map(function (f) { return LABEL[f].toLowerCase(); }).join(", "); }
  function announce(msg) { $("announce").textContent = msg; }

  function derive(r) {
    var miss = r.flags.missing, truth = r.truth_missing;
    var differs = FIELDS.filter(function (f) { return (miss.indexOf(f) >= 0) !== (truth.indexOf(f) >= 0); });
    return { miss: miss, differs: differs, ready: r.flags.ready_to_price };
  }

  /* ---------- scoreboard ---------- */
  function band(w, bad, text) {
    var b = h("div", { class: "band" + (bad ? " bad" : ""), role: "img", "aria-label": text },
      h("div", { class: "grid" }), h("div", { class: "axisline" }), h("div", { class: "range" }), h("div", { class: "dot" }));
    b.style.setProperty("--lo", (w.lo * 100) + "%");
    b.style.setProperty("--hi", (w.hi * 100) + "%");
    b.style.setProperty("--p", (w.p * 100) + "%");
    return b;
  }
  function gauge(name, sub, w, bad) {
    var interval = "95% interval " + pct(w.lo) + " to " + pct(w.hi);
    return h("div", { class: "gauge" },
      h("div", {}, h("div", { class: "name", text: name }), h("div", { class: "sub", text: sub })),
      h("div", { class: "reading" }, w.k + " of " + w.n, h("small", { text: pct(w.p) })),
      h("div", {}, band(w, bad, name + ": " + w.k + " of " + w.n + ", " + interval), h("div", { class: "fine", text: interval })));
  }
  function renderScoreboard() {
    var c = ev.variants.checker, wrong = c.confidently_wrong, held = c.incomplete_rfqs_caught;
    var v = $("verdict");
    v.textContent = "";
    if (wrong.k === 0) {
      v.append("The agent held back ", h("b", { text: held.k + " of " + held.n }), " incomplete requests and priced none of them. Zero misses in " +
        wrong.n + " still leaves room: the true miss rate could be as high as ", h("b", { text: pct(wrong.hi) }), ".");
    } else {
      v.append("The agent let ", h("b", { text: wrong.k + " of " + wrong.n }), " requests through to pricing with a required field missing. The true rate could be between " +
        pct(wrong.lo) + " and " + pct(wrong.hi) + ".");
    }
    var g = $("gauges");
    g.textContent = "";
    g.append(
      gauge("Incomplete requests let through to pricing", "Marked ready to price while a required field was missing. Lower is better.", wrong, wrong.k > 0),
      gauge("Incomplete requests held back", "Requests with at least one missing field that the agent stopped before pricing.", held, false),
      gauge("Missing-spec recall", "Of the fields the customer left out, how many the agent flagged.", c.missing_recall, false),
      gauge("Missing-spec precision", "Of the fields the agent flagged, how many were really missing.", c.missing_precision, false),
      gauge("Field accuracy", "Found-or-missing call correct across " + ev.n_field_decisions + " field checks (" + ev.n_rfqs + " requests, 8 fields each).", c.field_accuracy, false),
      h("div", { class: "axis-row", "aria-hidden": "true" }, h("div", { class: "axis" }, h("span", { text: "0%" }), h("span", { text: "50%" }), h("span", { text: "100%" }))));
    var bs = c.field_accuracy_cluster_bootstrap;
    $("gauge-note").textContent = "Each bar is a 95% Wilson interval: the range of true rates consistent with what was observed. With 30 requests the bars are wide. " +
      "The " + ev.n_field_decisions + " field checks come from only " + ev.n_rfqs + " emails, so they are not independent; resampling whole requests gives " +
      pct(bs.lo) + " to " + pct(bs.hi) + " for field accuracy.";

    // ablation
    var rows = [["naive", "Any value the model returns counts as found"], ["evidence", "Plus: its quote must appear in the email"],
      ["checker", "Plus: no references to past orders, format checks, unit tokens"]];
    var tbody = h("tbody");
    rows.forEach(function (r) {
      var x = ev.variants[r[0]];
      tbody.appendChild(h("tr", {}, h("td", { text: r[1] }),
        h("td", { class: "num", text: x.missing_recall.k + "/" + x.missing_recall.n }),
        h("td", { class: "num", text: x.missing_precision.k + "/" + x.missing_precision.n }),
        h("td", { class: "num", text: x.confidently_wrong.k + " of " + x.confidently_wrong.n })));
    });
    var same = ev.variants.naive.confidently_wrong.k === ev.variants.checker.confidently_wrong.k;
    $("ablation-body").textContent = "";
    $("ablation-body").append(
      h("p", { text: "The model only extracts. A plain-Python checker decides whether a field counts as found, and sets ready_to_price. Each row adds one rule." }),
      h("div", { class: "tablewrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", { text: "Rule for “found”" }), h("th", { class: "num", text: "Recall" }),
          h("th", { class: "num", text: "Precision" }), h("th", { class: "num", text: "Let through" }))), tbody)),
      h("p", { text: same ? "The rules change field-level recall. At the request level the count stays the same on this sample, because every request the model misread also had a second real gap that blocked it anyway." :
        "The rules change both field-level recall and the number of incomplete requests let through." }));

    // failure mode
    var fm = ev.failure_mode;
    $("failure-title").textContent = "Top failure mode: " + fm.title.charAt(0).toLowerCase() + fm.title.slice(1);
    var list = h("ul", { class: "exlist" });
    fm.examples.forEach(function (x) {
      list.appendChild(h("li", {}, h("a", { href: "#/" + x.id, text: x.id }),
        " (" + LABEL[x.field].toLowerCase() + "): the model said “" + x.model_value + "”, quoting “" + x.model_evidence + "”. Checker: " + x.checker_reason + "."));
    });
    $("failure-body").textContent = "";
    $("failure-body").append(h("p", { text: fm.summary }), list, h("p", { text: fm.residual_note }));

    $("meta-line").textContent = "Model " + meta.model + " at temperature " + meta.temperature + ", prompt " + meta.prompt_version +
      ". Retrieval: " + meta.embedding_model + " with " + meta.index + ". Everything is precomputed offline; this page only reads JSON.";
  }

  /* ---------- list ---------- */
  function strip(r, big) {
    var d = derive(r);
    var s = h("span", { class: "strip" + (big ? " big" : ""), role: "img" });
    FIELDS.forEach(function (f) {
      var cls = "cell" + (d.miss.indexOf(f) >= 0 ? " missing" : " found") + (d.differs.indexOf(f) >= 0 ? " differs" : "");
      var cell = h("span", { class: cls, "aria-hidden": "true" });
      s.appendChild(big ? h("span", { class: "labeled" }, cell, h("span", { text: SHORT[f] })) : cell);
    });
    var found = 8 - d.miss.length;
    var t = "Found " + found + " of 8 required fields." + (d.miss.length ? " Flagged missing: " + labels(d.miss) + "." : "") +
      (d.differs.length ? " Disagrees with the hand label on " + labels(d.differs) + "." : "");
    s.setAttribute("aria-label", t);
    return s;
  }
  function rowState(r, d) {
    if (!d.ready) return h("span", { class: "state held", text: "Held back: needs " + labels(d.miss) });
    if (r.price.status === "priced") return h("span", { class: "state priced", text: "Priced " + money.format(r.price.total) + " (illustrative)" });
    return h("span", { class: "state", text: "Ready, but needs a person to price" });
  }
  function whatLine(r) {
    var p = r.flags.present, parts = [];
    if (p.indexOf("material_grade") >= 0) parts.push(r.extraction.material_grade.value);
    if (p.indexOf("dimensions") >= 0) parts.push(r.extraction.dimensions.value);
    return parts.length ? parts.join(", ") : "Core spec not stated";
  }
  function renderList() {
    var ol = $("rows");
    ol.textContent = "";
    results.forEach(function (r) {
      var d = derive(r);
      var a = h("a", { class: "row", href: "#/" + r.id, "data-id": r.id },
        h("span", { class: "top" }, h("span", { class: "id", text: r.id }), h("span", { class: "fam", text: FAMILY[r.family] })),
        h("span", { class: "what", text: whatLine(r) }),
        strip(r, false),
        h("span", {}, rowState(r, d), AMBIG[r.ambiguity] ? h("span", { class: "tag", text: " " + AMBIG[r.ambiguity] }) : null,
          d.differs.length ? h("span", { class: "tag", text: " Differs from the hand label" }) : null));
      ol.appendChild(h("li", { "data-id": r.id }, a));
    });
    var defs = [
      ["all", "All requests", function () { return true; }],
      ["held", "Held back", function (r) { return !r.flags.ready_to_price; }],
      ["priced", "Priced", function (r) { return r.flags.ready_to_price; }],
      ["differs", "Differs from label", function (r) { return derive(r).differs.length > 0; }],
      ["ambig", "Test cases", function (r) { return r.ambiguity !== "none"; }]];
    var f = $("filters");
    f.textContent = "";
    defs.forEach(function (d) {
      var n = results.filter(d[2]).length;
      var b = h("button", { type: "button", "aria-pressed": String(filter === d[0]), text: d[1] + " (" + n + ")" });
      b.addEventListener("click", function () {
        filter = d[0];
        Array.prototype.forEach.call(f.children, function (x) { x.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        results.forEach(function (r) { ol.querySelector('li[data-id="' + r.id + '"]').hidden = !d[2](r); });
        announce(n + " requests shown.");
      });
      f.appendChild(b);
    });
  }

  /* ---------- detail ---------- */
  function section(title, id) { return h("section", { class: "sec", "aria-labelledby": id }, h("h3", { id: id, text: title })); }

  function renderDetail(r) {
    var d = derive(r), root = $("detail-body");
    root.textContent = "";
    var back = h("button", { class: "back", type: "button", text: "Back to the list" });
    back.addEventListener("click", function () { location.hash = "#/"; });

    var heading = h("h2", { id: "detail-title", text: r.id });
    var decision = h("div", { class: "decision" + (d.ready ? "" : " held") });
    decision.appendChild(h("p", { class: "headline", text: d.ready ? "Ready to price." : "Held back: ask the customer first." }));
    decision.appendChild(h("p", { text: d.ready ? "All 8 required fields were found in the email." : "Missing: " + labels(d.miss) + "." }));
    var truth = r.truth_missing;
    decision.appendChild(h("p", { text: "Hand label: " + (truth.length ? "missing " + labels(truth) : "nothing missing") + ". " +
      (d.differs.length ? "The agent disagrees on " + labels(d.differs) + "." : "The agent agrees.") }));

    var email = section("Email", "h-email");
    email.appendChild(h("pre", { class: "email", text: "Subject: " + r.subject + "\n\n" + r.body }));
    email.appendChild(h("p", { class: "attach" }, r.attachments.length ? ["Attachments (names only, the agent cannot open them): ",
      h("code", { text: r.attachments.join(", ") })] : "No attachments."));

    var reads = section("What the agent read", "h-reads");
    reads.appendChild(h("div", { class: "strip-wrap" }, strip(r, true)));
    var table = h("div", { class: "reads", role: "list" });
    FIELDS.forEach(function (f) {
      var x = r.extraction[f], miss = d.miss.indexOf(f) >= 0, differs = d.differs.indexOf(f) >= 0;
      var s = h("div", { class: "s " + (miss ? "no" : "ok") }, miss ? "Missing" : "Found");
      if (miss && r.flags.reasons[f]) s.appendChild(h("span", { class: "why", text: r.flags.reasons[f] }));
      if (differs) s.appendChild(h("span", { class: "diff", text: "Hand label says " + (miss ? "found" : "missing") }));
      table.appendChild(h("div", { class: "read", role: "listitem" },
        h("div", { class: "f", text: LABEL[f] }),
        h("div", { class: "v", text: x.value ? "“" + x.value + "”" : "Not stated" }),
        h("div", { class: "q", text: x.evidence ? "Quote: " + x.evidence : "" }), s));
    });
    reads.appendChild(table);

    var draft = section("Clarification draft", "h-draft");
    if (r.draft.text) {
      draft.appendChild(h("pre", { class: "draft", text: r.draft.text }));
      var copy = h("button", { class: "btn", type: "button", text: "Copy draft" });
      copy.addEventListener("click", function () { copyText(r.draft.text, copy); });
      draft.appendChild(copy);
      draft.appendChild(h("p", { class: "fine", text: r.draft.covers_all_missing ? "A keyword check confirms the draft asks about every missing field." : "A keyword check could not confirm the draft covers every missing field. Read it before sending." }));
    } else {
      draft.appendChild(h("p", { text: "No draft needed. Every required field was found." }));
    }

    var price = section("Price trace", "h-price");
    price.appendChild(h("p", { class: "fine", text: r.price.note }));
    if (r.price.steps.length) {
      var tb = h("tbody");
      r.price.steps.forEach(function (s) {
        var money_ = /\(\$\)/.test(s.step);
        tb.appendChild(h("tr", {}, h("td", { text: s.step }), h("td", { text: s.detail }),
          h("td", { class: "num", text: money_ ? money.format(s.value) : num(s.value) })));
      });
      price.appendChild(h("div", { class: "tablewrap trace" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", { text: "Step" }), h("th", { text: "How" }), h("th", { class: "num", text: "Value" }))), tb)));
      price.appendChild(h("p", { class: "total", text: money.format(r.price.unit_price) + " each, " + money.format(r.price.total) + " total (illustrative)" }));
    }

    var jobs = section("Similar past jobs", "h-jobs");
    jobs.appendChild(h("p", { class: "fine", text: "Found by sentence embeddings and FAISS over 80 invented jobs of the same product family." }));
    var ul = h("ul", { class: "jobs" });
    r.similar_jobs.forEach(function (j) {
      ul.appendChild(h("li", {}, h("div", { class: "jh" }, h("span", { text: j.job_id + " (match " + j.score.toFixed(2) + ")" }),
        h("span", { text: money.format(j.total_price) + ", " + j.lead_days + " days" })), h("div", { class: "js", text: j.summary })));
    });
    jobs.appendChild(ul);

    root.append(back, heading,
      h("p", { class: "meta", text: FAMILY[r.family] + ", received " + dateFmt.format(new Date(r.received + "T00:00:00Z")) + "." + (AMBIG[r.ambiguity] ? " " + AMBIG[r.ambiguity] + "." : "") }),
      decision, email, reads, draft, price, jobs);
  }

  function copyText(text, btn) {
    function done(ok) {
      btn.textContent = ok ? "Draft copied" : "Couldn't copy. Select the text instead.";
      announce(btn.textContent);
      setTimeout(function () { btn.textContent = "Copy draft"; }, 2200);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
    else done(false);
  }

  /* ---------- routing ---------- */
  function route() {
    var m = /^#\/(RFQ-\d{3})$/.exec(location.hash);
    var ws = $("rfqs");
    var rows = document.querySelectorAll(".row");
    Array.prototype.forEach.call(rows, function (a) { a.removeAttribute("aria-current"); });
    if (m && byId[m[1]]) {
      var r = byId[m[1]];
      lastId = r.id;
      renderDetail(r);
      $("placeholder").hidden = true;
      $("detail-body").hidden = false;
      var link = document.querySelector('.row[data-id="' + r.id + '"]');
      if (link) link.setAttribute("aria-current", "true");
      ws.setAttribute("data-view", "detail");
      announce("Showing " + r.id);
      if (narrow.matches) { ws.scrollIntoView(); $("detail").focus({ preventScroll: true }); }
      else $("detail").scrollTop = 0;
    } else {
      ws.setAttribute("data-view", "list");
      $("placeholder").hidden = false;
      $("detail-body").hidden = true;
      if (narrow.matches && lastId) {
        var back = document.querySelector('.row[data-id="' + lastId + '"]');
        if (back) { back.scrollIntoView({ block: "center" }); back.focus({ preventScroll: true }); }
      }
    }
  }

  /* ---------- boot ---------- */
  function load(url) { return fetch(url).then(function (r) { if (!r.ok) throw new Error(url); return r.json(); }); }
  Promise.all([load("data/results.json"), load("data/eval.json"), load("data/meta.json")]).then(function (all) {
    results = all[0]; ev = all[1]; meta = all[2];
    results.forEach(function (r) { byId[r.id] = r; });
    renderScoreboard();
    renderList();
    window.addEventListener("hashchange", route);
    route();
  }).catch(function () {
    $("verdict").textContent = "Couldn't load the results. Reload the page, or read the JSON in data/outputs/ in the repo.";
  });
})();
