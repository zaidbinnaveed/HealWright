// HealWright element extraction.
//
// Evaluated in ONE page.evaluate round trip. Two modes:
//   - snapshot: every interactive element in the main frame, capped at `max`
//   - target:   the single element passed as `arg.target` (record-time fingerprint),
//               so record time and heal time use exactly the same feature code.
//
// Returns compact rows (arrays, not objects). Text values are only
// whitespace-collapsed and length-bounded here; canonical normalisation
// (NFKC, casefold, zero-width stripping) happens in Python so it is identical
// at record and heal time.
//
// Never reads <script>/<style>/<template>/<noscript> content.
(arg) => {
  "use strict";
  const t0 = performance.now();
  const opts = arg || {};
  const MAX = Math.max(1, Math.min(opts.max || 400, 400));
  const TEXT_MAX = 200;
  const ATTR_MAX = 30;
  const ATTR_VALUE_MAX = 200;
  const CLASS_MAX = 50;
  const ANCESTORS = 6;
  const NEIGHBORS = 5;
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT"]);
  const INTERACTIVE_ROLES = [
    "button", "link", "menuitem", "tab", "checkbox", "switch", "radio", "textbox", "combobox",
  ];
  const SELECTOR = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary",
    ...INTERACTIVE_ROLES.map((r) => `[role="${r}"]`),
    "[tabindex]", "[onclick]", "[contenteditable='']", "[contenteditable='true']",
  ].join(",");

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim().slice(0, TEXT_MAX);

  const implicitRole = (el) => {
    const tag = el.tagName;
    switch (tag) {
      case "A": case "AREA": return el.hasAttribute("href") ? "link" : null;
      case "BUTTON": return "button";
      case "SUMMARY": return "button";
      case "SELECT": return el.multiple || el.size > 1 ? "listbox" : "combobox";
      case "TEXTAREA": return "textbox";
      case "INPUT": {
        const type = (el.getAttribute("type") || "text").toLowerCase();
        if (["button", "submit", "reset", "image"].includes(type)) return "button";
        if (type === "checkbox") return "checkbox";
        if (type === "radio") return "radio";
        if (type === "range") return "slider";
        if (type === "number") return "spinbutton";
        if (type === "search") return el.hasAttribute("list") ? "combobox" : "searchbox";
        if (["text", "email", "tel", "url", "password", ""].includes(type)) {
          return el.hasAttribute("list") ? "combobox" : "textbox";
        }
        return null;
      }
      case "NAV": return "navigation";
      case "MAIN": return "main";
      case "FORM": return "form";
      case "HEADER": return el.closest("article,aside,main,nav,section") ? null : "banner";
      case "FOOTER": return el.closest("article,aside,main,nav,section") ? null : "contentinfo";
      case "ASIDE": return "complementary";
      case "ARTICLE": return "article";
      case "UL": case "OL": return "list";
      case "LI": return "listitem";
      case "DIALOG": return "dialog";
      case "TABLE": return "table";
      case "H1": case "H2": case "H3": case "H4": case "H5": case "H6": return "heading";
      default: return null;
    }
  };

  const roleOf = (el) => {
    const explicit = (el.getAttribute("role") || "").trim().split(/\s+/)[0];
    return explicit ? explicit.toLowerCase() : implicitRole(el);
  };

  const visibleText = (el) => {
    if (SKIP_TAGS.has(el.tagName)) return "";
    // innerText respects CSS visibility and excludes <script> content, BUT for an
    // element that is not rendered (display:none, [hidden]) it falls back to
    // textContent, which includes script source. Unrendered text is not visible.
    if (el.getClientRects().length === 0) return "";
    return clean(el.innerText !== undefined ? el.innerText : el.textContent);
  };

  const textOfIds = (ids) =>
    ids.split(/\s+/).map((id) => document.getElementById(id))
      .filter(Boolean).map((n) => visibleText(n)).join(" ");

  const accessibleName = (el, role) => {
    const labelledby = el.getAttribute("aria-labelledby");
    if (labelledby) {
      const t = clean(textOfIds(labelledby));
      if (t) return t;
    }
    const aria = clean(el.getAttribute("aria-label"));
    if (aria) return aria;
    const tag = el.tagName;
    if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") {
      const type = (el.getAttribute("type") || "").toLowerCase();
      if (tag === "INPUT" && ["button", "submit", "reset"].includes(type)) {
        return clean(el.value || (type === "submit" ? "Submit" : type === "reset" ? "Reset" : ""));
      }
      if (el.labels && el.labels.length) {
        const t = clean(Array.from(el.labels).map((l) => visibleText(l)).join(" "));
        if (t) return t;
      }
      const ph = clean(el.getAttribute("placeholder"));
      if (ph) return ph;
      return clean(el.getAttribute("title"));
    }
    if (tag === "IMG") return clean(el.getAttribute("alt"));
    // Name from content for buttons, links and similar roles.
    let t = visibleText(el);
    if (!t) {
      const img = el.querySelector("img[alt]");
      if (img) t = clean(img.getAttribute("alt"));
    }
    return t || clean(el.getAttribute("title"));
  };

  const hrefPath = (el) => {
    const raw = el.getAttribute("href") || "";
    try {
      return new URL(raw, document.baseURI).pathname;
    } catch (_) {
      // e.g. about:blank base: keep the path part of the raw attribute
      return raw.split(/[?#]/)[0];
    }
  };

  const attributesOf = (el) => {
    const out = {};
    let n = 0;
    const put = (k, v) => {
      if (v === null || v === undefined || n >= ATTR_MAX) return;
      out[k] = String(v).slice(0, ATTR_VALUE_MAX);
      n += 1;
    };
    for (const name of ["id", "name", "type", "placeholder", "data-testid"]) {
      if (el.hasAttribute(name)) put(name, el.getAttribute(name));
    }
    if (el.hasAttribute("href")) put("href", hrefPath(el));
    for (const a of Array.from(el.attributes)) {
      if (a.name.startsWith("aria-")) put(a.name, a.value);
    }
    return out;
  };

  const classesOf = (el) => Array.from(el.classList).slice(0, CLASS_MAX).map((c) => c.slice(0, 100));

  const ancestorsOf = (el) => {
    const out = [];
    let node = el.parentElement;
    while (node && out.length < ANCESTORS) {
      const r = roleOf(node);
      const tag = node.tagName.toLowerCase();
      out.push(r ? `${tag}[${r}]` : tag);
      node = node.parentElement;
    }
    return out;
  };

  const neighborsOf = (el, ownText) => {
    const out = [];
    const seen = new Set([ownText]);
    const add = (node) => {
      if (!node || SKIP_TAGS.has(node.tagName) || out.length >= NEIGHBORS) return;
      if ((node.textContent || "").length > 1000) return; // cheap guard against big containers
      const t = visibleText(node);
      if (t && !seen.has(t)) {
        seen.add(t);
        out.push(t);
      }
    };
    if (el.labels) Array.from(el.labels).forEach(add);
    let node = el;
    for (let depth = 0; depth < 3 && node && out.length < NEIGHBORS; depth += 1) {
      let prev = node.previousElementSibling;
      let next = node.nextElementSibling;
      while ((prev || next) && out.length < NEIGHBORS) {
        if (prev) { add(prev); prev = prev.previousElementSibling; }
        if (next) { add(next); next = next.nextElementSibling; }
      }
      node = node.parentElement;
    }
    return out;
  };

  const r1 = (v) => Math.round(v * 10) / 10;

  const row = (el) => {
    const role = roleOf(el);
    const text = visibleText(el);
    const b = el.getBoundingClientRect();
    return [
      role,
      accessibleName(el, role),
      el.tagName.toLowerCase(),
      text,
      attributesOf(el),
      classesOf(el),
      ancestorsOf(el),
      neighborsOf(el, text),
      [r1(b.x), r1(b.y), r1(b.width), r1(b.height)],
      el.getRootNode() instanceof ShadowRoot,
    ];
  };

  const isCandidate = (el) => {
    if (SKIP_TAGS.has(el.tagName)) return false;
    if (el.getClientRects().length === 0) return false; // display:none or detached
    const ti = el.getAttribute("tabindex");
    const native = el.matches("a[href],button,input,select,textarea,summary,[onclick]");
    const roleHit = INTERACTIVE_ROLES.includes((el.getAttribute("role") || "").toLowerCase());
    const editable = el.isContentEditable;
    if (!native && !roleHit && !editable) {
      // only reason to be here is tabindex: require tabindex >= 0
      return ti !== null && parseInt(ti, 10) >= 0;
    }
    return true;
  };

  let hasShadowRoots = false;
  const all = document.querySelectorAll("*");
  for (let i = 0; i < all.length; i += 1) {
    if (all[i].shadowRoot) { hasShadowRoots = true; break; }
  }

  const fields = [
    "role", "name", "tag", "text", "attrs", "classes", "ancestors", "neighbors", "bbox", "in_shadow",
  ];
  // Page state for contracts: rendered dialogs and DOM node count.
  const modalNodes = new Set(document.querySelectorAll(
    "dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]"));
  let modals = 0;
  modalNodes.forEach((m) => { if (m.getClientRects().length > 0) modals += 1; });

  const page = {
    v: 1,
    fields,
    viewport: [window.innerWidth, window.innerHeight],
    has_iframes: document.querySelector("iframe,frame") !== null,
    has_shadow_roots: hasShadowRoots,
    state: { nodes: document.getElementsByTagName("*").length, modals },
  };

  if (opts.target !== undefined) {
    // target mode; target may be null (element not present yet) -> state only
    const el = opts.target;
    return { ...page, mode: "target", total: el ? 1 : 0, truncated: false,
             rows: el ? [row(el)] : [], ms: r1(performance.now() - t0) };
  }

  const found = Array.from(document.querySelectorAll(SELECTOR)).filter(isCandidate);
  const kept = found.slice(0, MAX);
  if (opts.keep) {
    Object.defineProperty(window, "__healwright_candidates", {
      value: kept, configurable: true, enumerable: false, writable: true,
    });
  }
  return {
    ...page,
    mode: "snapshot",
    total: found.length,
    truncated: found.length > MAX,
    rows: kept.map(row),
    ms: r1(performance.now() - t0),
  };
}
