/* Browser-local analyst work. Source evidence is read-only and stored separately. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ABWorkspace = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const KEY = "atlanticbridge.analyst-workspace.v1";
  const LEGACY_KEY = "atlanticbridge.watched-companies.v1";
  const STATUSES = {new:"To review",researching:"Researching",contacted:"Contacted",follow_up:"Follow up",closed:"Closed"};
  const MAX_ENTRIES = 500, MAX_BYTES = 2 * 1024 * 1024, DAY = 86400000;
  const clone = x => JSON.parse(JSON.stringify(x));
  const plain = x => x && typeof x === "object" && !Array.isArray(x);
  const idValid = id => typeof id === "string" && /^[a-f0-9]{64}$/.test(id);
  function dateValid(value) {
    return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
      Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
  }
  function utcToday(now = Date.now()) { return new Date(now).toISOString().slice(0,10); }
  function signalAge(signal, now = Date.now()) {
    const value = signal?.publicly_available_date;
    return dateValid(value) ? Math.floor((Date.parse(utcToday(now)) - Date.parse(value)) / DAY) : null;
  }
  function feedHealth(payload, now = Date.now()) {
    if (payload?.status !== "ACTIVE") return {state:"unavailable", ageHours:null};
    // Generation is not a source check. Never use generated_at to hide old observations.
    const observed = Date.parse(payload.source?.observed_at || "");
    if (!Number.isFinite(observed) || observed > now + 300000) return {state:"unverified", ageHours:null};
    const ageHours = Math.max(0,(now - observed) / 3600000);
    return {state:ageHours > 48 ? "stale" : "recent", ageHours};
  }
  function money(value, currency) {
    const text = String(value ?? "").trim();
    if (!text) return "Amount not stated";
    if (!/^-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(text)) return `${text}${currency ? " " + currency : ""} (as published)`;
    const amount = Number(text.replace(/,/g,""));
    if (!Number.isFinite(amount)) return "Amount not interpretable";
    if (!currency) return `${text} (currency not stated)`;
    try { return new Intl.NumberFormat("en-CA",{style:"currency",currency,maximumFractionDigits:2}).format(amount); }
    catch (_) { return `${text} ${currency} (as published)`; }
  }
  function groupCompanies(payload) {
    const groups = new Map();
    if (payload?.status !== "ACTIVE") return groups;
    for (const signal of payload.signals || []) {
      if (!idValid(signal.company_id)) continue;
      let company = groups.get(signal.company_id);
      if (!company) {
        company = {id:signal.company_id,company_name:signal.company_name,country:signal.country,signals:[]};
        groups.set(company.id,company);
      }
      company.signals.push(signal);
    }
    for (const company of groups.values()) {
      company.signals.sort((a,b) => String(b.publicly_available_date || "").localeCompare(String(a.publicly_available_date || "")) || String(a.id).localeCompare(String(b.id)));
      company.latest_public_date = company.signals[0]?.publicly_available_date || "";
    }
    return groups;
  }
  function blankEntry(id, company = null, payload = null, now = new Date().toISOString()) {
    return {id,company_name:company?.company_name || "",country:company?.country || "",status:"new",notes:"",next_action:"",due_date:"",
      updated_at:now,source_url:payload?.source?.source_url || "",source_sha256:payload?.source?.source_sha256 || "",
      snapshot_observed_at:payload?.source?.observed_at || "",latest_public_date:company?.latest_public_date || ""};
  }
  function validateEntry(item) {
    if (!plain(item) || !idValid(item.id) || !Object.hasOwn(STATUSES,item.status)) throw new Error("Invalid worklist identity or status.");
    const limits = {company_name:1000,country:100,notes:4000,next_action:500,due_date:10,updated_at:40,source_url:2000,source_sha256:64,snapshot_observed_at:40,latest_public_date:10};
    const result = {id:item.id,status:item.status};
    for (const [key,limit] of Object.entries(limits)) {
      if (typeof item[key] !== "string" || item[key].length > limit) throw new Error(`Invalid or oversized ${key}.`);
      result[key] = item[key];
    }
    for (const key of ["due_date","latest_public_date"]) if (result[key] && !dateValid(result[key])) throw new Error(`Invalid ${key}.`);
    for (const key of ["updated_at","snapshot_observed_at"]) if (result[key] && !Number.isFinite(Date.parse(result[key]))) throw new Error(`Invalid ${key}.`);
    if (!result.updated_at) throw new Error("Missing update timestamp.");
    if (result.source_url && !/^https?:\/\//i.test(result.source_url)) throw new Error("Invalid source URL.");
    if (result.source_sha256 && !/^[a-f0-9]{64}$/.test(result.source_sha256)) throw new Error("Invalid source hash.");
    return result;
  }
  function validateData(value) {
    if (!plain(value) || value.schema_version !== 1 || !Array.isArray(value.entries) || value.entries.length > MAX_ENTRIES) throw new Error("Unsupported or oversized workspace.");
    const entries = value.entries.map(validateEntry);
    if (new Set(entries.map(e=>e.id)).size !== entries.length) throw new Error("Duplicate workspace identities.");
    return {schema_version:1,entries};
  }
  class Store {
    constructor(storage) { this.storage=storage;this.raw=null;this.data={schema_version:1,entries:[]};this.loaded=false; }
    load(companies = new Map(), payload = null) {
      const raw = this.storage.getItem(KEY);
      let data;
      if (raw !== null) {
        if (raw.length > MAX_BYTES) throw new Error("Workspace is too large; existing data was not changed.");
        data = validateData(JSON.parse(raw));
      } else {
        const legacyRaw = this.storage.getItem(LEGACY_KEY);
        const legacy = legacyRaw === null ? [] : JSON.parse(legacyRaw);
        if (!Array.isArray(legacy) || legacy.length > MAX_ENTRIES || !legacy.every(idValid)) throw new Error("Existing watchlist is invalid; it was not overwritten.");
        data = {schema_version:1,entries:[...new Set(legacy)].map(id=>blankEntry(id,companies.get(id),payload))};
      }
      this.raw=raw;this.data=data;this.loaded=true;return clone(data);
    }
    entries() { return clone(this.data.entries); }
    get(id) { const entry=this.data.entries.find(e=>e.id===id);return entry?clone(entry):null; }
    write(entries) {
      if (!this.loaded) throw new Error("Workspace is not available for editing.");
      const data = validateData({schema_version:1,entries});
      const raw = JSON.stringify(data);
      if (raw.length > MAX_BYTES) throw new Error("Workspace storage limit reached. Export a backup before reducing it.");
      if (this.storage.getItem(KEY) !== this.raw) throw new Error("Workspace changed in another tab. Your draft is retained; reload the company to compare before saving.");
      // setItem is the only mutation: failed writes leave the previous in-memory and stored value untouched.
      this.storage.setItem(KEY,raw);this.raw=raw;this.data=data;return clone(data);
    }
    put(entry) { const valid=validateEntry(entry);const entries=this.entries().filter(e=>e.id!==valid.id);entries.push(valid);return this.write(entries); }
    remove(id) { return this.write(this.entries().filter(e=>e.id!==id)); }
    mergeNew(backup) {
      const incoming = validateBackup(backup);
      const current = this.entries();const ids=new Set(current.map(e=>e.id));const added=incoming.entries.filter(e=>!ids.has(e.id));
      this.write([...current,...added]);return {added:added.length,kept:incoming.entries.length-added.length};
    }
    backup() { return {format:"atlanticbridge-analyst-workspace",schema_version:1,exported_at:new Date().toISOString(),entries:this.entries()}; }
  }
  function validateBackup(value) {
    if (typeof value === "string") {
      if (value.length > MAX_BYTES) throw new Error("Backup exceeds the 2 MB limit.");
      value=JSON.parse(value);
    }
    if (!plain(value) || value.format !== "atlanticbridge-analyst-workspace") throw new Error("Not an AtlanticBridge workspace backup.");
    return validateData(value);
  }
  function csvCell(value) {
    let text=String(value ?? "");
    // Quoting alone does not prevent spreadsheet formulas. Neutralize leading formula/control characters.
    if (/^[\s\uFEFF]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text="'"+text;
    return '"'+text.replace(/"/g,'""')+'"';
  }
  function worklistCSV(entries) {
    const keys=["company_name","country","status","due_date","next_action","notes","latest_public_date","snapshot_observed_at","source_url","source_sha256","id","updated_at"];
    return [keys,...entries.map(e=>keys.map(k=>e[k]))].map(row=>row.map(csvCell).join(",")).join("\r\n")+"\r\n";
  }
  return {KEY,LEGACY_KEY,STATUSES,MAX_BYTES,Store,blankEntry,validateEntry,validateBackup,worklistCSV,csvCell,utcToday,dateValid,signalAge,feedHealth,money,groupCompanies};
});
