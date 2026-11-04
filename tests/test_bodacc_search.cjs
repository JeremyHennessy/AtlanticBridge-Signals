"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
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

test("browser script initializes automatically and carries the SIREN into the official destination", () => {
  const listeners = {};
  const input = { value: "", addEventListener: (name, fn) => { listeners[name] = fn; } };
  const link = { hidden: true, removeAttribute(name) { if (name === "href") delete this.href; } };
  const status = { textContent: "" };
  const elements = { "bodacc-siren": input, "bodacc-search-link": link, "bodacc-lookup-status": status };
  const document = { getElementById: id => elements[id] };
  const script = fs.readFileSync(path.join(__dirname, "../ui/bodacc-search.js"), "utf8");
  vm.runInNewContext(script, { document, URLSearchParams });
  assert.equal(typeof listeners.input, "function");
  assert.equal(link.hidden, true);
  input.value = "987654321";
  listeners.input();
  assert.equal(link.hidden, false);
  const destination = new URL(link.href);
  assert.equal(destination.origin, "https://www.bodacc.fr");
  assert.equal(destination.searchParams.get("q.registre"), "registre:987654321");
});

test("app markup loads the helper and exposes the expected lookup controls", () => {
  const html = fs.readFileSync(path.join(__dirname, "../ui/index.html"), "utf8");
  assert.match(html, /<script src="bodacc-search\.js" defer><\/script>/);
  assert.match(html, /id="bodacc-siren"[^>]*pattern="\[0-9\]\{9\}"/);
  assert.match(html, /id="bodacc-search-link"[^>]*target="_blank"[^>]*referrerpolicy="no-referrer"/);
});
