/* Separate research lane. Published snapshot and local review are never qualification gates. */
(function (root) {
  "use strict";
  const MAX_BYTES = 32 * 1024 * 1024;
  const PAGE_SIZE = 40;
  const PUBLISHED = Object.freeze({
    path: "data/cordis-research-2026-11-09.json", asOf: "2026-11-09", bytes: 977669,
    sha256: "df7d55e6e3e2603e1b1bd38fc0068752388885357deb8442e95b498385b84825"
  });
  const SOURCE_URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-json.zip";
  const CATALOGUE_URL = "https://data.europa.eu/data/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027";
  const LICENCE_URL = "https://eur-lex.europa.eu/eli/dec/2011/833/oj";
  const EU27 = Object.freeze({ AT: "Austria", BE: "Belgium", BG: "Bulgaria", HR: "Croatia", CY: "Cyprus", CZ: "Czechia", DK: "Denmark", EE: "Estonia", FI: "Finland", FR: "France", DE: "Germany", GR: "Greece", HU: "Hungary", IE: "Ireland", IT: "Italy", LV: "Latvia", LT: "Lithuania", LU: "Luxembourg", MT: "Malta", NL: "Netherlands", PL: "Poland", PT: "Portugal", RO: "Romania", SK: "Slovakia", SI: "Slovenia", ES: "Spain", SE: "Sweden" });
  const SCOPE = Object.freeze({
    eu_country_scope: "EU27_PARTICIPANT_LOCATION_NOT_PARENT_OWNERSHIP",
    country_normalization: "SOURCE_EL_NORMALIZED_TO_ISO_GR_WITH_RAW_CODE_PRESERVED",
    commercial_activity_code: "PRC",
    commercial_activity_meaning: "Private for-profit entities, excluding Higher or Secondary Education Establishments",
    organisation_identity: "COMMISSION_PARTICIPANT_IDENTIFIER_CODE_NOT_VERIFIED_LEGAL_IDENTITY",
    active_field_meaning: "FRAMEWORK_PARTNERSHIP_AGREEMENT_ACTIVITY_NOT_UNIVERSAL_PARTICIPATION_STATUS",
    end_of_participation_meaning: "SOURCE_BOOLEAN_NOT_A_DATE",
    date_meaning: "PROJECT_PERIOD_AND_CONTENT_UPDATE_NOT_PUBLICATION_OR_MARKET_ENTRY",
    privacy: "CONTACTS_ADDRESSES_VAT_GEOLOCATION_AND_OBJECTIVES_NOT_EXPORTED",
    json_mapping: "organisation.id=PIC; address.country=country; organizationActivityType code=activity; attributes.type=role; attributes.terminated=endOfParticipation; missing fields remain empty"
  });
  const PROJECT_KEYS = "id project_id source_url source_record_sha256 acronym title project_status_raw project_start_date_raw project_end_date_raw source_content_update_raw project_end_date_is_past unended_canada_and_eu_prc_participants_listed eu_prc_participants canada_participants civilian_scope qualification_status model_eligible expansion_inferred";
  const ORG_KEYS = "source_record_sha256 source_organisation_id name country country_raw activity_type_raw role_raw end_of_participation_raw active_fpa_raw source_content_update_raw";
  function insist(condition, message) { if (!condition) throw new Error(message); }
  function object(value, label) { insist(value !== null && typeof value === "object" && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype, "Invalid " + label); }
  function keys(value, expected, label) {
    object(value, label);
    const allowed = typeof expected === "string" ? expected.split(" ") : expected;
    insist(Object.keys(value).length === allowed.length && Object.keys(value).every(key => allowed.includes(key)), "Unexpected or missing fields in " + label);
  }
  function text(value, max, label, empty = true) {
    insist(typeof value === "string" && value.length <= max && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value) && (empty || value.trim().length > 0), "Invalid " + label);
  }
  function count(value, label, max = 1000000) { insist(Number.isSafeInteger(value) && value >= 0 && value <= max, "Invalid " + label); }
  function hash(value) { insist(typeof value === "string" && /^[a-f0-9]{64}$/.test(value), "Invalid source hash"); }
  function projectId(value) { insist(typeof value === "string" && /^[0-9]{1,12}$/.test(value), "Invalid project ID"); }
  function day(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
    const parsed = new Date(value + "T00:00:00Z");
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }
  function instant(value) {
    insist(typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) && day(value.slice(0, 10)) && Number.isFinite(Date.parse(value)) && Number(value.slice(11, 13)) < 24, "Invalid acquisition timestamp");
    const utcDay = new Date(value).toISOString().slice(0, 10);
    insist(day(utcDay), "Invalid acquisition timestamp");
    return utcDay;
  }
  function array(value, label, max = 50000) { insist(Array.isArray(value) && value.length <= max, "Invalid or excessive " + label); }
  function uniqueIds(value, label) {
    array(value, label, 1000000);
    value.forEach(projectId);
    insist(new Set(value).size === value.length, "Duplicate " + label);
    return new Set(value);
  }
  function validateOrganisation(org, canadian, seen) {
    keys(org, ORG_KEYS, "participant"); hash(org.source_record_sha256);
    insist(!seen.has(org.source_record_sha256), "Duplicate participant source record"); seen.add(org.source_record_sha256);
    if (org.source_organisation_id !== null) text(org.source_organisation_id, 80, "participant identifier", false);
    text(org.name, 1000, "participant name", false); text(org.country, 2, "participant country", false);
    text(org.country_raw, 2, "raw participant country", false);
    insist(org.country === (org.country_raw === "EL" ? "GR" : org.country_raw), "Unsupported country alias or mismatched location");
    text(org.activity_type_raw, 20, "activity code"); text(org.role_raw, 100, "participant role");
    text(org.end_of_participation_raw, 30, "participation flag"); text(org.active_fpa_raw, 30, "FPA activity flag");
    insist(["PRC", "HES", "REC", "PUB", "OTH"].includes(org.activity_type_raw), "Unknown participant activity code");
    insist(["participant", "coordinator", "associatedPartner", "thirdParty"].includes(org.role_raw), "Unknown participant role");
    insist(["true", "false"].includes(org.end_of_participation_raw), "Invalid participation-termination flag");
    text(org.source_content_update_raw, 80, "participant content update");
    insist(canadian ? org.country === "CA" : Object.hasOwn(EU27, org.country) && org.activity_type_raw === "PRC", "Participant outside research scope");
  }
  function validatePayload(payload) {
    keys(payload, "schema_version status mode as_of_date interpretation source scope summary audit projects", "payload");
    insist(payload.schema_version === 1 && payload.mode === "RESEARCH_CO_PARTICIPATION_ONLY", "Unsupported research schema or mode");
    insist(["AVAILABLE", "PARTIAL"].includes(payload.status), "Unsupported source status");
    insist(day(payload.as_of_date), "Invalid as-of date"); text(payload.interpretation, 4000, "interpretation", false);
    const source = payload.source;
    keys(source, "name source_url catalogue_url sha256 bytes retrieved_at file_last_modified catalogue_modified licence_url attribution clock_scope", "source");
    insist(source.source_url === SOURCE_URL && source.catalogue_url === CATALOGUE_URL && source.licence_url === LICENCE_URL, "Unexpected source or licence URL");
    text(source.name, 500, "source name", false); hash(source.sha256); count(source.bytes, "source byte count", 192 * 1024 * 1024); insist(source.bytes > 0, "Empty source archive");
    insist(instant(source.retrieved_at) <= payload.as_of_date, "Acquisition occurred after the requested as-of date");
    for (const key of ["file_last_modified", "catalogue_modified"]) if (source[key] !== null) text(source[key], 100, key, false);
    text(source.attribution, 2000, "attribution", false);
    insist(source.clock_scope === "CURRENT_DOWNLOADED_SNAPSHOT_NOT_FIRST_PUBLICATION_OR_FIRST_DISCOVERY", "Unsupported clock scope");
    keys(payload.scope, Object.keys(SCOPE), "scope");
    for (const key of Object.keys(SCOPE)) insist(payload.scope[key] === SCOPE[key], "Unsupported interpretation scope");

    array(payload.projects, "projects");
    const projectIds = new Set(), euIds = new Set(), caIds = new Set();
    let participationRows = 0;
    const actual = { project_count: payload.projects.length, eu_prc_participation_rows: 0, eu_prc_source_organisation_ids: 0, canada_participation_rows: 0, canada_source_organisation_ids: 0, missing_organisation_id_rows: 0, unended_partner_projects: 0, project_status_counts: Object.create(null), qualified_lead_count: 0 };
    for (const project of payload.projects) {
      const participantHashes = new Set(); // Hierarchical JSON organisations can recur unchanged across projects.
      keys(project, PROJECT_KEYS, "project"); projectId(project.project_id);
      insist(!projectIds.has(project.project_id), "Duplicate project ID"); projectIds.add(project.project_id);
      insist(project.id === "cordis-project:" + project.project_id && project.source_url === "https://cordis.europa.eu/project/id/" + project.project_id, "Invalid exact project URL or identity");
      hash(project.source_record_sha256); text(project.acronym, 500, "acronym"); text(project.title, 4000, "title"); text(project.project_status_raw, 100, "project status");
      for (const key of ["project_start_date_raw", "project_end_date_raw", "source_content_update_raw"]) text(project[key], 80, key);
      const past = day(project.project_end_date_raw) ? project.project_end_date_raw < payload.as_of_date : null;
      insist(project.project_end_date_is_past === past, "Inconsistent project end-date flag");
      insist(project.civilian_scope === "NO_EXPLICIT_MARKER_NOT_VERIFIED" && project.qualification_status === "RESEARCH_ONLY_NOT_QUALIFIED" && project.model_eligible === false && project.expansion_inferred === false, "Project qualification or expansion claim is not allowed");
      for (const [field, canadian, ids, metric] of [["eu_prc_participants", false, euIds, "eu_prc_participation_rows"], ["canada_participants", true, caIds, "canada_participation_rows"]]) {
        array(project[field], field, 10000); insist(project[field].length > 0, "Project lacks required participants");
        for (const org of project[field]) { validateOrganisation(org, canadian, participantHashes); if (org.source_organisation_id === null) actual.missing_organisation_id_rows++; else ids.add(org.source_organisation_id); }
        actual[metric] += project[field].length;
      }
      participationRows += participantHashes.size;
      insist(participationRows <= 250000, "Excessive participation rows");
      const unended = project.eu_prc_participants.some(org => org.end_of_participation_raw.toLowerCase() === "false") && project.canada_participants.some(org => org.end_of_participation_raw.toLowerCase() === "false");
      insist(project.unended_canada_and_eu_prc_participants_listed === unended, "Inconsistent participation flags");
      actual.unended_partner_projects += Number(unended);
      actual.project_status_counts[project.project_status_raw] = (actual.project_status_counts[project.project_status_raw] || 0) + 1;
    }
    actual.eu_prc_source_organisation_ids = euIds.size; actual.canada_source_organisation_ids = caIds.size;
    keys(payload.summary, Object.keys(actual), "summary");
    for (const key of Object.keys(actual).filter(key => key !== "project_status_counts")) insist(payload.summary[key] === actual[key], "Inconsistent summary: " + key);
    keys(payload.summary.project_status_counts, Object.keys(actual.project_status_counts), "project status counts");
    for (const key of Object.keys(actual.project_status_counts)) insist(payload.summary.project_status_counts[key] === actual.project_status_counts[key], "Inconsistent project status count");

    const audit = payload.audit;
    keys(audit, "archive_project_rows archive_organisation_rows valid_project_rows quarantined_project_rows quarantined_canada_projects quarantined_canada_eu_prc_projects coverage canada_projects canada_eu_any_activity_projects canada_eu_prc_projects_before_scope scope_held_projects boundary", "audit");
    for (const key of ["archive_project_rows", "archive_organisation_rows", "valid_project_rows", "canada_projects", "canada_eu_any_activity_projects", "canada_eu_prc_projects_before_scope"]) count(audit[key], key);
    text(audit.boundary, 2000, "audit boundary", false); array(audit.quarantined_project_rows, "quarantined projects", 1000000); array(audit.scope_held_projects, "scope-held projects", 1000000);
    const quarantined = new Set(), held = new Set();
    for (const row of audit.quarantined_project_rows) {
      keys(row, "project_id source_record_number source_record_sha256 column_count reason", "quarantine entry"); projectId(row.project_id); hash(row.source_record_sha256); count(row.source_record_number, "source record number", 1000001); count(row.column_count, "column count");
      insist(row.source_record_number >= 2 && row.reason === "MALFORMED_PROJECT_ROW_WIDTH" && !quarantined.has(row.project_id) && !projectIds.has(row.project_id), "Invalid quarantine identity or reason"); quarantined.add(row.project_id);
    }
    for (const row of audit.scope_held_projects) {
      keys(row, "project_id reason", "scope-held entry"); projectId(row.project_id);
      insist(["EXPLICIT_MILITARY_MARKER", "AMBIGUOUS_CIVILIAN_SCOPE"].includes(row.reason) && !held.has(row.project_id) && !quarantined.has(row.project_id) && !projectIds.has(row.project_id), "Invalid scope-held identity or reason"); held.add(row.project_id);
    }
    const qCanada = uniqueIds(audit.quarantined_canada_projects, "quarantined Canadian project IDs");
    const qBoth = uniqueIds(audit.quarantined_canada_eu_prc_projects, "quarantined candidate project IDs");
    insist([...qCanada].every(id => quarantined.has(id)) && [...qBoth].every(id => qCanada.has(id)), "Invalid quarantine subset");
    insist(audit.archive_project_rows === audit.valid_project_rows + quarantined.size && audit.valid_project_rows >= projectIds.size + held.size && audit.archive_organisation_rows >= participationRows, "Inconsistent archive coverage");
    insist(audit.canada_eu_prc_projects_before_scope === projectIds.size + held.size + qBoth.size && audit.canada_eu_any_activity_projects >= audit.canada_eu_prc_projects_before_scope && audit.canada_projects >= audit.canada_eu_any_activity_projects && audit.canada_projects >= projectIds.size + held.size + qCanada.size && audit.archive_project_rows >= audit.canada_projects, "Inconsistent candidate coverage");
    insist(payload.status === (quarantined.size ? "PARTIAL" : "AVAILABLE") && audit.coverage === (quarantined.size ? "PARTIAL_MALFORMED_PROJECT_ROWS_QUARANTINED" : "ALL_ROWS_PARSED"), "Inconsistent partial coverage status");
    return payload;
  }
  function parse(raw) {
    insist(typeof raw === "string" && new TextEncoder().encode(raw).length <= MAX_BYTES, "Research file exceeds 32 MiB");
    let payload;
    try { payload = JSON.parse(raw); } catch (_) { throw new Error("File is not valid JSON"); }
    return validatePayload(payload);
  }
  function filterProjects(projects, query = "", country = "") {
    insist(typeof query === "string" && typeof country === "string" && (country === "" || Object.hasOwn(EU27, country)), "Invalid review filter");
    const needle = query.trim().toLocaleLowerCase();
    return projects.filter(project => (!country || project.eu_prc_participants.some(org => org.country === country)) && (!needle || [project.project_id, project.acronym, project.title, ...project.eu_prc_participants.map(org => org.name), ...project.canada_participants.map(org => org.name)].some(value => value.toLocaleLowerCase().includes(needle))));
  }
  function pageOf(projects, requestedPage) {
    const pages = Math.max(1, Math.ceil(projects.length / PAGE_SIZE));
    const page = Math.min(Math.max(Number.isSafeInteger(requestedPage) ? requestedPage : 0, 0), pages - 1);
    return { page, pages, items: projects.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), start: projects.length ? page * PAGE_SIZE + 1 : 0, end: Math.min(projects.length, (page + 1) * PAGE_SIZE) };
  }
  async function readPublished(fetcher, cryptoApi) {
    insist(typeof fetcher === "function" && cryptoApi && cryptoApi.subtle, "Published snapshot loading is unavailable in this browser");
    const response = await fetcher(PUBLISHED.path, { credentials: "omit", redirect: "error", referrerPolicy: "no-referrer" });
    insist(response.ok && !response.redirected, "Published snapshot request failed");
    insist(/^application\/json(?:;|$)/i.test(response.headers.get("content-type") || ""), "Published snapshot is not JSON");
    insist(response.body && typeof response.body.getReader === "function", "Published snapshot body is unavailable");
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        insist(size <= PUBLISHED.bytes, "Published snapshot exceeds its reviewed size");
        chunks.push(value);
      }
    } catch (error) { try { await reader.cancel(); } catch (_) { /* Preserve the original validation error. */ } throw error; }
    finally { reader.releaseLock(); }
    insist(size === PUBLISHED.bytes, "Published snapshot size does not match the reviewed file");
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const digest = Array.from(new Uint8Array(await cryptoApi.subtle.digest("SHA-256", bytes)), n => n.toString(16).padStart(2, "0")).join("");
    insist(digest === PUBLISHED.sha256, "Published snapshot checksum does not match the reviewed file");
    const payload = parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    insist(payload.as_of_date === PUBLISHED.asOf, "Published snapshot as-of date changed");
    return payload;
  }
  function createFileLoader(onChange, services = {}) {
    let generation = 0;
    return {
      clear() { generation++; onChange({ status: "empty" }); },
      async loadPublished() {
        const selected = ++generation;
        onChange({ status: "loading", published: true });
        try {
          const payload = await readPublished(services.fetcher, services.cryptoApi);
          if (selected !== generation) return;
          onChange({ status: "ready", published: true, payload, file: { name: PUBLISHED.path, modified: null, published: true } });
        } catch (error) {
          if (selected === generation) onChange({ status: "error", published: true, message: error instanceof Error ? error.message : "Published snapshot could not be read" });
        }
      },
      async load(file) {
        if (!file) return; // A cancelled picker keeps the currently reviewed file.
        const selected = ++generation;
        onChange({ status: "loading" }); // Clear old results before the asynchronous read.
        try {
          insist(Number.isSafeInteger(file.size) && file.size > 0 && file.size <= MAX_BYTES, "Choose a nonempty research JSON no larger than 32 MiB");
          const raw = await file.text();
          if (selected !== generation) return;
          const payload = parse(raw);
          const modified = Number.isFinite(file.lastModified) && file.lastModified > 0 && Number.isFinite(new Date(file.lastModified).getTime()) ? new Date(file.lastModified).toISOString() : null;
          onChange({ status: "ready", payload, file: { name: String(file.name), modified } });
        } catch (error) {
          if (selected === generation) onChange({ status: "error", message: error instanceof Error ? error.message : "File could not be read" });
        }
      }
    };
  }

  function mount(document) {
    const byId = id => document.getElementById(id);
    const node = (tag, value, className) => { const element = document.createElement(tag); if (value !== undefined) element.textContent = value; if (className) element.className = className; return element; };
    const pair = (list, label, value) => list.append(node("dt", label), node("dd", value || "Not supplied"));
    let payload = null, page = 0;
    const participants = (title, records) => {
      const section = node("section"); section.append(node("h4", title));
      const list = node("ul");
      for (const org of records) {
        const item = node("li"); item.append(node("strong", org.name + " · " + (org.country === "CA" ? "Canada (CA)" : EU27[org.country] + " (" + org.country + ")") + (org.country_raw !== org.country ? " · source code " + org.country_raw : "")));
        item.append(node("div", "Source role: " + (org.role_raw || "not supplied") + " · Source ID: " + (org.source_organisation_id || "not supplied"), "muted"));
        item.append(node("div", "Source content update: " + (org.source_content_update_raw || "not supplied") + " · End-of-participation flag: " + (org.end_of_participation_raw || "not supplied"), "muted"));
        list.append(item);
      }
      section.append(list); return section;
    };
    const renderProjects = () => {
      if (!payload) return;
      const matches = filterProjects(payload.projects, byId("search").value, byId("country").value), current = pageOf(matches, page); page = current.page;
      const container = byId("projects"); container.replaceChildren();
      byId("results-status").textContent = "Showing " + current.start + "–" + current.end + " of " + matches.length + " matching projects (" + payload.projects.length + " in the file).";
      if (!matches.length) container.append(node("p", payload.projects.length ? "No projects match these filters. Try a different search or location." : "The loaded file contains no included projects. This does not establish absence of research activity."));
      for (const project of current.items) {
        const card = node("article", undefined, "project"); card.append(node("span", "Research only · unqualified", "badge"));
        card.append(node("span", "Project " + project.project_id, "badge"));
        card.append(node("h3", (project.acronym ? project.acronym + " · " : "") + (project.title || "Untitled source record")));
        card.append(node("p", "Source status: " + (project.project_status_raw || "not supplied") + " · Project period: " + (project.project_start_date_raw || "not supplied") + " to " + (project.project_end_date_raw || "not supplied")));
        card.append(node("p", "Source project content update: " + (project.source_content_update_raw || "not supplied") + ". This is not a publication date.", "muted"));
        if (project.project_end_date_is_past) card.append(node("p", "The listed project end date is before the file's as-of date. Do not infer a current relationship.", "muted"));
        const link = node("a", "Open this project on CORDIS ↗"); link.href = project.source_url; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link);
        const details = node("details"); details.append(node("summary", project.eu_prc_participants.length + " EU-27 PRC and " + project.canada_participants.length + " Canadian participation rows"));
        const columns = node("div", undefined, "participants"); columns.append(participants("EU-27 PRC participant locations", project.eu_prc_participants), participants("Canadian participant locations", project.canada_participants));
        details.append(columns, node("p", "Listed on the same consortium project, not a verified bilateral partnership. End-of-participation is a source boolean, not a date. FPA activity is not a universal participation-status flag.", "muted"));
        card.append(details); container.append(card);
      }
      byId("previous-page").disabled = page === 0; byId("next-page").disabled = page + 1 >= current.pages;
      byId("page-status").textContent = "Page " + (page + 1) + " of " + current.pages;
    };
    const renderSnapshot = file => {
      const summary = byId("summary"); summary.replaceChildren();
      for (const [label, value] of [["Included projects", payload.summary.project_count], ["EU-27 PRC participation rows", payload.summary.eu_prc_participation_rows], ["Canadian participation rows", payload.summary.canada_participation_rows], ["Distinct EU-27 source IDs", payload.summary.eu_prc_source_organisation_ids], ["Distinct Canadian source IDs", payload.summary.canada_source_organisation_ids], ["Qualified leads", 0]]) {
        const metric = node("div", undefined, "metric"); metric.append(node("strong", value.toLocaleString()), node("span", label)); summary.append(metric);
      }
      const audit = payload.audit, warning = byId("partial-warning"); warning.hidden = payload.status !== "PARTIAL";
      warning.textContent = payload.status === "PARTIAL" ? "Partial coverage: " + audit.quarantined_project_rows.length + " malformed project rows were quarantined, including " + audit.quarantined_canada_eu_prc_projects.length + " Canadian / EU-27 PRC candidate projects. They are excluded below. Missing rows are not evidence of absence." : "";
      byId("coverage").textContent = "Archive parse: " + audit.valid_project_rows.toLocaleString() + " valid project rows / " + audit.archive_project_rows.toLocaleString() + " total; " + audit.archive_organisation_rows.toLocaleString() + " organisation rows. " + audit.scope_held_projects.length + " candidate projects held by conservative scope screening. " + payload.summary.missing_organisation_id_rows + " included participation rows lack a source organisation ID.";
      const clocks = byId("clocks"); clocks.replaceChildren();
      for (const [label, value] of [["Source", payload.source.name], ["Source archive URL", payload.source.source_url], ["Source catalogue modified (raw)", payload.source.catalogue_modified], ["Source archive Last-Modified (raw)", payload.source.file_last_modified], ["Acquisition retrieved at", payload.source.retrieved_at], ["Calculation as-of date", payload.as_of_date], [file.published ? "Published snapshot file" : "Local review filename", file.name], ["Local file modified (device metadata)", file.published ? "Not used for the published snapshot" : file.modified], ["Source archive SHA-256", payload.source.sha256], ["Source archive bytes", String(payload.source.bytes)], ["Reuse licence", payload.source.licence_url]]) pair(clocks, label, value);
      byId("attribution").textContent = payload.source.attribution + (file.published ? " Published derivative bytes match the reviewed snapshot checksum. The original source archive is not fetched or independently verified by this page." : " The archive hash is supplied by the local derivative, not independently checked by this page.") + " No clock here establishes first publication or current commercial activity.";
      const country = byId("country"); country.replaceChildren(); const all = node("option", "All included EU-27 locations"); all.value = ""; country.append(all);
      const countries = new Set(payload.projects.flatMap(project => project.eu_prc_participants.map(org => org.country)));
      for (const code of [...countries].sort((a, b) => EU27[a].localeCompare(EU27[b]))) { const option = node("option", EU27[code] + " (" + code + ")"); option.value = code; country.append(option); }
      byId("search").value = ""; country.value = ""; page = 0; byId("review").hidden = false; renderProjects();
    };
    const loader = createFileLoader(state => {
      payload = null; byId("review").hidden = true; byId("projects").replaceChildren(); byId("summary").replaceChildren(); byId("clocks").replaceChildren();
      byId("clear-file").disabled = state.status === "empty";
      if (state.status === "ready") { payload = state.payload; byId("load-status").textContent = state.published ? "Published snapshot as of 9 November 2026. Reviewed checksum, structure and counts validated. This is not a live feed." : "Local file: " + state.file.name + ". Structure and counts validated. This is not the published snapshot; source authenticity is not verified by this page."; renderSnapshot(state.file); }
      else byId("load-status").textContent = state.status === "loading" ? (state.published ? "Loading and validating the published snapshot. Previous results have been cleared." : "Reading and validating the local file. Previous results have been cleared.") : state.status === "error" ? (state.published ? "Published snapshot unavailable: " : "File rejected: ") + state.message + ". Counts are unavailable, not zero. No records are shown." : "No file loaded. Counts are unavailable, not zero.";
    }, { fetcher: root.fetch && root.fetch.bind(root), cryptoApi: root.crypto });
    byId("reload-published").addEventListener("click", () => loader.loadPublished());
    byId("research-file").addEventListener("change", event => { const file = event.target.files[0]; if (file) { loader.load(file); event.target.value = ""; } });
    byId("clear-file").addEventListener("click", () => { byId("research-file").value = ""; loader.clear(); });
    byId("search").addEventListener("input", () => { page = 0; renderProjects(); });
    byId("country").addEventListener("change", () => { page = 0; renderProjects(); });
    byId("previous-page").addEventListener("click", () => { page--; renderProjects(); });
    byId("next-page").addEventListener("click", () => { page++; renderProjects(); });
    loader.loadPublished();
  }
  const api = Object.freeze({ MAX_BYTES, PAGE_SIZE, PUBLISHED, readPublished, SOURCE_URL, CATALOGUE_URL, LICENCE_URL, SCOPE, validatePayload, parse, filterProjects, pageOf, createFileLoader });
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else if (root.document) mount(root.document);
})(typeof globalThis !== "undefined" ? globalThis : this);
