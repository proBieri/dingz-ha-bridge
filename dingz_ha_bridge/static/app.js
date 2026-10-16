"use strict";

// Relative URLs so the page also works below the HA ingress path.
const headers = { "Content-Type": "application/json", "X-Dingz-UI": "1" };
const $ = (id) => document.getElementById(id);
const POLL_MS = 1000;
const QUALITY_CLASS = { excellent: "ok", good: "ok", fair: "warn", poor: "bad" };

// UI texts. German if the browser prefers German, English otherwise.
const I18N = {
  en: {
    rescan: "Rescan", subnetPlaceholder: "Optional subnet, e.g. 192.168.1.0/24",
    colName: "Name", colModel: "Model", colMqttId: "MQTT ID", colWifi: "WLAN", colHa: "In HA",
    colSources: "Found via", noDevices: "No dingz found.",
    setBroker: "Set MQTT broker",
    setBrokerHint: "Address as the dingz reaches the broker. Ideally a dedicated broker user for the dingz.",
    user: "User", password: "Password", mqttEnabled: "MQTT enabled", apply: "Apply",
    scanning: "Scanning …", lastScan: "Last scan {time}",
    ago_s: "{n} s ago", ago_min: "{n} min ago", ago_h: "{n} h ago",
    lastMessage: "Last message: {topic}", noMessage: "no message received yet", bridgeOff: "bridge not running",
    yes: "yes", no: "no", error: "Error",
    openWebUi: "Open web interface ↗",
    fIp: "IP", fMac: "MAC", fMqttId: "MQTT ID", fRoom: "Room", fModel: "Model", fFirmware: "Firmware",
    fHardware: "Hardware", fPir: "PIR", fProtected: "Locked", fMqttEnabled: "MQTT enabled",
    fBroker: "MQTT broker", fOutput: "Output {n}", fWifi: "WLAN signal",
    inactive: " (inactive)", on: ", on",
    measuring: "measuring …", notFound: "not found", moreAps: "other APs: {list} dBm",
    measuredAt: "measured {time}", measureAgain: "measure again",
    wifiTip: "Strongest access point of the own SSID according to the dingz WLAN scan",
    q_excellent: "excellent", q_good: "good", q_fair: "fair", q_poor: "poor",
    confirmSet: "Set the MQTT broker of {host} to {target}?", applying: "Applying …",
    r_applied: "MQTT settings applied", r_rejected: "The dingz did not take the new MQTT settings",
    updateAvailable: "Update available: v{version} ↗", upToDate: "up to date", checkedAt: "checked {time}",
    updateFailed: "update check failed",
    u_disabled: "update check disabled", u_unreachable: "GitHub not reachable",
    u_not_public: "update check: repository not public or not found", u_no_release: "no release yet",
  },
  de: {
    rescan: "Neu scannen", subnetPlaceholder: "Subnetz optional, z. B. 192.168.1.0/24",
    colName: "Name", colModel: "Modell", colMqttId: "MQTT-ID", colWifi: "WLAN", colHa: "In HA",
    colSources: "Gefunden über", noDevices: "Keine dingz gefunden.",
    setBroker: "MQTT-Broker setzen",
    setBrokerHint: "Adresse so, wie der dingz den Broker erreicht. Am besten ein eigener Broker-Benutzer für die dingz.",
    user: "Benutzer", password: "Passwort", mqttEnabled: "MQTT aktiv", apply: "Übernehmen",
    scanning: "Scan läuft …", lastScan: "Letzter Scan {time}",
    ago_s: "vor {n} s", ago_min: "vor {n} min", ago_h: "vor {n} h",
    lastMessage: "Letzte Nachricht: {topic}", noMessage: "noch keine Nachricht empfangen", bridgeOff: "Bridge läuft nicht",
    yes: "ja", no: "nein", error: "Fehler",
    openWebUi: "Webinterface öffnen ↗",
    fIp: "IP", fMac: "MAC", fMqttId: "MQTT-ID", fRoom: "Raum", fModel: "Modell", fFirmware: "Firmware",
    fHardware: "Hardware", fPir: "PIR", fProtected: "Gesperrt", fMqttEnabled: "MQTT aktiv",
    fBroker: "MQTT-Broker", fOutput: "Ausgang {n}", fWifi: "WLAN-Signal",
    inactive: " (inaktiv)", on: ", an",
    measuring: "wird gemessen …", notFound: "nicht gefunden", moreAps: "weitere APs: {list} dBm",
    measuredAt: "gemessen {time}", measureAgain: "neu messen",
    wifiTip: "Stärkster Access Point der eigenen SSID laut WLAN-Scan des dingz",
    q_excellent: "sehr gut", q_good: "gut", q_fair: "mässig", q_poor: "schlecht",
    confirmSet: "MQTT-Broker von {host} auf {target} setzen?", applying: "Wird übernommen …",
    r_applied: "MQTT-Einstellungen übernommen", r_rejected: "Der dingz hat die neuen MQTT-Einstellungen nicht übernommen",
    updateAvailable: "Update verfügbar: v{version} ↗", upToDate: "aktuell", checkedAt: "geprüft {time}",
    updateFailed: "Update-Check fehlgeschlagen",
    u_disabled: "Update-Check deaktiviert", u_unreachable: "GitHub nicht erreichbar",
    u_not_public: "Update-Check: Repository nicht öffentlich oder nicht gefunden", u_no_release: "noch kein Release",
  },
};
// ?lang=de|en wins; otherwise the first supported language in the browser's preference
// order; English as fallback.
const LANG = [
  new URLSearchParams(location.search).get("lang") || "",
  ...(navigator.languages || [navigator.language || "en"]),
]
  .map((l) => l.toLowerCase().slice(0, 2))
  .find((l) => l in I18N) || "en";

