"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { buildSearchUrl, init } = require("../ui/bodacc-search.js");
test("builds a fixed official BODACC SIREN search URL", () => {
  const url = new URL(buildSearchUrl("123456789"));
  assert.equal(url.origin, "https://www.bodacc.fr");
  assert.equal(url.pathname, "/pages/annonces-commerciales-recherche/");
  assert.equal(url.searchParams.get("q.registre"), "registre:123456789");
  assert.equal(url.searchParams.get("sort"), "dateparution");
});
test("rejects invalid values and URL injection", () => {
  for (const value of ["", "12345678", "1234567890", "12345abc9", "123456789&x=y", " registre:123456789", null]) {
    assert.equal(buildSearchUrl(value), null, String(value));
  }
});
test("shows a search link only for an exact nine-digit identifier", () => {
  const listeners = {};
  const input = { value: "", addEventListener: (name, fn) => { listeners[name] = fn; } };
  const link = { hidden: false, href: "stale", removeAttribute(name) { if (name === "href") delete this.href; } };
  const status = { textContent: "" };
  const elements = { "bodacc-siren": input, "bodacc-search-link": link, "bodacc-lookup-status": status };
  assert.equal(init({ getElementById: id => elements[id] }), true);
  assert.equal(link.hidden, true);
  input.value = "123456789"; listeners.input();
  assert.equal(link.hidden, false);
  assert.equal(new URL(link.href).searchParams.get("q.registre"), "registre:123456789");
  input.value = "12345abc9"; listeners.input();
  assert.equal(link.hidden, true);
  assert.equal(Object.hasOwn(link, "href"), false);
});
