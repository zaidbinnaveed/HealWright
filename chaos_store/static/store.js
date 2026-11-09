// Chaos Store client. Handlers are attached by inline scripts that the server
// renders right after each element (Renderer.close), so no element attribute
// names its action, and renaming ids, classes or tags never breaks the store.
"use strict";

const cw = (() => {
  const refs = {};

  async function api(method, url, body) {
    const res = await fetch(url, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
    let data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    return { ok: res.ok, status: res.status, data };
  }

  const say = (ref, text) => { if (refs[ref]) refs[ref].textContent = text; };
  const val = (ref) => (refs[ref] ? refs[ref].value : "");
  const errorOf = (r, fallback) => (r.data && r.data.error) || fallback;

  function quantity() {
    const n = parseInt(val("qty") || "1", 10);
    return Number.isFinite(n) && n >= 1 && n <= 10 ? n : 1;
  }

  function showModal(show) {
    if (refs.modal) refs.modal.hidden = !show;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  const handlers = {
    async add_to_cart(el, args) {
      const r = await api("POST", "/api/cart", { product_id: args.pid, qty: quantity() });
      if (r.ok) {
        say("status", `Added to cart (${r.data.count} in cart)`);
        showModal(true);
      } else {
        say("status", errorOf(r, "Could not add to cart"));
      }
    },
    async add_to_wishlist(el, args) {
      const r = await api("POST", "/api/wishlist", { product_id: args.pid });
      say("status", r.ok ? "Added to wishlist" : errorOf(r, "Could not add to wishlist"));
    },
    async save_for_later(el, args) {
      const r = await api("POST", `/api/cart/${args.item}/save`);
      if (r.ok) window.location.reload();
    },
    async remove_coupon() {
      const r = await api("DELETE", "/api/coupon");
      if (r.ok) {
        window.location.reload();
      } else {
        say("coupon_status", errorOf(r, "Could not remove coupon"));
      }
    },
    close_modal() {
      showModal(false);
    },
    async remove_from_cart(el, args) {
      const r = await api("DELETE", `/api/cart/${args.item}`);
      if (r.ok) window.location.reload();
    },
    async apply_coupon() {
      const r = await api("POST", "/api/coupon", { code: val("coupon").trim() || "-" });
      if (r.ok) {
        window.location.reload();
      } else {
        say("coupon_status", errorOf(r, "Could not apply coupon"));
      }
    },
    async place_order() {
      if (!refs.agree || !refs.agree.checked) {
        say("checkout_status", "Please accept the terms");
        return;
      }
      const r = await api("POST", "/api/orders", {
        name: val("ship_name").trim(),
        email: val("email").trim(),
        address: val("address").trim(),
        shipping: val("shipping") || "standard",
      });
      if (r.ok) {
        window.location.assign(`/order/${r.data.id}`);
      } else {
        say("checkout_status", r.status === 422 ? "Please enter your name and a valid email"
          : errorOf(r, "Could not place order"));
      }
    },
    async confirm_order(el, args) {
      const r = await api("POST", `/api/orders/${args.oid}/confirm`);
      say("order_status", r.ok ? "Status: Confirmed" : errorOf(r, "Could not confirm order"));
    },
    async cancel_order(el, args) {
      const r = await api("DELETE", `/api/orders/${args.oid}`);
      say("order_status", r.ok ? "Status: Cancelled" : errorOf(r, "Could not cancel order"));
    },
    async search() {
      const q = val("search_q").trim();
      const r = await api("GET", `/api/search?q=${encodeURIComponent(q)}`);
      const list = refs.search_results;
      if (!list || !r.ok) return;
      list.innerHTML = r.data.results.length
        ? r.data.results.map((p) =>
          `<li><a href="/product/${p.id}">${escapeHtml(p.name)}</a> <span>${escapeHtml(p.price)}</span></li>`).join("")
        : "<li>No products found</li>";
    },
  };

  function bind(el, action, args) {
    const handler = handlers[action];
    if (!el || !handler) return;
    const run = (event) => {
      event.preventDefault();
      handler(el, args || {});
    };
    el.addEventListener("click", run);
    // Keyboard activation for non-native controls (role=button on a div, etc.).
    el.addEventListener("keydown", (event) => {
      if (el.tagName !== "BUTTON" && (event.key === "Enter" || event.key === " ")) run(event);
    });
  }

  function ref(name, el) {
    if (el) refs[name] = el;
  }

  // Enter in the search box runs the search, like a real store.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && refs.search_q && event.target === refs.search_q) {
      event.preventDefault();
      handlers.search();
    }
  });

  return { bind, ref };
})();
