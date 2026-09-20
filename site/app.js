/* Assurance Gate dashboard. Vanilla ES2020, no dependencies, no build step. */
(function () {
  "use strict";

  var DEV = new URLSearchParams(location.search).has("dev");
  var DATA_URL = DEV ? "dev/sample_data.json" : "data.json";
  var DATA_B_URL = DEV ? "dev/sample_data_b.json" : "data_b.json";

  /* Optional page configuration, set by an inline script before this file.
     The Space build leaves it unset and behaves exactly as before. */
  var CFG = window.GATE_CONFIG || {};

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

  var SVG_NS = "http://www.w3.org/2000/svg";

  /* Same shape as h, for SVG nodes. Every figure is drawn, never pasted. */
  function sv(tag, props) {
    var n = document.createElementNS(SVG_NS, tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "text") n.appendChild(document.createTextNode(String(v)));
        else n.setAttribute(k, String(v));
      });
    }
    for (var i = 2; i < arguments.length; i++) add(n, arguments[i]);
    return n;
  }

  function r1(v) {
    return Math.round(v * 10) / 10;
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

  /* Some hazards arrive as a display name rather than a strings key. */
  function hazardName(id) {
    return has("hazard." + id) ? t("hazard." + id) : id;
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

  /* Decision opening ----------------------------------------------------- */

  /* Isometric line drawing in the same hand as the project cards: eval
     records flow into a gate panel, five bars stand against one threshold
     line fixed before the run, one bar crosses it, a verdict slab below. */
  var SCHEM_HAIR = [
    "125.4,80.0 73.4,110.0", "160.0,100.0 108.0,130.0",
    "194.6,120.0 142.7,150.0", "229.3,140.0 177.3,170.0",
    "90.7,80.0 229.3,160.0", "73.4,90.0 212.0,170.0"
  ];
  var SCHEM_BARS = [
    ["98.0,58.0 117.0,69.0 117.0,95.0 98.0,84.0", false],
    ["124.0,73.0 143.0,84.0 143.0,106.0 124.0,95.0", false],
    ["150.0,88.0 169.0,99.0 169.0,124.0 150.0,113.0", false],
    ["176.0,79.0 195.0,90.0 195.0,143.0 176.0,132.0", true],
    ["202.0,118.0 221.0,129.0 221.0,152.0 202.0,141.0", false]
  ];
  var SCHEM_SLAB = [
    "56.1,150.0 160.0,210.0 149.6,216.0 45.7,156.0",
    "160.0,213.0 149.6,219.0 149.6,216.0 160.0,210.0",
    "45.7,159.0 149.6,219.0 149.6,216.0 45.7,156.0"
  ];

  /* A flat isometric tile, used for the incoming evaluation records. */
  function diamond(cx, cy, w, hh) {
    return [
      cx + "," + (cy - hh), (cx + w) + "," + cy,
      cx + "," + (cy + hh), (cx - w) + "," + cy
    ].join(" ");
  }

  function schematic() {
    var g = sv("svg", {
      "class": "schem", viewBox: "30 16 266 226", role: "img",
      "aria-label": t("decision.schematic_alt"), focusable: "false",
      fill: "none", stroke: "currentColor", "stroke-width": "1.2"
    });
    add(g, sv("text", { x: 36, y: 26, "text-anchor": "start", text: t("fig.results") }));
    [34, 48, 62].forEach(function (cy) {
      add(g, sv("polygon", { points: diamond(52, cy, 11, 6) }));
    });
    add(g, sv("polyline", { points: "63,48 96,70", "class": "link" }));
    add(g, sv("polygon", { points: "108.0,70.0 246.6,150.0 194.6,180.0 56.1,100.0" }));
    SCHEM_HAIR.forEach(function (p) {
      add(g, sv("polyline", { points: p, "class": "hair" }));
    });
    SCHEM_BARS.forEach(function (bar) {
      add(g, sv("polygon", { points: bar[0], "class": bar[1] ? "bar hot" : "bar" }));
    });
    add(g, sv("polyline", { points: "82.0,48.0 236.0,137.0", "class": "lead" }));
    add(g, sv("text", { x: 84, y: 44, "text-anchor": "start", text: t("fig.threshold") }));
    add(g, sv("text", { x: 178, y: 74, "text-anchor": "start", "class": "hot",
      fill: "currentColor", text: t("fig.flagged") }));
    SCHEM_SLAB.forEach(function (p) { add(g, sv("polygon", { points: p })); });
    add(g, sv("text", { x: 44, y: 234, "text-anchor": "start", text: t("fig.verdict") }));
    return g;
  }

  function introBlock() {
    return h("section", { "class": "intro", "aria-labelledby": "intro-title" },
      h("h2", { id: "intro-title", text: t("decision.intro_title") }),
      h("div", { "class": "intro-grid" },
        h("ul", { "class": "intro-lines" },
          ["decision.intro_1", "decision.intro_2", "decision.intro_3", "decision.intro_4"]
            .map(function (key) { return h("li", { text: t(key) }); })),
        h("div", {}, schematic())),
      h("p", { "class": "how-to-read", text: t("decision.how_to_read") })
    );
  }

  /* page: decision ------------------------------------------------------- */

  function pageDecision() {
    var frag = document.createDocumentFragment();
    var s = suite();
    var c = candidate();
    add(frag, trackSwitch());
    add(frag, ribbonAndBanner());

    if (!c) {
      add(frag, h("p", { text: t("evidence.empty_b") }));
      return frag;
    }

    add(frag, introBlock());
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

    return frag;
  }

  /* Two segmented buttons under the nav, each with its one line description.
     The ?track=b URL still drives this through the router. */
  function trackSwitch() {
    var seg = h("div", { class: "seg", role: "group", "aria-label": t("decision.tracks_title") });
    add(seg, h("button", {
      class: "", "aria-pressed": TRACK === "a" ? "true" : "false",
      text: t("track.a_short"), onclick: function () { setTrack("a"); }
    }));
    add(seg, h("button", {
      class: "", "aria-pressed": TRACK === "b" ? "true" : "false",
      text: t("track.b_short"), onclick: function () { setTrack("b"); }
    }));
    var bar = h("div", { class: "trackbar" }, seg,
      h("p", { class: "desc" },
        h("strong", { text: t("track.a_short") }), " ", t("track.a_desc")),
      h("p", { class: "desc" },
        h("strong", { text: t("track.b_short") }), " ", t("track.b_desc")));
    var box = h("div", {}, bar);
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

  /* gate figures --------------------------------------------------------- */

  var FIG_W = 320;
  var FIG_X0 = 10;
  var FIG_X1 = 296;
  var FIG_Y = 28;

  function figShell(label) {
    return sv("svg", {
      "class": "gfig", viewBox: "0 0 " + FIG_W + " 52", role: "img",
      "aria-label": label, focusable: "false", fill: "none", stroke: "currentColor"
    });
  }

  function figAxis(g, loLabel, hiLabel) {
    add(g, sv("line", {
      x1: FIG_X0, y1: FIG_Y, x2: FIG_X1, y2: FIG_Y, "class": "axis"
    }));
    add(g, sv("text", { x: FIG_X0, y: 48, "text-anchor": "start", text: loLabel }));
    add(g, sv("text", { x: FIG_X1, y: 48, "text-anchor": "end", text: hiLabel }));
  }

  /* One rate gate: the interval between bound and point estimate, both
     marked, against the threshold line and the side the gate allows. */
  function rateFigure(gate, label) {
    var point = Number(gate.point_estimate);
    var bound = Number(gate.bound);
    var thr = Number(gate.threshold);
    var g = figShell(label);

    function X(v) {
      var c = Math.max(0, Math.min(1, v));
      return r1(FIG_X0 + (FIG_X1 - FIG_X0) * c);
    }

    var xt = X(thr);
    var zoneFrom = gate.direction === "ceiling" ? FIG_X0 : xt;
    var zoneTo = gate.direction === "ceiling" ? xt : FIG_X1;
    add(g, sv("rect", {
      x: zoneFrom, y: FIG_Y - 13, width: Math.max(1, zoneTo - zoneFrom), height: 26,
      "class": "zone"
    }));
    figAxis(g, "0", "1");

    var lo = Math.min(X(point), X(bound));
    var hi = Math.max(X(point), X(bound));
    add(g, sv("line", {
      x1: lo, y1: FIG_Y, x2: Math.max(hi, lo + 1), y2: FIG_Y,
      "class": "iv s-" + gate.status
    }));
    add(g, sv("line", {
      x1: X(bound), y1: FIG_Y - 9, x2: X(bound), y2: FIG_Y + 9,
      "class": "tick s-" + gate.status
    }));
    add(g, sv("circle", {
      cx: X(point), cy: FIG_Y, r: 4.5, "class": "dot-" + gate.status
    }));
    add(g, sv("line", { x1: xt, y1: FIG_Y - 16, x2: xt, y2: FIG_Y + 16, "class": "thr" }));
    add(g, sv("text", {
      x: xt, y: 12, "text-anchor": xt > FIG_W - 60 ? "end" : "middle",
      text: num(thr, 2)
    }));
    return g;
  }

  /* One count gate: failing results as a bar against the allowed count. */
  function countFigure(gate, label) {
    var nFail = Number(gate.n_fail || 0);
    var allowed = Number(gate.threshold || 0);
    var top = Math.max(nFail, allowed, 1) * 1.25;
    var g = figShell(label);

    function X(v) {
      return r1(FIG_X0 + (FIG_X1 - FIG_X0) * Math.max(0, Math.min(1, v / top)));
    }

    figAxis(g, "0", String(Math.round(top)));
    add(g, sv("rect", {
      x: FIG_X0, y: FIG_Y - 7, width: Math.max(2, X(nFail) - FIG_X0), height: 14,
      "class": "dot-" + gate.status
    }));
    var xt = X(allowed);
    add(g, sv("line", { x1: xt, y1: FIG_Y - 16, x2: xt, y2: FIG_Y + 16, "class": "thr" }));
    add(g, sv("text", {
      x: xt, y: 12, "text-anchor": xt < 40 ? "start" : "middle", text: String(allowed)
    }));
    return g;
  }

  function gateFigure(gate) {
    if (gate.kind === "rate" && gate.point_estimate !== null && gate.bound !== null) {
      return rateFigure(gate, t("gates.fig_rate_alt", {
        gate: shortName(gate.gate_id), point: pct(gate.point_estimate),
        bound: pct(gate.bound), threshold: num(gate.threshold, 2)
      }));
    }
    return countFigure(gate, t("gates.fig_count_alt", {
      gate: shortName(gate.gate_id), n_fail: gate.n_fail || 0,
      allowed: num(gate.threshold, 0)
    }));
  }

  function directionLine(gate) {
    if (gate.kind === "rate") {
      return h("p", { class: "figline",
        text: gate.direction === "ceiling" ? t("gates.dir_ceiling") : t("gates.dir_floor") });
    }
    return h("p", { class: "figline" },
      t("gates.fig_failing") + " ",
      h("span", { class: "num", text: String(gate.n_fail || 0) }), ". ",
      t("gates.dir_max"));
  }

  /* page: gates ---------------------------------------------------------- */

  function pageGates(params) {
    var frag = document.createDocumentFragment();
    var c = candidate();
    if (!c) { add(frag, h("p", { text: t("evidence.empty_b") })); return frag; }
    var focus = params.get("gate");

    add(frag, h("h1", { text: t("gates.title") }));
    add(frag, h("p", { class: "lede", text: t("gates.lede") }));
    add(frag, h("p", { class: "figlegend", text: t("gates.fig_legend") }));

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
      var figTr = h("tr", { class: "figrow" },
        h("td", { colspan: "9" },
          gateFigure(g), directionLine(g)));
      return [tr, figTr];
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
      /* The worked example is an illustration of the mechanism, so its
         figure carries no verdict colour. The prose states the outcome. */
      var wFig = {
        gate_id: w.gate_id, kind: "rate", direction: "floor", status: "not_applicable",
        point_estimate: w.point_estimate, bound: w.bound, threshold: w.threshold
      };
      add(frag, h("h2", { text: t("gates.worked_example_title") }));
      add(frag, h("div", { class: "example" },
        gateFigure(wFig),
        directionLine(wFig),
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

    var hazardOnly = cov.rows.length > 0 && cov.rows.every(function (r) {
      return r.family === "hazard";
    });

    add(frag, h("h1", { text: t("coverage.title") }));
    if (hazardOnly) {
      add(frag, h("p", { class: "lede", text: t("coverage.b_lede") }));
    } else {
      add(frag, h("p", { class: "lede", text: t("coverage.lede") }));
      add(frag, h("p", { class: "small", text: t("coverage.legend") }));
    }

    var byFamily = {};
    cov.rows.forEach(function (r) {
      byFamily[r.family] = byFamily[r.family] || {};
      byFamily[r.family][r.parameter] = byFamily[r.family][r.parameter] || [];
      byFamily[r.family][r.parameter].push(r);
    });

    if (hazardOnly) {
      add(frag, hazardBars(byFamily.hazard));
    } else {
      Object.keys(byFamily).forEach(function (fam) {
        add(frag, h("h2", { text: t("family." + fam) }));
        add(frag, coverageGrid(fam, byFamily[fam]));
      });
    }

    add(frag, h("p", { text: t("coverage.unbinned", { n: cov.unbinned }) }));
    if (cov.unmapped && cov.unmapped.length) {
      add(frag, h("p", { text: t("coverage.unmapped", { list: cov.unmapped.join(", ") }) }));
    }

    add(frag, h("h2", { text: t("coverage.not_covered_title") }));
    add(frag, h("p", { text: t("coverage.unknown_unsafe") }));
    add(frag, h("ul", {}, (cov.not_covered || []).map(function (r) {
      return h("li", {}, h("strong", { text: hazardName(r.hazard) }), " ", t(r.note_key));
    })));
    return frag;
  }

  function binStatusClass(status) {
    if (status === "ok") return "pass";
    return status === "empty" ? "fail" : "sparse";
  }

  /* One grid per family. Rows are parameters, columns are the bins of
     equal width, and the count sits inside the cell. */
  function coverageGrid(fam, byParam) {
    var params = Object.keys(byParam);
    var width = 0;
    params.forEach(function (p) { width = Math.max(width, byParam[p].length); });

    var cols = [];
    for (var i = 0; i < width; i++) cols.push(i);

    return h("div", { class: "scroll" }, h("table", { class: "grid" },
      h("caption", { text: t("coverage.grid_caption", { family: t("family." + fam) }) }),
      h("thead", {}, h("tr", {},
        h("th", { scope: "col", text: t("coverage.col.parameter") }),
        cols.map(function (i) {
          return h("th", { scope: "col", class: "n", text: t("coverage.col.bin", { i: i + 1 }) });
        }))),
      h("tbody", {}, params.map(function (par) {
        var rows = byParam[par];
        return h("tr", {},
          h("th", { scope: "row", text: has("parameter." + par) ? t("parameter." + par) : par }),
          cols.map(function (i) {
            var r = rows[i];
            if (!r) return h("td", { class: "cell" });
            var n = h("span", { class: "cell-n", text: String(r.n) });
            var inner = r.scenario_ids && r.scenario_ids.length
              ? h("a", {
                  href: "#/evidence?scenario=" + encodeURIComponent(r.scenario_ids.join(",")),
                  "aria-label": t("coverage.bin_link", { n: r.n, bin: r.bin_label })
                }, n)
              : n;
            return h("td", { class: "cell " + r.status },
              inner,
              h("span", { class: "cell-range", text: r.bin_label }),
              h("span", {
                class: "cell-state st st-" + binStatusClass(r.status),
                text: t("bin." + r.status)
              }));
          }));
      }))
    ));
  }

  /* Track B: one row per hazard category, the sample count as a bar. */
  function hazardBars(byParam) {
    var params = Object.keys(byParam);
    var top = 1;
    params.forEach(function (p) {
      byParam[p].forEach(function (r) { top = Math.max(top, r.n); });
    });

    return h("div", { class: "scroll" }, h("table", { class: "grid" },
      h("caption", { text: t("coverage.b_title") }),
      h("thead", {}, h("tr", {},
        h("th", { scope: "col", text: t("coverage.b_col.hazard") }),
        h("th", { scope: "col", text: t("coverage.b_col.count") }),
        h("th", { scope: "col", class: "n", text: t("gates.col.n") }))),
      h("tbody", {}, params.map(function (par) {
        var r = byParam[par][0];
        var w = Math.max(1, Math.round(280 * (r.n / top)));
        var bar = sv("svg", {
          "class": "hbar", viewBox: "0 0 280 18", role: "img",
          "aria-label": t("coverage.b_bar_alt", { n: r.n }), focusable: "false"
        },
          sv("rect", { x: 0, y: 4, width: 280, height: 10, "class": "bg" }),
          sv("rect", { x: 0, y: 4, width: w, height: 10, "class": "fill" }));
        return h("tr", {},
          h("th", { scope: "row", class: "hazname", text: r.bin_label }),
          h("td", { class: "barcell" }, bar),
          h("td", { class: "n" },
            h("span", { class: "num", text: String(r.n) }), " ",
            h("span", {
              class: "st st-" + binStatusClass(r.status), text: t("bin." + r.status)
            })));
      }))
    ));
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
    var body = h("div", {
      class: "node " + node.type + " s-" + (node.status || "info")
        + (focus === node.id ? " current" : "")
    },
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
        add(frag, trackSwitch());
        return frag;
      }
      add(frag, sampleBlock(cb.samples));
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
    add(frag, h("p", { class: "small", text: t("evidence.mini_caption") }));
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

  /* The two predicate thresholds the Track A gates read, 1.5 s and 0.5 m.
     Each card draws its own value against them. */
  var MINI = [
    { key: "ttc_min_s", label: "evidence.mini_ttc", threshold: 1.5, lo: 0, hi: 4.5 },
    { key: "d_min_m", label: "evidence.mini_dist", threshold: 0.5, lo: -0.5, hi: 2 }
  ];

  function miniFigure(m) {
    var g = sv("svg", {
      "class": "mini", viewBox: "0 0 240 56", role: "img",
      "aria-label": t("evidence.mini_alt"), focusable: "false"
    });
    MINI.forEach(function (spec, i) {
      var y = 8 + i * 26;
      var x0 = 54;
      var x1 = 232;
      function X(v) {
        var c = (Math.max(spec.lo, Math.min(spec.hi, v)) - spec.lo) / (spec.hi - spec.lo);
        return r1(x0 + (x1 - x0) * c);
      }
      var value = m[spec.key];
      add(g, sv("text", { x: 0, y: y + 12, "text-anchor": "start", text: t(spec.label) }));
      add(g, sv("rect", { x: x0, y: y + 3, width: x1 - x0, height: 11, "class": "bg" }));
      if (value !== null && value !== undefined) {
        var ok = Number(value) >= spec.threshold;
        var from = X(Math.min(spec.threshold, spec.lo < 0 ? 0 : spec.lo));
        var to = X(Number(value));
        add(g, sv("rect", {
          x: Math.min(from, to), y: y + 3,
          width: Math.max(2, Math.abs(to - from)), height: 11,
          "class": ok ? "bar-pass" : "bar-fail"
        }));
      }
      add(g, sv("line", {
        x1: X(spec.threshold), y1: y, x2: X(spec.threshold), y2: y + 17, "class": "thr"
      }));
    });
    return g;
  }

  function tierClass(tier) {
    if (tier === "critical") return "fail";
    return tier === "near_miss" ? "conditional" : "pass";
  }

  function resultCard(r) {
    var m = r.metrics || {};
    return h("li", { class: "card", id: "scenario-" + r.scenario_id },
      r.thumbnail ? thumb(r) : null,
      h("h3", { text: r.scenario_id }),
      h("p", { class: "small", text: t("family." + r.family) + " " + r.planner + " " },
        r.severity_tier ? h("span", { class: "pill st-" + tierClass(r.severity_tier),
          text: t("tier." + r.severity_tier) }) : null),
      miniFigure(m),
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

  /* Stored refs are relative to the report root. A published page that
     keeps the evaluation bundle elsewhere sets inspectBase. */
  function inspectHref(ref) {
    if (!CFG.inspectBase) return ref;
    var base = String(CFG.inspectBase);
    if (base.charAt(base.length - 1) !== "/") base += "/";
    return base + String(ref).replace(/^\/+/, "");
  }

  /* Track B holds hundreds of samples. One page of 50 is rendered at a
     time and the button extends the page, so the filters stay put. */
  var B_FILTERS = { task: "", text: "" };
  var B_PAGE = 50;

  function sampleBlock(samples) {
    var box = document.createDocumentFragment();
    var tasks = uniq(samples.map(function (s) { return s.task; }));

    var line = h("div", { class: "toolbar" });
    add(line, h("span", { class: "small filter-label", text: t("evidence.col.task") }));
    add(line, h("button", {
      class: "chip", "aria-pressed": B_FILTERS.task === "" ? "true" : "false",
      text: t("evidence.filter.any"),
      onclick: function () { B_FILTERS.task = ""; B_PAGE = 50; render(); }
    }));
    tasks.forEach(function (v) {
      add(line, h("button", {
        class: "chip", "aria-pressed": B_FILTERS.task === v ? "true" : "false", text: v,
        onclick: function () { B_FILTERS.task = v; B_PAGE = 50; render(); }
      }));
    });
    add(box, line);
    add(box, h("div", { class: "toolbar" }, h("input", {
      type: "search", value: B_FILTERS.text, "aria-label": t("evidence.filter.text_b"),
      placeholder: t("evidence.filter.text_b"),
      oninput: function (e) { B_FILTERS.text = e.target.value; B_PAGE = 50; rerenderSoon(); }
    })));

    var needle = B_FILTERS.text.toLowerCase();
    var shown = samples.filter(function (s) {
      if (B_FILTERS.task && s.task !== B_FILTERS.task) return false;
      if (needle) {
        var hay = (s.sample_id + " " + (s.completion_public || "")).toLowerCase();
        if (hay.indexOf(needle) < 0) return false;
      }
      return true;
    });

    var page = shown.slice(0, B_PAGE);
    add(box, h("p", { class: "small", text: t("evidence.count_b", { k: page.length, n: shown.length }) }));
    if (!page.length) {
      add(box, h("p", { class: "note", text: t("evidence.empty") }));
      add(box, trackSwitch());
      return box;
    }
    add(box, sampleTable(page));
    if (shown.length > page.length) {
      add(box, h("p", { class: "more" }, h("button", {
        class: "chip", text: t("evidence.show_more"),
        onclick: function () { B_PAGE += 50; render(); }
      })));
    }
    add(box, trackSwitch());
    return box;
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
            ? h("a", { href: inspectHref(s.inspect_ref), text: s.sample_id })
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
          h("td", {}, h("ul", {}, row.not_covered.map(function (hz) { return h("li", { text: hazardName(hz) }); })))
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
    var wantB = route.params.get("track") === "b";
    if (wantB && TRACK !== "b" && B_STATE !== "loading") { setTrack("b"); return; }
    if (!wantB && route.params.get("track") === "a" && TRACK !== "a") { TRACK = "a"; }
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

  /* case study page layout ----------------------------------------------- */

  /* Slots that sit above the dashboard header, in order. */
  var CS_TOP = ["crumbs", "intro", "status", "glance", "problem", "what",
                "solution", "result"];
  /* Slots that sit under the dashboard view, above its own footnote. */
  var CS_BOTTOM = ["architecture", "why", "how", "criteria", "metrics", "not"];

  function slotBox(node) {
    var box = h("div", { class: "wrap cs" });
    box.appendChild(node);
    return box;
  }

  /* Fragments are parsed with DOMParser and adopted, so no markup string
     ever reaches the live document. */
  function mountCaseStudy(text) {
    var doc = new DOMParser().parseFromString(text, "text/html");
    var slots = {};
    var found = doc.querySelectorAll("[data-slot]");
    for (var i = 0; i < found.length; i++) {
      slots[found[i].getAttribute("data-slot")] = found[i];
    }

    var header = document.querySelector("header.top");
    var foot = document.querySelector("footer.foot");
    if (!header || !foot) return;

    CS_TOP.forEach(function (name) {
      if (!slots[name]) return;
      document.body.insertBefore(slotBox(document.adoptNode(slots[name])), header);
    });
    CS_BOTTOM.forEach(function (name) {
      if (!slots[name]) return;
      document.body.insertBefore(slotBox(document.adoptNode(slots[name])), foot);
    });
    if (slots.footer) {
      document.body.insertBefore(
        slotBox(document.adoptNode(slots.footer)), foot.nextSibling);
    }
    document.body.classList.add("has-casestudy");
  }

  function loadCaseStudy() {
    if (!CFG.casestudy) return Promise.resolve(null);
    return fetch("casestudy.html").then(function (r) {
      if (!r.ok) throw new Error("no case study");
      return r.text();
    }).catch(function (err) {
      if (window.console) window.console.error(err);
      return null;
    });
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
      }),
      loadCaseStudy()
    ]).then(function (parts) {
      S = parts[0];
      DATA = parts[1];
      if (parts[2]) mountCaseStudy(parts[2]);
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
