"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");
const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "ui/ui/index.html"), "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 1);
function redirect(href) {
  const calls = [], link = {};
  vm.runInNewContext(scripts[0][1], {
    URL,
    window: {location: {href, replace: target => calls.push(target)}},
    document: {getElementById: id => {assert.equal(id, "continue"); return link;}},
  }, {timeout: 1000});
  return {calls, link};
}
for (const [name, source, expected] of [
  ["Pages repository path", "https://example.test/AtlanticBridge-Signals/ui/", "https://example.test/AtlanticBridge-Signals/"],
  ["root domain", "https://example.test/ui/", "https://example.test/"],
  ["explicit index", "https://example.test/AtlanticBridge-Signals/ui/index.html", "https://example.test/AtlanticBridge-Signals/"],
  ["query and case deep link", "https://example.test/AtlanticBridge-Signals/ui/?ref=old%20link&x=%26#companies?case=case-1", "https://example.test/AtlanticBridge-Signals/?ref=old%20link&x=%26#companies?case=case-1"],
  ["query cannot redirect offsite", "https://example.test/ui/?next=https://evil.test/#//evil.test/", "https://example.test/?next=https://evil.test/#//evil.test/"],
  ["malicious-looking hash stays text", "https://example.test/ui/#javascript:alert(1)</script><img%20src=x%20onerror=alert(1)>", "https://example.test/#javascript:alert(1)%3C/script%3E%3Cimg%20src=x%20onerror=alert(1)%3E"],
]) {
  test(name, () => {
    const {calls, link} = redirect(source);
    assert.deepEqual(calls, [expected]);
    assert.equal(link.href, expected);
    assert.equal(new URL(calls[0]).origin, new URL(source).origin);
    assert.deepEqual(redirect(expected).calls, [], "canonical URL cannot bounce back");
  });
}
test("unrelated paths do not redirect", () => {
  for (const pathname of ["/", "/AtlanticBridge-Signals/", "/AtlanticBridge-Signals/index.html", "/preview/", "/ui/other.html"]) {
    assert.deepEqual(redirect("https://example.test" + pathname).calls, []);
  }
});
test("published app is the terminal route and alias has a no-script link", () => {
  const canonical = fs.readFileSync(path.join(root, "ui/index.html"), "utf8");
  assert.match(canonical, /data-ui-version=/);
  assert.doesNotMatch(canonical, /http-equiv=["']refresh|location\.replace/);
  assert.doesNotMatch(html, /http-equiv=["']refresh|innerHTML|document\.write/);
  assert.match(html, /<a id="continue" href="\.\.\/">Continue<\/a>/);
});
