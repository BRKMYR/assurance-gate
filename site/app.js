/* Assurance Gate dashboard. Vanilla ES2020, no dependencies, no build step. */
(function () {
  "use strict";

  var DEV = new URLSearchParams(location.search).has("dev");
  var DATA_URL = DEV ? "dev/sample_data.json" : "data.json";
  var DATA_B_URL = DEV ? "dev/sample_data_b.json" : "data_b.json";

  var S = {};
  var DATA = null;
  var DATA_B = null;
  var B_STATE = "idle";
  var TRACK = "a";

  /* strings -------------------------------------------------------------- */

  function t(key, vars) {
    var s = Object.prototype.hasOwnProperty.call(S, key) ? S[key] : "";
    if (!s) s = "[" + key + "]";
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        s = s.split("{" + k + "}").join(String(vars[k]));
      });
    }
    return s;
  }

  function has(key) {
    return Object.prototype.hasOwnProperty.call(S, key) && S[key] !== "";
  }

  /* dom ------------------------------------------------------------------ */

  function h(tag, props) {
    var n = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "class") n.className = v;
        else if (k === "text") n.textContent = v;
        else if (k === "onclick") n.addEventListener("click", v);
        else if (k === "oninput") n.addEventListener("input", v);
        else n.setAttribute(k, v);
      });
    }
    for (var i = 2; i < arguments.length; i++) add(n, arguments[i]);
    return n;
  }

  function add(parent, kid) {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) {
      kid.forEach(function (k) { add(parent, k); });
      return;
    }
    parent.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  /* formatting ----------------------------------------------------------- */

  function num(v, digits) {
    if (v === null || v === undefined) return t("value.none");
    return Number(v).toFixed(digits === undefined ? 4 : digits);
  }

  function pct(v) {
    if (v === null || v === undefined) return t("value.none");
    return Number(v).toFixed(4);
  }

  function day(iso) {
    if (!iso) return t("value.none");
    return String(iso).slice(0, 10);
  }

  function statusEl(status) {
    return h("span", { class: "st st-" + status, text: t("status." + status) });
  }

  function go(hash) {
    location.hash = hash;
  }

  /* data accessors ------------------------------------------------------- */

  function activeData() {
    return TRACK === "b" ? DATA_B : DATA;
  }

  function suite() {
    var d = activeData();
    return d && d.suites && d.suites.length ? d.suites[0] : null;
  }

  function candidate() {
    var s = suite();
    if (!s || !s.candidates || !s.candidates.length) return null;
    for (var i = 0; i < s.candidates.length; i++) {
      if (!s.candidates[i].excluded) return s.candidates[i];
    }
    return s.candidates[0];
  }

  function gateById(id) {
    var c = candidate();
    if (!c) return null;
    for (var i = 0; i < c.gates.length; i++) {
      if (c.gates[i].gate_id === id) return c.gates[i];
    }
    return null;
  }

  function shortName(id) {
    return has("gate.short." + id) ? t("gate.short." + id) : id;
  }

  function isDemo() {
    var s = suite();
    return !!s && s.preregistered === false;
  }

  /* shared blocks -------------------------------------------------------- */

  function ribbonAndBanner() {
    var out = [];
    if (isDemo()) out.push(h("p", { class: "ribbon", text: t("ribbon.demo") }));
    out.push(h("p", { class: "banner", text: t("banner") }));
    return out;
  }

  function headlineText(c) {
    var v = c.verdict;
    var k = v.failing_gates.length;
    var n = v.n_gates || c.gates.length;
    var names = v.failing_gates.map(shortName).join(", ");
    if (k === 0) {
      return t("decision.headline_pass", { candidate: v.candidate, n: n });
    }
    return t("decision.headline", {
      candidate: v.candidate, verdict: v.verdict, k: k, n: n, names: names
    });
  }

  function ownerP(key) {
    return h("p", { class: "owner", text: t(key) });
  }

  /* page: decision ------------------------------------------------------- */

  function pageDecision() {
    var frag = document.createDocumentFragment();
    var s = suite();
    var c = candidate();
    add(frag, ribbonAndBanner());

    if (!c) {
      add(frag, h("p", { text: t("evidence.empty_b") }));
      return frag;
    }

    add(frag, h("h1", { class: "headline", text: headlineText(c) }));

    var first = c.verdict.failing_gates[0];
    add(frag, h("button", {
      class: "btn-main",
      text: t("decision.see_why"),
      onclick: function () {
        go(first ? "/gates?gate=" + encodeURIComponent(first) : "/gates");
      }
    }));

    add(frag, ownerP("owner.problem"));
    add(frag, ownerP("owner.score_vs_decision"));

    add(frag, h("h2", { text: t("decision.timing_title") }));
    add(frag, h("div", { class: "card" }, h("dl", {},
      h("dt", { text: t("decision.gate_hash") }),
      h("dd", { class: "num", text: (s.gate_file_sha256 || "").slice(0, 16) }),
      h("dt", { text: t("decision.gate_published") }),
      h("dd", { class: "num", text: s.gate_published_at && s.gate_published_at.github_release
        ? day(s.gate_published_at.github_release) : t("value.none") }),
      h("dt", { text: t("decision.first_run") }),
      h("dd", { class: "num", text: day(s.first_run_at) })
    )));
    if (!s.gate_published_at || !s.gate_published_at.github_release) {
      add(frag, h("p", { class: "note warn", text: t("decision.not_preregistered") }));
    }

    var waived = c.gates.filter(function (g) { return g.waiver; });
    if (waived.length) {
      add(frag, h("h2", { text: t("decision.waivers_title") }));
      add(frag, h("ul", { class: "stack" }, waived.map(function (g) {
        return h("li", { class: "note warn" },
          h("strong", { text: shortName(g.gate_id) }), " ",
          h("span", { text: g.waiver.risk_accepted }), " ",
          h("span", { class: "small", text: t("decision.waiver_meta", {
            signer: g.waiver.signer, expires: day(g.waiver.expires_at)
          }) }),
          g.waiver_note ? h("span", { class: "st st-fail", text: " " + t("waiver." + g.waiver_note.replace(/\s+/g, "_")) }) : null
        );
      })));
    }

    if (s.deviations && s.deviations.length) {
      add(frag, h("h2", { text: t("decision.deviations_title") }));
      add(frag, h("ul", { class: "stack" }, s.deviations.map(function (d) {
        return h("li", { class: "note bad" },
          h("strong", { text: shortName(d.gate_id) }), " ",
          h("span", { text: d.field + " " }),
          h("span", { class: "struck num", text: String(d.frozen_value) }), " ",
          h("span", { class: "num", text: String(d.new_value) }), " ",
          h("span", { text: d.reason }), " ",
          h("span", { class: "small", text: t("decision.deviation_meta", {
            signer: d.signer, changed: day(d.changed_at)
          }) })
        );
      })));
    }

    add(frag, h("h2", { text: t("decision.credibility_title") }));
    add(frag, h("ul", {}, (s.credibility || []).map(function (key) {
      return h("li", { text: t(key) });
    })));

    add(frag, h("h2", { text: t("decision.independence_title") }));
    add(frag, h("ul", {}, (s.independence || []).map(function (key) {
      return h("li", { text: t(key) });
    })));

    add(frag, h("h2", { text: t("decision.tracks_title") }));
    add(frag, trackTabs());
    return frag;
  }

  function trackTabs() {
    var wrapEl = h("div", { class: "toolbar", role: "group", "aria-label": "Tracks" });
    add(wrapEl, h("button", {
      class: "chip", "aria-pressed": TRACK === "a" ? "true" : "false",
      text: t("track.a"), onclick: function () { setTrack("a"); }
    }));
    add(wrapEl, h("button", {
      class: "chip", "aria-pressed": TRACK === "b" ? "true" : "false",
      text: t("track.b"), onclick: function () { setTrack("b"); }
    }));
    var box = h("div", {});
    add(box, wrapEl);
    if (TRACK === "b" && B_STATE === "missing") {
      add(box, h("p", { class: "note", text: t("evidence.empty_b") }));
    }
    if (TRACK === "b" && B_STATE === "loading") {
      add(box, h("p", { class: "small", text: t("app.loading") }));
    }
    return box;
  }

  function setTrack(track) {
    if (track === "a") {
      TRACK = "a";
      render();
      return;
    }
    TRACK = "b";
    if (B_STATE === "ok" || B_STATE === "missing") { render(); return; }
    B_STATE = "loading";
    render();
    fetch(DATA_B_URL).then(function (r) {
      if (!r.ok) throw new Error("missing");
      return r.json();
    }).then(function (j) {
      DATA_B = j;
      B_STATE = "ok";
      render();
    }).catch(function () {
      B_STATE = "missing";
      render();
    });
  }

  /* page: gates ---------------------------------------------------------- */

  function pageGates(params) {
    var frag = document.createDocumentFragment();
    var c = candidate();
    if (!c) { add(frag, h("p", { text: t("evidence.empty_b") })); return frag; }
    var focus = params.get("gate");

    add(frag, h("h1", { text: t("gates.title") }));
    add(frag, h("p", { class: "lede", text: t("gates.lede") }));

    var head = [
      [t("gates.col.gate"), ""], [t("gates.col.class"), ""], [t("gates.col.n"), "n"],
      [t("gates.col.unscorable"), "n"], [t("gates.col.point"), "n"], [t("gates.col.bound"), "n"],
      [t("gates.col.threshold"), "n"], [t("gates.col.margin"), "n"], [t("gates.col.status"), ""]
    ];
    var thead = h("tr", {}, head.map(function (col) {
      return h("th", { class: col[1], scope: "col", text: col[0] });
    }));

    var body = h("tbody", {}, c.gates.map(function (g) {
      var tr = h("tr", { id: "gate-" + g.gate_id, class: focus === g.gate_id ? "focus" : "" },
        h("th", { scope: "row" }, h("button", {
          class: "row-btn",
          text: shortName(g.gate_id),
          onclick: function () { go("/evidence?gate=" + encodeURIComponent(g.gate_id)); }
        })),
        h("td", { text: t("class." + g["class"]) }),
        h("td", { class: "n", text: String(g.n) }),
        h("td", { class: "n", text: String(g.n_unscorable) }),
        h("td", { class: "n", text: pct(g.point_estimate) }),
        h("td", { class: "n", text: pct(g.bound) }),
        h("td", { class: "n" }, g.deviation
          ? [h("span", { class: "struck", text: String(g.deviation.frozen_value) }), " ",
             h("span", { text: num(g.threshold, 2) })]
          : num(g.threshold, 2)),
        h("td", { class: "n", text: g.margin === null ? t("value.none") : num(g.margin) }),
        h("td", {}, statusEl(g.status),
          g.reason ? h("span", { class: "small", text: " " + t("reason." + g.reason) }) : null,
          g.frozen_status && g.frozen_status !== g.status
            ? h("span", { class: "small", text: " " + t("gates.frozen_status", { status: t("status." + g.frozen_status) }) })
            : null)
      );
      return tr;
    }));

    add(frag, h("div", { class: "scroll" },
      h("table", {}, h("caption", { text: t("gates.caption") }), h("thead", {}, thead), body)));

    add(frag, h("h2", { text: t("gates.rationale_title") }));
    add(frag, c.gates.map(function (g) {
      var key = "rationale." + g.gate_id;
      var src = "gate.source." + g.gate_id;
      return h("details", { open: focus === g.gate_id ? "open" : false, id: "rationale-" + g.gate_id },
        h("summary", { text: shortName(g.gate_id) }),
        h("p", { class: has(key) ? "" : "owner", text: has(key) ? t(key) : t("gates.rationale_missing") }),
        h("p", { class: "small", text: t("gates.source_label") + " " + (has(src) ? t(src) : t("value.none")) })
      );
    }));

    var w = c.worked_example;
    if (w) {
      add(frag, h("h2", { text: t("gates.worked_example_title") }));
      add(frag, h("div", { class: "example" },
        h("p", { text: t("gates.worked_example", {
          gate: shortName(w.gate_id), n: w.n, n_fail: w.n_fail,
          point: pct(w.point_estimate), bound: pct(w.bound), threshold: num(w.threshold, 2)
        }) }),
        h("p", { class: "small", text: w.live ? t("gates.worked_example_live") : t("gates.worked_example_fixed") })
      ));
    }

    if (c.regression) add(frag, regressionBlock(c.regression));

    if (focus) {
      window.setTimeout(function () {
        var row = document.getElementById("gate-" + focus);
        if (row) row.scrollIntoView({ block: "center" });
      }, 0);
    }
    return frag;
  }

  function regressionBlock(r) {
    var box = document.createDocumentFragment();
    add(box, h("h2", { text: t("gates.regression_title") }));
    add(box, h("p", { text: t("gates.regression_summary", {
      candidate: r.candidate, baseline: r.baseline, n: r.n_pairs,
      tier: r.n_tier_worse, ttc: r.n_ttc_drop
    }) }));

    var flagged = r.pairs.filter(function (p) { return p.tier_worse || p.ttc_drop; });
    var rest = r.pairs.filter(function (p) { return !(p.tier_worse || p.ttc_drop); });
    add(box, pairTable(flagged, t("gates.pairs_flagged")));
    add(box, h("details", {},
      h("summary", { text: t("gates.pairs_all", { n: rest.length }) }),
      pairTable(rest, t("gates.pairs_rest"))));
    return box;
  }

  function pairTable(pairs, caption) {
    var cols = [t("gates.col.scenario"), t("gates.col.family"), t("gates.col.tier_base"),
      t("gates.col.tier_cand"), t("gates.col.ttc_base"), t("gates.col.ttc_cand"),
      t("gates.col.ttc_delta")];
    return h("div", { class: "scroll" }, h("table", {},
      h("caption", { text: caption }),
      h("thead", {}, h("tr", {}, cols.map(function (label) {
        return h("th", { scope: "col", text: label });
      }))),
      h("tbody", {}, pairs.map(function (p) {
        return h("tr", {},
          h("th", { scope: "row" }, h("button", {
            class: "row-btn", text: p.scenario_id,
            onclick: function () { go("/evidence?scenario=" + encodeURIComponent(p.scenario_id)); }
          })),
          h("td", { text: t("family." + p.family) }),
          h("td", { text: p.tier_baseline ? t("tier." + p.tier_baseline) : t("value.none") }),
          h("td", { class: p.tier_worse ? "st st-fail" : "", text: p.tier_candidate ? t("tier." + p.tier_candidate) : t("value.none") }),
          h("td", { class: "n", text: num(p.ttc_baseline, 2) }),
          h("td", { class: "n", text: num(p.ttc_candidate, 2) }),
          h("td", { class: "n " + (p.ttc_drop ? "st-fail" : ""), text: num(p.ttc_delta, 2) })
        );
      }))
    ));
  }

  /* page: coverage ------------------------------------------------------- */

  function pageCoverage() {
    var frag = document.createDocumentFragment();
    var c = candidate();
    if (!c || !c.coverage) { add(frag, h("p", { text: t("evidence.empty_b") })); return frag; }
    var cov = c.coverage;

    add(frag, h("h1", { text: t("coverage.title") }));
    add(frag, h("p", { class: "lede", text: t("coverage.lede") }));
    add(frag, h("p", { class: "small", text: t("coverage.legend") }));

    var byFamily = {};
    cov.rows.forEach(function (r) {
      byFamily[r.family] = byFamily[r.family] || {};
      byFamily[r.family][r.parameter] = byFamily[r.family][r.parameter] || [];
      byFamily[r.family][r.parameter].push(r);
    });

    Object.keys(byFamily).forEach(function (fam) {
      add(frag, h("h2", { text: t("family." + fam) }));
      Object.keys(byFamily[fam]).forEach(function (par) {
        add(frag, h("h3", { text: t("parameter." + par) }));
        add(frag, h("ul", { class: "bins" }, byFamily[fam][par].map(function (r) {
          var label = h("span", { class: "num", text: String(r.n) });
          label.className = "n";
          var inner = r.scenario_ids && r.scenario_ids.length
            ? h("a", { href: "#/evidence?scenario=" + encodeURIComponent(r.scenario_ids.join(",")),
                "aria-label": t("coverage.bin_link", { n: r.n, bin: r.bin_label }) }, label)
            : label;
          return h("li", { class: "bin " + r.status },
            inner,
            h("span", { text: r.bin_label }),
            h("span", { class: "st st-" + (r.status === "ok" ? "pass" : (r.status === "empty" ? "fail" : "sparse")),
              text: " " + t("bin." + r.status) })
          );
        })));
      });
    });

    add(frag, h("p", { text: t("coverage.unbinned", { n: cov.unbinned }) }));
    if (cov.unmapped && cov.unmapped.length) {
      add(frag, h("p", { text: t("coverage.unmapped", { list: cov.unmapped.join(", ") }) }));
    }

    add(frag, h("h2", { text: t("coverage.not_covered_title") }));
    add(frag, h("p", { text: t("coverage.unknown_unsafe") }));
    add(frag, h("ul", {}, (cov.not_covered || []).map(function (r) {
      return h("li", {}, h("strong", { text: t("hazard." + r.hazard) }), " ", t(r.note_key));
    })));
    return frag;
  }

  /* page: assurance case ------------------------------------------------- */

  function pageCase(params) {
    var frag = document.createDocumentFragment();
    var c = candidate();
    if (!c || !c.case || !c.case.nodes) { add(frag, h("p", { text: t("evidence.empty_b") })); return frag; }
    var focus = params.get("node");
    var index = {};
    c.case.nodes.forEach(function (n) { index[n.id] = n; });

    add(frag, h("h1", { text: t("case.title") }));
    add(frag, h("p", { class: "lede", text: t("case.lede") }));

    var root = index[c.case.root] || c.case.nodes[0];
    add(frag, h("ul", { class: "tree" }, renderNode(root, index, focus, 0)));
    return frag;
  }

  function nodeText(node) {
    if (node.text_key === "case.context.deployment") return t("owner.deployment_context");
    return t(node.text_key);
  }

  function renderNode(node, index, focus, depth) {
    if (!node) return null;
    var body = h("div", { class: "node " + node.type + (focus === node.id ? " current" : "") },
      h("span", { class: "tag", text: t("node." + node.type) }),
      h("span", { text: nodeText(node) }),
      node.status !== "info" ? h("span", {}, " ", statusEl(node.status)) : null,
      node.evidence_ref ? h("span", {}, " ", evidenceLink(node.evidence_ref)) : null
    );
    var kids = (node.children || []).map(function (id) {
      return renderNode(index[id], index, focus, depth + 1);
    }).filter(Boolean);
    if (!kids.length) return h("li", { id: "node-" + node.id }, body);
    return h("li", { id: "node-" + node.id },
      h("details", { open: depth < 2 || focus ? "open" : false },
        h("summary", {}, body),
        h("ul", {}, kids)));
  }

  function evidenceLink(ref) {
    if (ref.indexOf(".") > 0 && ref.split(".").length > 2) {
      return h("a", { href: "#/gates?gate=" + encodeURIComponent(ref), text: t("case.see_gate") });
    }
    return h("a", { href: "#/evidence?scenario=" + encodeURIComponent(ref), text: t("case.see_scenario") });
  }

  /* page: evidence ------------------------------------------------------- */

  var FILTERS = { family: "", planner: "", tier: "", text: "" };

  function pageEvidence(params) {
    var frag = document.createDocumentFragment();
    if (params.get("track") === "b" && TRACK !== "b") { TRACK = "b"; }

    if (TRACK === "b") {
      add(frag, h("h1", { text: t("evidence.title_b") }));
      add(frag, h("p", { class: "note", text: t("evidence.redaction") }));
      var cb = candidate();
      if (!cb || !cb.samples || !cb.samples.length) {
        add(frag, h("p", { class: "note", text: t("evidence.empty_b") }));
        add(frag, trackTabs());
        return frag;
      }
      add(frag, sampleTable(cb.samples));
      add(frag, trackTabs());
      return frag;
    }

    var c = candidate();
    if (!c) { add(frag, h("p", { text: t("evidence.empty_b") })); return frag; }

    add(frag, h("h1", { text: t("evidence.title") }));

    var only = null;
    var scenarioParam = params.get("scenario");
    var gateParam = params.get("gate");
    if (scenarioParam) only = scenarioParam.split(",");
    if (gateParam) {
      var g = gateById(gateParam);
      only = g ? g.failing_ids.slice() : [];
      add(frag, h("p", { class: "note bad", text: t("evidence.from_gate", {
        gate: shortName(gateParam), n: only.length
      }) }));
    }
    if (only) {
      add(frag, h("button", { class: "chip", text: t("evidence.clear_filter"), onclick: function () { go("/evidence"); } }));
    }

    var pool = c.results.slice();
    if (only) {
      var set = {};
      only.forEach(function (id) { set[id] = true; });
      pool = pool.filter(function (r) { return set[r.scenario_id]; });
      pool.sort(function (a, b) { return only.indexOf(a.scenario_id) - only.indexOf(b.scenario_id); });
    }

    add(frag, filterBar(c.results));

    var shown = pool.filter(function (r) {
      if (FILTERS.family && r.family !== FILTERS.family) return false;
      if (FILTERS.planner && r.planner !== FILTERS.planner) return false;
      if (FILTERS.tier && r.severity_tier !== FILTERS.tier) return false;
      if (FILTERS.text) {
        var hay = (r.scenario_id + " " + r.description).toLowerCase();
        if (hay.indexOf(FILTERS.text.toLowerCase()) < 0) return false;
      }
      return true;
    });

    add(frag, h("p", { class: "small", text: t("evidence.count", { k: shown.length, n: c.results.length }) }));
    if (!shown.length) {
      add(frag, h("p", { class: "note", text: t("evidence.empty") }));
      return frag;
    }
    add(frag, h("ul", { class: "cards" }, shown.map(resultCard)));
    return frag;
  }

  function uniq(list) {
    var seen = {};
    var out = [];
    list.forEach(function (v) { if (v && !seen[v]) { seen[v] = true; out.push(v); } });
    out.sort();
    return out;
  }

  function filterBar(results) {
    var box = h("div", { class: "toolbar", role: "group", "aria-label": "Filters" });
    var groups = [
      { field: "family", label: t("evidence.filter.family"), prefix: "family.", values: uniq(results.map(function (r) { return r.family; })) },
      { field: "planner", label: t("evidence.filter.planner"), prefix: "", values: uniq(results.map(function (r) { return r.planner; })) },
      { field: "tier", label: t("evidence.filter.tier"), prefix: "tier.", values: uniq(results.map(function (r) { return r.severity_tier; })) }
    ];
    var outer = h("div", {});
    groups.forEach(function (grp) {
      var line = h("div", { class: "toolbar" });
      add(line, h("span", { class: "small filter-label", text: grp.label }));
      add(line, h("button", {
        class: "chip", "aria-pressed": FILTERS[grp.field] === "" ? "true" : "false",
        text: t("evidence.filter.any"),
        onclick: function () { FILTERS[grp.field] = ""; render(); }
      }));
      grp.values.forEach(function (v) {
        add(line, h("button", {
          class: "chip", "aria-pressed": FILTERS[grp.field] === v ? "true" : "false",
          text: grp.prefix ? t(grp.prefix + v) : v,
          onclick: function () { FILTERS[grp.field] = v; render(); }
        }));
      });
      add(outer, line);
    });
    var search = h("input", {
      type: "search", value: FILTERS.text, "aria-label": t("evidence.filter.text"),
      placeholder: t("evidence.filter.text"),
      oninput: function (e) { FILTERS.text = e.target.value; rerenderSoon(); }
    });
    add(box, search);
    add(outer, box);
    return outer;
  }

  var searchTimer = null;
  function rerenderSoon() {
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(function () {
      render();
      var el = document.querySelector('input[type="search"]');
      if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
    }, 200);
  }

  function thumb(r) {
    var img = h("img", { src: r.thumbnail, loading: "lazy",
      alt: t("evidence.thumb_alt", { id: r.scenario_id }) });
    img.addEventListener("error", function () {
      if (img.parentNode) img.parentNode.removeChild(img);
    });
    return img;
  }

  function resultCard(r) {
    var m = r.metrics || {};
    return h("li", { class: "card", id: "scenario-" + r.scenario_id },
      r.thumbnail ? thumb(r) : null,
      h("h3", { text: r.scenario_id }),
      h("p", { class: "small", text: t("family." + r.family) + " " + r.planner + " " },
        r.severity_tier ? h("span", { class: "st st-" + (r.severity_tier === "critical" ? "fail" : (r.severity_tier === "near_miss" ? "conditional" : "pass")),
          text: t("tier." + r.severity_tier) }) : null),
      h("dl", {},
        h("dt", { text: t("metric.ttc_min_s") }), h("dd", { text: num(m.ttc_min_s, 2) }),
        h("dt", { text: t("metric.d_min_m") }), h("dd", { text: num(m.d_min_m, 2) }),
        h("dt", { text: t("metric.collision") }), h("dd", { text: m.collision ? t("value.yes") : t("value.no") }),
        h("dt", { text: t("metric.delta_v_mps") }), h("dd", { text: num(m.delta_v_mps, 2) }),
        h("dt", { text: t("metric.hard_brake_fraction") }), h("dd", { text: num(m.hard_brake_fraction, 2) }),
        h("dt", { text: t("metric.mean_speed_ratio") }), h("dd", { text: num(m.mean_speed_ratio, 2) })
      ),
      h("p", { text: r.description }),
      h("details", {}, h("summary", { text: t("evidence.parameters") }),
        h("dl", {}, Object.keys(r.parameters || {}).map(function (k) {
          return [h("dt", { text: has("parameter." + k) ? t("parameter." + k) : k }),
            h("dd", { text: num(r.parameters[k], 2) })];
        })))
    );
  }

  function sampleTable(samples) {
    var cols = [t("evidence.col.sample"), t("evidence.col.task"), t("evidence.col.category"),
      t("evidence.col.score"), t("evidence.col.completion")];
    return h("div", { class: "scroll" }, h("table", {},
      h("caption", { text: t("evidence.title_b") }),
      h("thead", {}, h("tr", {}, cols.map(function (label) { return h("th", { scope: "col", text: label }); }))),
      h("tbody", {}, samples.map(function (s) {
        return h("tr", {},
          h("th", { scope: "row" }, s.inspect_ref
            ? h("a", { href: s.inspect_ref, text: s.sample_id })
            : document.createTextNode(s.sample_id)),
          h("td", { text: s.task }),
          h("td", { text: s.category || t("value.none") }),
          h("td", { class: "n", text: num(s.score, 2) }),
          h("td", { text: s.completion_public })
        );
      }))
    ));
  }

  /* page: limitations ---------------------------------------------------- */

  function pageLimits() {
    var frag = document.createDocumentFragment();
    var c = candidate();
    add(frag, h("h1", { text: t("limits.title") }));
    add(frag, ownerP("owner.limitations"));
    add(frag, ownerP("owner.deployment_context"));
    if (!c) return frag;

    add(frag, h("h2", { text: t("limits.residual_title") }));
    add(frag, h("p", { text: t("limits.residual_lede") }));
    add(frag, h("div", { class: "scroll" }, h("table", {},
      h("caption", { text: t("limits.residual_title") }),
      h("thead", {}, h("tr", {},
        h("th", { scope: "col", text: t("limits.col.family") }),
        h("th", { scope: "col", text: t("limits.col.cannot_see") }),
        h("th", { scope: "col", text: t("limits.col.not_covered") }))),
      h("tbody", {}, (c.residual_risk || []).map(function (row) {
        return h("tr", {},
          h("th", { scope: "row", text: t("family." + row.family) }),
          h("td", {}, h("ul", {}, row.cannot_see.map(function (k) { return h("li", { text: t(k) }); }))),
          h("td", {}, h("ul", {}, row.not_covered.map(function (hz) { return h("li", { text: t("hazard." + hz) }); })))
        );
      }))
    )));
    return frag;
  }

  /* router --------------------------------------------------------------- */

  var ROUTES = {
    "/": pageDecision,
    "/gates": pageGates,
    "/coverage": pageCoverage,
    "/case": pageCase,
    "/evidence": pageEvidence,
    "/limits": pageLimits
  };

  function parseHash() {
    var raw = location.hash.replace(/^#/, "") || "/";
    var cut = raw.indexOf("?");
    var path = cut < 0 ? raw : raw.slice(0, cut);
    var query = cut < 0 ? "" : raw.slice(cut + 1);
    if (!path) path = "/";
    return { path: path, params: new URLSearchParams(query) };
  }

  function render() {
    var view = document.getElementById("view");
    var route = parseHash();
    var page = ROUTES[route.path] || ROUTES["/"];
    clear(view);
    try {
      add(view, page(route.params));
    } catch (err) {
      add(view, h("p", { class: "note bad", text: t("app.error") }));
      if (window.console) window.console.error(err);
    }
    var links = document.querySelectorAll("#nav a");
    for (var i = 0; i < links.length; i++) {
      var match = links[i].getAttribute("data-route") === route.path;
      if (match) links[i].setAttribute("aria-current", "page");
      else links[i].removeAttribute("aria-current");
    }
    document.title = t("app.title") + " " + t("nav." + routeName(route.path));
  }

  function routeName(path) {
    var map = { "/": "decision", "/gates": "gates", "/coverage": "coverage",
      "/case": "case", "/evidence": "evidence", "/limits": "limits" };
    return map[path] || "decision";
  }

  function applyStaticStrings() {
    var nodes = document.querySelectorAll("[data-s]");
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute("data-s");
      if (has(key)) nodes[i].textContent = t(key);
    }
  }

  function boot() {
    Promise.all([
      fetch("strings.json").then(function (r) { return r.json(); }),
      fetch(DATA_URL).then(function (r) {
        if (!r.ok) throw new Error("no data");
        return r.json();
      })
    ]).then(function (parts) {
      S = parts[0];
      DATA = parts[1];
      applyStaticStrings();
      window.addEventListener("hashchange", render);
      render();
    }).catch(function (err) {
      var view = document.getElementById("view");
      clear(view);
      add(view, h("p", { class: "note bad", text: t("app.error") }));
      if (window.console) window.console.error(err);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
