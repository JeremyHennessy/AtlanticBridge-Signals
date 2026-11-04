(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.BodaccSearch = api;
    if (root.document) api.init(root.document);
  }
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const SEARCH_URL = "https://www.bodacc.fr/pages/annonces-commerciales-recherche/";
  function buildSearchUrl(value) {
    if (typeof value !== "string" || !/^\d{9}$/.test(value)) return null;
    const query = new URLSearchParams({ "q.registre": `registre:${value}`, sort: "dateparution" });
    return `${SEARCH_URL}?${query.toString()}`;
  }
  function init(document) {
    const input = document.getElementById("bodacc-siren");
    const link = document.getElementById("bodacc-search-link");
    const status = document.getElementById("bodacc-lookup-status");
    if (!input || !link || !status) return false;
    function update() {
      const url = buildSearchUrl(input.value);
      if (!url) {
        link.hidden = true;
        link.removeAttribute("href");
        status.textContent = "Enter exactly nine digits for a verified French SIREN.";
        return;
      }
      link.href = url;
      link.hidden = false;
      status.textContent = "Ready. Check the legal entity and the dates on the official BODACC site.";
    }
    input.addEventListener("input", update);
    update();
    return true;
  }
  return { buildSearchUrl, init };
});