function t(key, vars = {}) {
  const text = I18N[LANG][key] ?? I18N.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? ""));
}

function translatePage() {
  document.documentElement.lang = LANG;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-placeholder]")) el.placeholder = t(el.dataset.i18nPlaceholder);
}

let devices = [];
let selected = null;
let defaultBroker = "";
let clockOffset = 0; // server time - browser time, for "x s ago"
const rows = new Map(); // host -> { tr, cells, lastMessage }
const wifi = new Map(); // host -> signal or { pending } / { error }
const wifiQueue = [];
let wifiRunning = false;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* plain text error */ }
  if (!response.ok && !(data && ("ok" in data || "error" in data))) {
    throw new Error(text || response.statusText);
  }
  return data;
}

function showError(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

function setCell(td, text, className = "") {
  td.textContent = text ?? "–";
  td.className = className;
}

// Link to the device's own web interface; opens in a new tab.
function deviceLink(host, text) {
  const a = document.createElement("a");
  a.href = `http://${host}/`;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = text;
  a.addEventListener("click", (event) => event.stopPropagation());
  return a;
}

function ago(seconds) {
  if (seconds < 60) return t("ago_s", { n: Math.max(0, Math.round(seconds)) });
  if (seconds < 3600) return t("ago_min", { n: Math.round(seconds / 60) });
  return t("ago_h", { n: Math.round(seconds / 3600) });
}

function createRow(d) {
  const tr = document.createElement("tr");
  const names = ["name", "ip", "model", "fw", "mqttId", "mqtt", "wifi", "ha", "sources"];
  // data-label drives the column name shown next to each value in the mobile card layout.
  const labels = {
    name: t("colName"), ip: "IP", model: t("colModel"), fw: "FW", mqttId: t("colMqttId"),
    mqtt: "MQTT", wifi: t("colWifi"), ha: t("colHa"), sources: t("colSources"),
  };
  const cells = Object.fromEntries(names.map((n) => {
    const td = document.createElement("td");
    td.dataset.label = labels[n];
    return [n, td];
  }));
  cells.ip.append(deviceLink(d.host, d.host));

  // MQTT cell: activity dot + state + time since the last message.
  const dot = document.createElement("span");
  dot.className = "dot";
  const label = document.createElement("span");
  const since = document.createElement("span");
  since.className = "muted since";
  cells.mqtt.append(dot, label, since);

  tr.append(...names.map((n) => cells[n]));
  tr.addEventListener("click", () => select(d.host));
  return { tr, cells, dot, label, since, lastMessage: null };
}

function updateRow(row, d) {
  const { cells } = row;
  setCell(cells.name, d.name || d.mqtt_id || d.host);
  setCell(cells.model, d.model);
  setCell(cells.fw, d.fw_version);
  setCell(cells.mqttId, d.mqtt_id);
  setCell(cells.sources, d.sources.join(", "));
  row.tr.classList.toggle("selected", selected === d.host);

  if (d.mqtt_online === null) {
    row.label.textContent = "–";
    row.label.className = "";
  } else {
    row.label.textContent = d.mqtt_online ? "online" : "offline";
    row.label.className = d.mqtt_online ? "ok" : "bad";
  }

  const last = d.bridge && d.bridge.last_message;
  if (last) {
    if (row.lastMessage !== null && last > row.lastMessage) flash(row.dot);
    row.lastMessage = last;
    row.since.textContent = " · " + ago(Date.now() / 1000 + clockOffset - last);
    row.dot.title = t("lastMessage", { topic: d.bridge.last_topic });
    row.dot.classList.add("seen");
  } else {
    row.since.textContent = "";
    row.dot.title = d.bridge ? t("noMessage") : t("bridgeOff");
  }

  if (d.bridge === null) setCell(cells.ha, "–");
  else setCell(cells.ha, d.bridge.published ? t("yes") : t("no"), d.bridge.published ? "ok" : "bad");

  renderWifiCell(cells.wifi, wifi.get(d.host));
}

function flash(dot) {
  dot.classList.remove("flash");
  void dot.offsetWidth; // restart the animation
  dot.classList.add("flash");
}

function renderWifiCell(td, w) {
  if (!w || w.pending) return setCell(td, "…", "muted");
  if (w.error) return setCell(td, t("error"), "bad");
  if (w.rssi === null) return setCell(td, "–", "muted");
  setCell(td, `${w.rssi} dBm`, QUALITY_CLASS[w.quality] || "");
  td.title = `${w.percent} %, ${t("q_" + w.quality)} · ${w.ssid}`;
}

function render(data) {
  devices = data.devices;
  defaultBroker = data.default_broker || "";
  clockOffset = data.now - Date.now() / 1000;
  $("version").textContent = "v" + data.version;
  $("scan-info").textContent = data.scanning
    ? t("scanning")
    : data.last_scan ? t("lastScan", { time: new Date(data.last_scan * 1000).toLocaleTimeString() }) : "";

  const hosts = devices.map((d) => d.host);
  const sameList = hosts.length === rows.size && hosts.every((h) => rows.has(h));
  if (!sameList) {
    const body = $("devices");
    body.replaceChildren();
    for (const d of devices) {
      const row = rows.get(d.host) || createRow(d);
      rows.set(d.host, row);
      body.append(row.tr);
    }
    for (const host of [...rows.keys()]) if (!hosts.includes(host)) rows.delete(host);
  }
  for (const d of devices) {
    updateRow(rows.get(d.host), d);
    if (!wifi.has(d.host)) queueWifi(d.host);
  }
  $("empty").hidden = devices.length > 0 || data.scanning;
}

// WLAN measurements run one after another; the server caches them for 5 minutes.
function queueWifi(host, refresh = false) {
  wifi.set(host, { pending: true });
  wifiQueue.push({ host, refresh });
  runWifiQueue();
}

async function runWifiQueue() {
  if (wifiRunning) return;
  wifiRunning = true;
  while (wifiQueue.length) {
    const { host, refresh } = wifiQueue.shift();
    let result;
    try {
      result = await api(`api/devices/${encodeURIComponent(host)}/wifi${refresh ? "?refresh=1" : ""}`);
    } catch (err) {
      result = { error: err.message };
    }
    wifi.set(host, result);
    const row = rows.get(host);
    if (row) renderWifiCell(row.cells.wifi, result);
    if (selected === host) renderWifiDetail(host);
  }
  wifiRunning = false;
}

let openedFromHash = false;

async function poll() {
  try {
    render(await api("api/devices"));
    showError("");
    // #<ip> in the URL opens that device's details once it is listed.
    const wanted = decodeURIComponent(location.hash.slice(1));
    if (!openedFromHash && wanted && rows.has(wanted)) {
      openedFromHash = true;
      select(wanted);
    }
  } catch (err) {
    showError(err.message);
  }
  setTimeout(poll, POLL_MS);
}

async function rescan() {
  $("scan").disabled = true;
  showError("");
  $("scan-info").textContent = t("scanning");
  try {
    render(await api("api/scan", { method: "POST", body: JSON.stringify({ subnet: $("subnet").value.trim() }) }));
  } catch (err) {
    showError(err.message);
  } finally {
    $("scan").disabled = false;
  }
}

async function select(host) {
  selected = host;
  const device = devices.find((d) => d.host === host);
  $("detail").hidden = false;
  $("detail-title").textContent = (device && device.name) || host;
  $("detail-link").replaceChildren(deviceLink(host, t("openWebUi")));
  $("mqtt-result").textContent = "";
  const form = $("mqtt-form");
  form.broker.value = defaultBroker;
  form.password.value = "";
  for (const [h, row] of rows) row.tr.classList.toggle("selected", h === host);

  const dl = $("detail-status");
  dl.replaceChildren();
  try {
    const status = await api(`api/devices/${encodeURIComponent(host)}/status`);
    if (selected !== host) return;
    const items = [
      [t("fIp"), status.host], [t("fMac"), status.mac], [t("fMqttId"), status.mqtt_id], [t("fRoom"), status.room],
      [t("fModel"), status.model], [t("fFirmware"), status.fw_version], [t("fHardware"), status.hw_version],
      [t("fPir"), status.has_pir], [t("fProtected"), status.protected],
      [t("fMqttEnabled"), status.mqtt_enabled], [t("fBroker"), status.mqtt_uri],
      ...status.outputs.map((o) => [
        t("fOutput", { n: o.ph_out_id }),
        `${o.type}${o.enable ? "" : t("inactive")}${o.on ? t("on") : ""}`,
      ]),
      ...status.errors.map((e) => [t("error"), e]),
    ];
    for (const [key, value] of items) {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = key;
      dd.textContent = value === null || value === undefined ? "–" : value === true ? t("yes") : value === false ? t("no") : value;
      dl.append(dt, dd);
    }
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = t("fWifi");
    dd.id = "detail-wifi";
    dl.append(dt, dd);
    renderWifiDetail(host);
    form.enable.checked = status.mqtt_enabled !== false;
  } catch (err) {
    showError(err.message);
  }
}

function renderWifiDetail(host) {
  const dd = $("detail-wifi");
  if (!dd) return;
  const w = wifi.get(host);
  dd.replaceChildren();
  dd.className = "";
  if (!w || w.pending) {
    dd.textContent = t("measuring");
    dd.className = "muted";
    return;
  }
  const text = document.createElement("span");
  if (w.error || w.rssi === null) {
    text.textContent = w.error || t("notFound");
  } else {
    const others = w.access_points.length > 1 ? " · " + t("moreAps", { list: w.access_points.slice(1).join(", ") }) : "";
    const when = w.measured_at ? " · " + t("measuredAt", { time: new Date(w.measured_at * 1000).toLocaleTimeString() }) : "";
    text.textContent = `${w.rssi} dBm (${w.percent} %, ${t("q_" + w.quality)}) · ${w.ssid}${others}${when}`;
    text.title = t("wifiTip");
    text.className = QUALITY_CLASS[w.quality] || "";
  }
  const again = document.createElement("button");
  again.type = "button";
  again.className = "link";
  again.textContent = t("measureAgain");
  again.addEventListener("click", () => {
    queueWifi(host, true);
    renderWifiDetail(host);
  });
  dd.append(text, " ", again);
}

$("mqtt-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const target = `${form.broker.value}:${form.port.value || 1883}`;
  if (!confirm(t("confirmSet", { host: selected, target }))) return;
  const result = $("mqtt-result");
  result.className = "";
  result.textContent = t("applying");
  try {
    const data = await api(`api/devices/${encodeURIComponent(selected)}/mqtt`, {
      method: "POST",
      body: JSON.stringify({
        broker: form.broker.value.trim(),
        port: Number(form.port.value || 1883),
        username: form.username.value,
        password: form.password.value,
        enable: form.enable.checked,
      }),
    });
    result.className = data.ok ? "ok" : "bad";
    const message = data.code ? t("r_" + data.code) : data.message;
    result.textContent = message + (data.uri ? ` (${data.uri})` : "");
    form.password.value = "";
    if (data.ok) select(selected);
  } catch (err) {
    result.className = "bad";
    result.textContent = err.message;
  }
});

// Version and update check (server asks GitHub, cached for 6 h).
async function loadVersion() {
  const el = $("update");
  try {
    const v = await api("api/version");
    $("repo-link").href = v.repo_url;
    el.replaceChildren();
    if (v.update_available) {
      const a = document.createElement("a");
      a.href = v.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = t("updateAvailable", { version: v.latest });
      a.className = "update";
      el.append(a);
    } else if (v.latest) {
      el.textContent = t("upToDate");
      el.className = "ok";
    } else {
      el.textContent = v.error_code ? t("u_" + v.error_code) : v.error || "";
      el.className = "muted";
    }
    el.title = v.checked_at ? t("checkedAt", { time: new Date(v.checked_at * 1000).toLocaleString() }) : "";
  } catch (err) {
    el.textContent = t("updateFailed");
    el.title = err.message;
  }
}

translatePage();
$("scan").addEventListener("click", rescan);
poll();
loadVersion();
