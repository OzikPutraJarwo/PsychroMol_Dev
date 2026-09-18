import { api } from "./api.js";
import { Chart } from "./chart.js";
import * as dss from "./dss.js";
import * as fields from "./fields.js";
import { mollierChart, project, psychrometricChart } from "./geometry.js";
import * as psy from "./psychro.js";
import { DECISIONS, DEFAULT_COLUMNS, QUANTITIES, quantityById, valueOf } from "./quantities.js";
import { SOURCES, TOPICS } from "./references.js";
import { Trend } from "./trend.js";
import { PRESSURE_UNITS, kpaFromPa } from "./units.js";

const $ = (selector) => document.querySelector(selector);

const STATE_TONE = { OPTIMAL: "ok", LOW: "info", HIGH: "warning" };
const SEVERITY_ICON = { ok: "check_circle", warning: "warning", critical: "e911_emergency" };
const FIT_VIEWS = new Set(["chart", "data-chart", "data-table"]);
const LIVE_WITHOUT_LINK_SECONDS = 15;
const HISTORY_POINTS = 1500;
const TREND_POINTS = 600;
const DATA_CHART_POINTS = 2000;
const EXPORT_PAGE = 10000;
const DETECT_DELAY_MS = 600;
const TABLE_HEADER_HEIGHT = 38;
const TABLE_ROW_HEIGHT = 35;

const PROFILE_FIELDS = [
  "name", "crop_name", "stage",
  "temperature_min", "temperature_max", "temperature_reference",
  "humidity_min", "humidity_max", "humidity_reference",
  "vpd_min", "vpd_max", "vpd_reference",
  "pressure_mode", "pressure_kpa",
  "source_url", "poll_interval_seconds",
  "field_time", "field_temperature", "field_humidity", "field_pressure", "pressure_unit",
];

const state = {
  profiles: [],
  profile: null,
  latest: null,
  assessment: null,
  rules: [],
  view: "dashboard",
  miniKind: "psychrometric",
  fullKind: "psychrometric",
  range: { hours: 24, start: null, end: null, custom: false },
  columns: [...DEFAULT_COLUMNS],
  table: { page: 0, size: 20, total: 0 },
  timer: null,
  adviceOpen: false,
  lastSeenAt: null,
  history: [],
};

const charts = { mini: null, full: null, miniTrend: null, dataTrend: null };
const geometryCache = new Map();

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch {}
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function richText(value) {
  return escapeHtml(value)
    .replace(/_\{([^}]*)\}/g, "<sub>$1</sub>")
    .replace(/\^\{([^}]*)\}/g, "<sup>$1</sup>");
}

function number(value, digits) {
  return Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function numberOrNull(text) {
  const trimmed = String(text ?? "").trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function toast(message, bad = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("bad", bad);
  node.hidden = false;
  clearTimeout(Number(node.dataset.timer));
  node.dataset.timer = String(setTimeout(() => { node.hidden = true; }, 3600));
}

function icon(name, extra = "") {
  return `<span class="icon ${extra}">${name}</span>`;
}

function help(key) {
  return `<button type="button" class="help" data-help="${escapeHtml(key)}" aria-label="Formula and source" title="Formula and source">?</button>`;
}

function badge(value) {
  return `<span class="badge ${STATE_TONE[value] || "muted"}">${escapeHtml(value)}</span>`;
}

function severityBadge(severity) {
  return `<span class="badge ${escapeHtml(severity)}">${escapeHtml(severity)}</span>`;
}

function timeLabel(iso, seconds = true) {
  if (!iso) return "";
  return new Date(iso).toLocaleString([], {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", ...(seconds ? { second: "2-digit" } : {}),
  });
}

function stageLabel(profile) {
  return dss.stageById(profile.stage)?.label || profile.stage;
}

function bandText(min, max, unit, digits) {
  return `${number(min, digits)}–${number(max, digits)} ${unit}`;
}

function sourceLink(source) {
  if (!source.url) return "";
  return ` <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener">${escapeHtml(source.url.replace(/^https?:\/\//, ""))}</a>`;
}

function citationHtml(citation) {
  const source = SOURCES[citation.source];
  return `<li>
    <div><strong>${escapeHtml(source.short)}</strong>, ${escapeHtml(citation.locator)}</div>
    ${citation.quote ? `<blockquote>“${escapeHtml(citation.quote)}”</blockquote>` : ""}
    <div class="source-full">${escapeHtml(source.full)}${sourceLink(source)}</div>
  </li>`;
}

function freeTextHtml(text) {
  const mentioned = Object.values(SOURCES).filter((source) => text.includes(source.short));
  return `<div class="reference-text">${escapeHtml(text || "No reference entered.")}</div>
    ${mentioned.length ? `<ul class="citations">${mentioned.map((source) =>
      `<li><div class="source-full">${escapeHtml(source.full)}${sourceLink(source)}</div></li>`).join("")}</ul>` : ""}`;
}

function openReference(topic) {
  if (!topic) return;
  $("#reference-title").textContent = topic.title;
  $("#reference-body").innerHTML = `
    ${topic.formula?.length ? `<div class="formula">${topic.formula.map((line) => `<div>${richText(line)}</div>`).join("")}</div>` : ""}
    ${topic.where?.length ? `<ul class="where">${topic.where.map((line) => `<li>${richText(line)}</li>`).join("")}</ul>` : ""}
    ${(topic.text || []).map((paragraph) => `<p>${richText(paragraph)}</p>`).join("")}
    ${topic.note ? `<p class="note">${escapeHtml(topic.note)}</p>` : ""}
    ${topic.freeText !== undefined ? `<h3 class="section-title">Source</h3>${freeTextHtml(topic.freeText)}` : ""}
    ${topic.citations?.length ? `<h3 class="section-title">Sources</h3><ul class="citations">${topic.citations.map(citationHtml).join("")}</ul>` : ""}`;
  $("#reference-modal").hidden = false;
}

function stageReference(stageId) {
  const stage = dss.stageById(stageId);
  if (!stage) return null;
  return {
    title: `Reference VPD · ${stage.label}`,
    text: [`${bandText(stage.vpd.min, stage.vpd.max, "kPa", 2)} unless the profile has its own VPD band.`],
    note: stage.note,
    citations: stage.citations,
  };
}

function bandReference(key) {
  const profile = state.profile;
  if (!profile) return null;
  const indicator = dss.INDICATORS.find((item) => item.key === key);
  const band = dss.bands(profile)[key];
  if (!indicator || !band) return null;
  const range = bandText(band.min, band.max, indicator.unit, indicator.decimals);
  const where = `${profile.crop_name} · ${stageLabel(profile)}`;
  const rule = "Below the band is LOW, above it HIGH, and the limits count as inside.";
  if (key === "vpd" && !band.custom) {
    return {
      title: "VPD band",
      text: [`Optimal ${range}: the reference value for this growth stage (${where}).`, rule],
      note: band.stage.note,
      citations: band.stage.citations,
    };
  }
  return {
    title: `${indicator.label} band`,
    text: [`Optimal ${range}, entered for ${where}.`, rule],
    freeText: band.reference,
  };
}

function conditionSummary(rule) {
  return dss.INDICATORS.map(({ key, label }) => {
    const wanted = rule.conditions?.[key] ?? dss.ANY;
    return `${label} ${wanted === dss.ANY ? "any" : wanted}`;
  }).join(" · ");
}

function ruleReference(ruleId) {
  const rule = state.rules.find((item) => item.id === ruleId);
  if (!rule) return null;
  return {
    title: rule.name,
    text: [rule.recommendation, `Applies when: ${conditionSummary(rule)}.`],
    freeText: rule.reference,
  };
}

function openHelp(key) {
  const [kind, id] = key.split(":");
  const topic = {
    topic: () => TOPICS[id],
    band: () => bandReference(id),
    stage: () => stageReference(id),
    rule: () => ruleReference(Number(id)),
  }[kind]?.();
  if (topic) openReference(topic);
  else toast("No reference for this item", true);
}

function mergeProfile(profile) {
  if (!profile) return;
  state.profiles = state.profiles.map((item) => (item.id === profile.id ? profile : item));
  if (state.profile?.id === profile.id) {
    state.profile = profile;
    renderChip();
  }
}

function reassess() {
  state.assessment = state.profile ? dss.assess(state.profile, state.latest, state.rules) : null;
}

function showView(name) {
  state.view = name;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  $("#content").classList.toggle("fit", FIT_VIEWS.has(name));
  closeMenu();
  refreshViewData().catch((error) => toast(error.message, true));
  if (name === "rules") renderRules();
}

function closeMenu() {
  $("#sidebar").classList.remove("open");
  $("#scrim").classList.remove("open");
}

function renderChip() {
  if (!state.profile) {
    $("#chip-name").textContent = "No profile";
    $("#chip-sub").textContent = "Tap to set up";
    return;
  }
  $("#chip-name").textContent = state.profile.name;
  $("#chip-sub").textContent = `${state.profile.crop_name} · ${stageLabel(state.profile)}`;
}

function renderCards() {
  const host = $("#primary-cards");
  const { latest, assessment, profile } = state;
  if (!profile || !latest) {
    host.innerHTML = "";
    return;
  }
  const band = dss.bands(profile);
  const values = {
    temperature: latest.temperature_c,
    humidity: latest.relative_humidity_percent,
    vpd: assessment?.values?.vpd ?? null,
  };
  host.innerHTML = dss.INDICATORS.map((indicator) => {
    const classified = assessment?.classes?.[indicator.key];
    const limits = band[indicator.key];
    return `<div class="card ${classified && classified !== "OPTIMAL" ? "out" : ""}">
      <div class="card-top">
        <span class="label-row"><span class="label">${escapeHtml(indicator.label)}</span>${help(`topic:${indicator.topic}`)}</span>
        ${classified ? badge(classified) : ""}
      </div>
      <div class="value">${number(values[indicator.key], indicator.decimals)}<small>${escapeHtml(indicator.unit)}</small></div>
      <div class="target">${limits ? `Optimal ${escapeHtml(bandText(limits.min, limits.max, indicator.unit, indicator.decimals))}` : "No band"} ${help(`band:${indicator.key}`)}</div>
    </div>`;
  }).join("");
}

function sourceProblem() {
  const profile = state.profile;
  if (!profile?.last_poll_error) return "";
  return `<p class="problem">${icon("error")} The last fetch of the JSON link failed: ${escapeHtml(profile.last_poll_error)}</p>`;
}

function adviceDetailHtml() {
  const { assessment } = state;
  const steps = dss.explain(assessment);
  const classified = steps.filter((step) => step.group === "Classified");
  const workings = steps.filter((step) => step.group !== "Classified");
  const others = assessment.matches.slice(1);
  return `
    <div class="detail-block">
      <h4>Classification ${help("topic:classification")}</h4>
      <table class="calc">${classified.map((step) => `<tr>
        <th>${escapeHtml(step.label)}</th>
        <td>${escapeHtml(step.expression)}</td>
        <td class="result">${badge(step.result)}</td>
        <td class="help-cell">${help(`band:${step.band}`)}</td>
      </tr>`).join("")}</table>
      <p class="hint">${escapeHtml(assessment.label)}${assessment.headline ? ` → rule “${escapeHtml(assessment.headline.name)}”` : " → no rule matches"} ${help("topic:rules")}</p>
    </div>
    <div class="detail-block">
      <h4>Calculation</h4>
      <table class="calc">${workings.map((step) => `<tr>
        <th>${richText(step.label)}</th>
        <td>${richText(step.expression)}</td>
        <td class="result num">${escapeHtml(step.result)}</td>
        <td class="help-cell">${help(`topic:${step.topic}`)}</td>
      </tr>`).join("")}</table>
    </div>
    ${others.length ? `<div class="detail-block">
      <h4>Also matched</h4>
      ${others.map((rule) => `<p class="also">${severityBadge(rule.severity)} <strong>${escapeHtml(rule.name)}</strong> ${escapeHtml(rule.recommendation)} ${help(`rule:${rule.id}`)}</p>`).join("")}
    </div>` : ""}
    <p class="hint">Reading taken ${escapeHtml(timeLabel(state.latest.measured_at))} · updates live</p>`;
}

function renderAdvice() {
  const host = $("#advice-panel");
  const { profile, latest, assessment } = state;
  if (!profile) {
    host.innerHTML = "";
    return;
  }
  if (!latest) {
    host.innerHTML = `<div class="empty">
      ${icon("inbox")}
      <h3>No readings yet</h3>
      <p>${profile.source_url
        ? "Waiting for the first reading from the JSON link."
        : "Add a JSON link to this profile to start collecting readings."}</p>
      ${sourceProblem()}
      <button class="primary" id="empty-open">Open data settings</button>
    </div>`;
    $("#empty-open").addEventListener("click", () => openProfileModal("edit", profile.id, "data"));
    return;
  }
  if (!assessment?.classes) {
    host.innerHTML = `<div class="status warning">
      ${icon("warning")}
      <div class="status-body">
        <h3>This reading was not assessed</h3>
        <p>${escapeHtml(assessment?.error || "Unknown problem.")}</p>
        ${sourceProblem()}
      </div>
    </div>`;
    return;
  }
  const headline = assessment.headline;
  const severity = headline?.severity || "warning";
  const open = state.adviceOpen;
  host.innerHTML = `
    <section class="status advice ${escapeHtml(severity)}">
      ${icon(SEVERITY_ICON[severity] || "info")}
      <div class="status-body">
        <button type="button" class="advice-toggle" id="advice-toggle" aria-expanded="${open}">
          <span class="env-state">${escapeHtml(assessment.label)}</span>
          <span class="advice-title">${escapeHtml(headline ? headline.name : "No rule matches")}</span>
          <span class="advice-text">${escapeHtml(headline ? headline.recommendation : "No enabled rule matches these states. Add one on the Rules page.")}</span>
          <span class="advice-more">${open ? "Hide" : "Show"} how this was worked out ${icon(open ? "expand_less" : "expand_more")}</span>
        </button>
        ${sourceProblem()}
        <div class="advice-detail" ${open ? "" : "hidden"}>${open ? adviceDetailHtml() : ""}</div>
      </div>
      ${headline ? help(`rule:${headline.id}`) : ""}
    </section>`;
  $("#advice-toggle").addEventListener("click", () => {
    state.adviceOpen = !state.adviceOpen;
    renderAdvice();
  });
}

function renderPointDetail() {
  const host = $("#point-detail");
  const { latest, assessment } = state;
  if (!latest) {
    host.innerHTML = `<div class="point-empty">No reading yet</div>`;
    $("#point-time").textContent = "";
    return;
  }
  $("#point-time").textContent = timeLabel(latest.measured_at);
  const current = assessment?.state || null;
  host.innerHTML = QUANTITIES.map((quantity) => `
    <div class="point-row">
      <span class="label">${escapeHtml(quantity.label)} ${help(`topic:${quantity.topic}`)}</span>
      <span class="value">${number(valueOf(quantity, latest, current), quantity.decimals)}<small>${escapeHtml(quantity.unit)}</small></span>
    </div>`).join("");
}

function renderLive() {
  renderCards();
  renderAdvice();
  renderPointDetail();
  updateChartPoints();
}

function chartZone(profile) {
  return {
    temperatureMin: profile.temperature_min,
    temperatureMax: profile.temperature_max,
    humidityMin: profile.humidity_min,
    humidityMax: profile.humidity_max,
  };
}

function geometryFor(kind) {
  const profile = state.profile;
  const pressure = dss.pressureFor(profile, state.latest).pa;
  const zone = chartZone(profile);
  const key = [kind, Math.round(pressure / 10), zone.temperatureMin, zone.temperatureMax, zone.humidityMin, zone.humidityMax].join("|");
  if (!geometryCache.has(key)) {
    if (geometryCache.size > 12) geometryCache.clear();
    geometryCache.set(key, (kind === "mollier" ? mollierChart : psychrometricChart)({ pressure, zone }));
  }
  return geometryCache.get(key);
}

function currentPoint(kind) {
  const current = state.assessment?.state;
  if (!current) return null;
  const [x, y] = project(kind, current.temperature, current.humidityRatio);
  return { x, y };
}

function updateChartPoints() {
  if (charts.mini?.geometry) charts.mini.setCurrent(currentPoint(state.miniKind));
  if (charts.full?.geometry) charts.full.setCurrent(currentPoint(state.fullKind));
}

function setChartHelp(id, kind) {
  $(id).dataset.help = kind === "mollier" ? "topic:mollier-chart" : "topic:psychrometric-chart";
}

function drawChart(chart, kind) {
  try {
    const geometry = geometryFor(kind);
    if (chart.geometry !== geometry) chart.setGeometry(geometry);
    chart.setCurrent(currentPoint(kind));
  } catch (error) {
    if (!(error instanceof psy.PsychrometricRangeError)) throw error;
    chart.host.textContent = `Chart not available: ${error.message}`;
  }
}

function stateOfReading(reading) {
  const { state: computed } = dss.stateFor(state.profile, reading);
  return computed;
}

function historyPoints(kind) {
  const points = [];
  for (const reading of state.history) {
    const computed = stateOfReading(reading);
    if (!computed) continue;
    const [x, y] = project(kind, computed.temperature, computed.humidityRatio);
    points.push({
      x,
      y,
      time: reading.measured_at,
      lines: [
        timeLabel(reading.measured_at),
        `Temperature   ${number(computed.temperature, 1)} °C`,
        `Humidity   ${number(computed.relativeHumidity, 1)} %`,
        `VPD   ${number(kpaFromPa(computed.vapourPressureDeficit), 2)} kPa`,
      ],
    });
  }
  return points;
}

function hoursAgo(hours) {
  return new Date(Date.now() - hours * 3600000).toISOString();
}

async function loadMiniChart() {
  if (!state.profile || !state.latest) return;
  if (!charts.mini) charts.mini = new Chart($("#mini-chart"), { width: 560, height: 400, interactive: false });
  drawChart(charts.mini, state.miniKind);
}

async function loadMiniTrend() {
  if (!state.profile || !state.latest) return;
  if (!charts.miniTrend) charts.miniTrend = new Trend($("#mini-trend"), { width: 560, height: 400 });
  const payload = await api.readings(state.profile.id, { start: hoursAgo(24), max_points: TREND_POINTS });
  const rows = payload.items.map((reading) => {
    const computed = stateOfReading(reading);
    return {
      measured_at: reading.measured_at,
      temperature: reading.temperature_c,
      humidity: reading.relative_humidity_percent,
      vpd: computed ? kpaFromPa(computed.vapourPressureDeficit) : null,
    };
  });
  charts.miniTrend.setData(rows, [
    { key: "temperature", label: "Temperature", unit: "°C" },
    { key: "humidity", label: "Humidity", unit: "%" },
    { key: "vpd", label: "VPD", unit: "kPa" },
  ]);
}

async function loadFullChart() {
  if (!state.profile) return;
  if (!charts.full) charts.full = new Chart($("#full-chart"), { width: 880, height: 560, fitHeight: true });
  if (!state.latest) {
    charts.full.host.textContent = "No reading yet";
    return;
  }
  drawChart(charts.full, state.fullKind);
  await refreshChartHistory();
}

async function refreshChartHistory() {
  if (!state.profile || !charts.full) return;
  const payload = await api.readings(state.profile.id, { start: hoursAgo(24), max_points: HISTORY_POINTS });
  state.history = payload.items;
  stopPlayback();
  charts.full.setHistory(historyPoints(state.fullKind));
  const scrub = $("#history-scrub");
  scrub.max = Math.max(0, charts.full.historyRows.length - 1);
  scrub.value = scrub.max;
}

const playback = { timer: null, index: 0 };

function stopPlayback() {
  if (playback.timer) clearInterval(playback.timer);
  playback.timer = null;
  $("#history-play").innerHTML = `${icon("play_arrow")} Play history`;
  if (charts.full) charts.full.setPlaybackPoint(null);
  $("#history-scrub-time").textContent = "";
}

function playbackFrame(index) {
  const points = charts.full ? charts.full.historyRows : [];
  if (!points.length) return;
  const bounded = Math.max(0, Math.min(index, points.length - 1));
  const point = points[bounded];
  charts.full.setPlaybackPoint({ x: point.x, y: point.y });
  $("#history-scrub").value = bounded;
  $("#history-scrub-time").textContent = timeLabel(point.time, false);
}

function startPlayback() {
  const points = charts.full ? charts.full.historyRows : [];
  if (!points.length) { toast("No history to play back yet", true); return; }
  playback.index = Number($("#history-scrub").value);
  if (playback.index >= points.length - 1) playback.index = 0;
  $("#history-play").innerHTML = `${icon("pause")} Pause`;
  playback.timer = setInterval(() => {
    playbackFrame(playback.index);
    playback.index += 1;
    if (playback.index >= points.length) stopPlayback();
  }, 150);
}

function rangeParameters() {
  if (state.range.custom && state.range.start && state.range.end) {
    return { start: state.range.start, end: state.range.end };
  }
  return { start: hoursAgo(state.range.hours || 24) };
}

function toLocalInput(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function renderRangeControls() {
  const presets = [[1, "1 h"], [24, "24 h"], [168, "7 d"], [720, "30 d"]];
  const html = `
    <div class="range-controls">
      <div class="switch">
        ${presets.map(([hours, label]) => `<button data-range-hours="${hours}"
          class="${!state.range.custom && state.range.hours === hours ? "on" : ""}">${label}</button>`).join("")}
        <button data-range-custom="1" class="${state.range.custom ? "on" : ""}">Custom</button>
      </div>
      <div class="custom-range" ${state.range.custom ? "" : "hidden"}>
        <input type="datetime-local" data-range-start value="${toLocalInput(state.range.start)}">
        <span>to</span>
        <input type="datetime-local" data-range-end value="${toLocalInput(state.range.end)}">
        <button class="primary" data-range-apply>Apply</button>
      </div>
    </div>`;
  document.querySelectorAll(".range-host").forEach((host) => { host.innerHTML = html; });
}

async function reloadData() {
  state.table.page = 0;
  if (state.view === "data-chart") await loadDataChart();
  if (state.view === "data-table") await loadTable();
}

function wireRangeControls() {
  document.addEventListener("click", async (event) => {
    const preset = event.target.closest("[data-range-hours]");
    if (preset) {
      state.range = { hours: Number(preset.dataset.rangeHours), start: null, end: null, custom: false };
      renderRangeControls();
      await reloadData();
      return;
    }
    if (event.target.closest("[data-range-custom]")) {
      state.range = { ...state.range, custom: true };
      renderRangeControls();
      return;
    }
    const apply = event.target.closest("[data-range-apply]");
    if (apply) {
      const host = apply.closest(".range-controls");
      const start = host.querySelector("[data-range-start]").value;
      const end = host.querySelector("[data-range-end]").value;
      if (!start || !end) { toast("Choose both dates", true); return; }
      state.range = { hours: null, start: new Date(start).toISOString(), end: new Date(end).toISOString(), custom: true };
      renderRangeControls();
      await reloadData();
    }
  });
}

function numericColumns() {
  return state.columns.map(quantityById).filter(Boolean);
}

async function loadDataChart() {
  if (!state.profile) return;
  if (!charts.dataTrend) charts.dataTrend = new Trend($("#data-trend"), { width: 880, height: 420, fitHeight: true });
  const quantities = numericColumns();
  if (!quantities.length) {
    charts.dataTrend.setData([], []);
    return;
  }
  const payload = await api.readings(state.profile.id, { ...rangeParameters(), max_points: DATA_CHART_POINTS });
  const rows = payload.items.map((reading) => {
    const computed = stateOfReading(reading);
    const row = { measured_at: reading.measured_at };
    for (const quantity of quantities) row[quantity.id] = valueOf(quantity, reading, computed);
    return row;
  });
  charts.dataTrend.setData(rows, quantities.map((quantity) => ({ key: quantity.id, label: quantity.label, unit: quantity.unit })));
}

function tablePageSize() {
  const host = $("#table-fill");
  if (!$("#content").classList.contains("fit") || window.innerWidth <= 900) return 20;
  const height = host.clientHeight - 14;
  if (height <= 0) return state.table.size;
  return Math.max(5, Math.floor((height - TABLE_HEADER_HEIGHT) / TABLE_ROW_HEIGHT));
}

function decisionValues(reading) {
  const result = dss.assess(state.profile, reading, state.rules);
  return {
    state: result.label || result.error || "",
    rule: result.headline?.name || "",
    recommendation: result.headline?.recommendation || "",
    severity: result.headline?.severity || "",
  };
}

async function loadTable() {
  if (!state.profile) return;
  const size = tablePageSize();
  state.table.size = size;
  const payload = await api.readings(state.profile.id, {
    ...rangeParameters(), limit: size, offset: state.table.page * size, order: "desc",
  });
  state.table.total = payload.total;
  const pages = Math.max(1, Math.ceil(payload.total / size));
  if (state.table.page >= pages && payload.total) {
    state.table.page = pages - 1;
    await loadTable();
    return;
  }
  const quantities = numericColumns();
  const decisions = DECISIONS.filter((decision) => state.columns.includes(decision.id));
  $("#data-table").innerHTML = `
    <thead><tr>
      <th>Time</th>
      ${quantities.map((quantity) => `<th>${escapeHtml(quantity.label)} (${escapeHtml(quantity.unit)})</th>`).join("")}
      ${decisions.map((decision) => `<th class="text-cell">${escapeHtml(decision.label)}</th>`).join("")}
    </tr></thead>
    <tbody>${payload.items.map((reading) => {
      const computed = stateOfReading(reading);
      const decided = decisions.length ? decisionValues(reading) : null;
      return `<tr>
        <td>${escapeHtml(new Date(reading.measured_at).toLocaleString())}</td>
        ${quantities.map((quantity) => {
          const value = valueOf(quantity, reading, computed);
          return Number.isFinite(value) ? `<td>${number(value, quantity.decimals)}</td>` : '<td class="muted-cell">—</td>';
        }).join("")}
        ${decisions.map((decision) => decision.id === "rule" && decided.severity
          ? `<td class="text-cell">${severityBadge(decided.severity)} ${escapeHtml(decided.rule)}</td>`
          : `<td class="text-cell wrap" title="${escapeHtml(decided[decision.id])}">${escapeHtml(decided[decision.id]) || "—"}</td>`).join("")}
      </tr>`;
    }).join("")}</tbody>`;

  $("#pager-text").textContent = payload.total
    ? `Page ${state.table.page + 1} of ${pages} · ${payload.total} readings · newest first`
    : "No readings in this range";
  document.querySelectorAll("[data-page]").forEach((button) => {
    const back = button.dataset.page === "first" || button.dataset.page === "previous";
    button.disabled = back ? state.table.page === 0 : state.table.page >= pages - 1;
  });
}

function wireTable() {
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", async () => {
      const pages = Math.max(1, Math.ceil(state.table.total / state.table.size));
      const moves = { first: 0, previous: state.table.page - 1, next: state.table.page + 1, last: pages - 1 };
      state.table.page = Math.max(0, Math.min(pages - 1, moves[button.dataset.page]));
      await loadTable();
    });
  });

  let resizeTimer = null;
  new ResizeObserver(() => {
    if (state.view !== "data-table") return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const size = tablePageSize();
      if (size === state.table.size) return;
      state.table.page = Math.floor((state.table.page * state.table.size) / size);
      loadTable().catch((error) => toast(error.message, true));
    }, 150);
  }).observe($("#table-fill"));
}

async function refreshViewData() {
  if (!state.profile) return;
  if (state.view === "dashboard") await Promise.all([loadMiniChart(), loadMiniTrend()]);
  if (state.view === "chart") await loadFullChart();
  if (state.view === "data-chart") await loadDataChart();
  if (state.view === "data-table" && state.table.page === 0) await loadTable();
}

async function updateLatest() {
  const profile = state.profile;
  if (!profile) return;
  if (profile.source_url) {
    const result = await api.refresh(profile.id);
    if (state.profile?.id !== profile.id) return;
    state.latest = result.latest;
    mergeProfile(result.profile);
  } else {
    const latest = await api.latest(profile.id);
    if (state.profile?.id !== profile.id) return;
    state.latest = latest;
  }
  reassess();
}

let liveInFlight = false;

async function liveTick() {
  if (liveInFlight || !state.profile) return;
  liveInFlight = true;
  try {
    await updateLatest();
    renderLive();
    const seen = state.latest?.measured_at ?? null;
    if (seen !== state.lastSeenAt) {
      state.lastSeenAt = seen;
      await refreshViewData();
    }
  } catch (error) {
    console.warn("live update failed", error);
  } finally {
    liveInFlight = false;
  }
}

function startLive() {
  clearInterval(state.timer);
  if (!state.profile) return;
  const seconds = state.profile.source_url ? state.profile.poll_interval_seconds : LIVE_WITHOUT_LINK_SECONDS;
  state.timer = setInterval(liveTick, Math.max(1, seconds) * 1000);
}

async function loadRules() {
  const profile = state.profile;
  if (!profile.rules_seeded) {
    state.rules = await api.replaceRules(profile.id, dss.defaultRules());
    mergeProfile({ ...profile, rules_seeded: true });
    toast("The default rules were added to this profile");
  } else {
    state.rules = await api.rules(profile.id);
  }
}

async function selectProfile(profile) {
  clearInterval(state.timer);
  stopPlayback();
  state.profile = profile;
  state.latest = null;
  state.assessment = null;
  state.history = [];
  state.lastSeenAt = null;
  state.table.page = 0;
  storageSet("psychromol.profile", String(profile.id));
  renderChip();
  if (charts.full) charts.full.setHistory([]);
  try {
    await loadRules();
    await updateLatest();
  } catch (error) {
    toast(error.message, true);
  }
  reassess();
  state.lastSeenAt = state.latest?.measured_at ?? null;
  renderLive();
  if (state.view === "rules") renderRules();
  startLive();
  if (!state.latest) {
    $("#mini-chart").textContent = "";
    $("#mini-trend").textContent = "";
    charts.mini?.destroy();
    charts.miniTrend?.destroy();
    charts.mini = null;
    charts.miniTrend = null;
  }
  await refreshViewData().catch((error) => toast(error.message, true));
}

function renderRules() {
  const host = $("#rules-list");
  if (!state.profile) {
    $("#rules-intro").textContent = "Choose a profile first.";
    host.innerHTML = "";
    return;
  }
  $("#rules-intro").textContent = `Rules for ${state.profile.name}. The worst severity, then the lowest order, gives the recommendation.`;
  if (!state.rules.length) {
    host.innerHTML = `<div class="empty">
      ${icon("rule")}
      <h3>No rules</h3>
      <p>Rules turn the classified state into the recommendation on the dashboard.</p>
      <button class="primary" id="rules-restore">Restore the default rules</button>
    </div>`;
    $("#rules-restore").addEventListener("click", resetRules);
    return;
  }
  host.innerHTML = `<div class="list">${state.rules.map((rule) => `
    <div class="list-item">
      <span class="order mono">${rule.priority}</span>
      <div class="grow">
        <div class="name">
          ${severityBadge(rule.severity)}
          ${escapeHtml(rule.name)}
          ${rule.enabled ? "" : '<span class="badge muted">off</span>'}
          ${help(`rule:${rule.id}`)}
        </div>
        <div class="sub">${escapeHtml(conditionSummary(rule))}</div>
        <div class="sub">${escapeHtml(rule.recommendation)}</div>
      </div>
      <button class="icon-button" data-edit="${rule.id}" aria-label="Edit">${icon("edit")}</button>
      <button class="icon-button" data-delete="${rule.id}" aria-label="Delete">${icon("delete")}</button>
    </div>`).join("")}</div>`;

  host.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => openRuleModal(Number(button.dataset.edit)));
  });
  host.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const rule = state.rules.find((item) => item.id === Number(button.dataset.delete));
      if (!confirm(`Delete the rule "${rule.name}"?`)) return;
      try {
        await api.deleteRule(rule.id);
        await afterRulesChange("Rule deleted");
      } catch (error) { toast(error.message, true); }
    });
  });
}

async function afterRulesChange(message) {
  state.rules = await api.rules(state.profile.id);
  reassess();
  renderRules();
  renderLive();
  if (state.view === "data-table") await loadTable();
  toast(message);
}

async function resetRules() {
  if (!state.profile || !confirm(`Replace every rule of ${state.profile.name} with the default set?`)) return;
  try {
    await api.replaceRules(state.profile.id, dss.defaultRules());
    await afterRulesChange("Default rules restored");
  } catch (error) { toast(error.message, true); }
}

function stateSelect(id, value) {
  return `<select id="${id}">${[dss.ANY, ...dss.STATES].map((option) =>
    `<option value="${option}" ${option === value ? "selected" : ""}>${option === dss.ANY ? "Any" : option}</option>`).join("")}</select>`;
}

function openRuleModal(ruleId) {
  if (!state.profile) return;
  const rule = ruleId ? state.rules.find((item) => item.id === ruleId) : null;
  const conditions = rule?.conditions || { temperature: "HIGH", humidity: dss.ANY, vpd: dss.ANY };
  const nextOrder = Math.max(0, ...state.rules.map((item) => item.priority)) + 10;

  $("#rule-modal-title").textContent = rule ? "Edit rule" : "New rule";
  $("#rule-form").innerHTML = `
    <div class="field-row">
      <label class="field">Name<input type="text" id="rule-name" value="${escapeHtml(rule?.name || "")}" placeholder="Hot and humid"></label>
      <label class="field">Severity<select id="rule-severity">${dss.SEVERITIES.map((severity) =>
        `<option value="${severity}" ${severity === (rule?.severity || "warning") ? "selected" : ""}>${severity}</option>`).join("")}</select></label>
      <label class="field">Order<input type="number" step="1" id="rule-priority" value="${rule?.priority ?? nextOrder}"></label>
      <label class="field">Enabled<select id="rule-enabled">
        <option value="yes" ${rule && !rule.enabled ? "" : "selected"}>yes</option>
        <option value="no" ${rule && !rule.enabled ? "selected" : ""}>no</option>
      </select></label>
    </div>
    <h3 class="section-title">When ${help("topic:classification")}</h3>
    <div class="field-row">
      ${dss.INDICATORS.map((indicator) => `<label class="field">${escapeHtml(indicator.label)}${stateSelect(`rule-${indicator.key}`, conditions[indicator.key] ?? dss.ANY)}</label>`).join("")}
    </div>
    <h3 class="section-title">Recommend</h3>
    <textarea id="rule-recommendation" placeholder="Ventilate, then cool.">${escapeHtml(rule?.recommendation || "")}</textarea>
    <h3 class="section-title">Reference</h3>
    <textarea id="rule-reference" placeholder="Author (year), title, page. “The sentence the advice rests on.”">${escapeHtml(rule?.reference || "")}</textarea>
    <p class="hint">Every recommendation needs the source it rests on; it is shown behind the ? next to the advice.</p>
    <div class="form-actions">
      <button class="ghost" data-close>Cancel</button>
      <button class="primary" id="rule-save">${rule ? "Save rule" : "Create rule"}</button>
    </div>`;
  $("#rule-modal").hidden = false;

  $("#rule-save").addEventListener("click", async () => {
    const body = {
      name: $("#rule-name").value.trim(),
      conditions: Object.fromEntries(dss.INDICATORS.map(({ key }) => [key, $(`#rule-${key}`).value])),
      severity: $("#rule-severity").value,
      recommendation: $("#rule-recommendation").value.trim(),
      reference: $("#rule-reference").value.trim(),
      priority: Number($("#rule-priority").value),
      enabled: $("#rule-enabled").value === "yes",
    };
    const problems = dss.validateRule(body);
    if (problems.length) { toast(problems.join("; "), true); return; }
    try {
      if (rule) await api.updateRule(rule.id, body);
      else await api.addRule(state.profile.id, body);
      $("#rule-modal").hidden = true;
      await afterRulesChange(rule ? "Rule saved" : "Rule created");
    } catch (error) { toast(error.message, true); }
  });
}

const modalState = {
  mode: "edit",
  editingProfileId: null,
  addRendered: false,
  tab: "crop",
  source: { url: "", document: null, via: null, error: null, readAt: null },
};

let previewTimer = null;
let detectTimer = null;

function stopPreview() {
  clearInterval(previewTimer);
  clearTimeout(detectTimer);
  previewTimer = null;
  detectTimer = null;
}

function editingProfile() {
  return state.profiles.find((item) => item.id === modalState.editingProfileId) || null;
}

function profileBody(profile, changes = {}) {
  const body = {};
  for (const key of PROFILE_FIELDS) body[key] = profile[key];
  return { ...body, ...changes };
}

function openProfileModal(mode, profileId = null, startTab = null) {
  stopPreview();
  modalState.mode = mode;
  modalState.editingProfileId = mode === "edit" ? (profileId ?? state.profile?.id ?? null) : null;
  if (mode === "edit" && !editingProfile()) {
    modalState.mode = "add";
    modalState.editingProfileId = null;
  }
  if (modalState.mode === "add") modalState.addRendered = false;
  modalState.source = { url: "", document: null, via: null, error: null, readAt: null };
  modalState.tab = startTab || "crop";
  $("#profile-modal").hidden = false;
  renderProfileModal();
}

function closeProfileModal() {
  stopPreview();
  $("#profile-modal").hidden = true;
}

function renderProfileModal() {
  const card = $("#profile-modal-card");
  stopPreview();
  if (modalState.mode === "switch") {
    card.classList.remove("wide");
    card.innerHTML = switchModeHtml();
    wireSwitchMode(card);
    return;
  }
  card.classList.add("wide");
  const profile = modalState.mode === "edit" ? editingProfile() : null;
  card.innerHTML = editorModeHtml(profile);
  wireEditorHeader(profile);
  card.querySelectorAll(".modal-nav-item").forEach((item) => {
    item.addEventListener("click", () => switchModalTab(item.dataset.tab));
  });
  switchModalTab(modalState.tab);
}

function switchModeHtml() {
  const rows = state.profiles.map((profile) => `
    <div class="list-item" data-switch-to="${profile.id}">
      <div class="grow">
        <div class="name">${escapeHtml(profile.name)}</div>
        <div class="sub">${escapeHtml(`${profile.crop_name} · ${stageLabel(profile)}`)}${profile.source_url ? " · live link" : ""}</div>
      </div>
      ${profile.id === state.profile?.id ? '<span class="badge ok">current</span>' : ""}
      <span class="icon">chevron_right</span>
    </div>`).join("");
  return `
    <div class="modal-head">
      <h2>Switch profile</h2>
      <button class="icon-button" data-close><span class="icon">close</span></button>
    </div>
    <div class="modal-body">
      ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">${icon("workspaces")}<h3>No profiles</h3><p>Add one below.</p></div>`}
      <button class="primary wide-button" id="switch-add-new">${icon("add")} Add new profile</button>
    </div>`;
}

function wireSwitchMode(card) {
  card.querySelectorAll("[data-switch-to]").forEach((row) => {
    row.addEventListener("click", async () => {
      closeProfileModal();
      await selectProfile(state.profiles.find((item) => item.id === Number(row.dataset.switchTo)));
    });
  });
  $("#switch-add-new").addEventListener("click", () => openProfileModal("add"));
}

function editorModeHtml(profile) {
  const actions = profile
    ? `<button class="danger" id="profile-delete-btn">${icon("delete")} Delete</button>
       <button class="ghost" id="profile-switch-btn">${icon("swap_horiz")} Switch profile</button>`
    : `<button class="primary" id="profile-create-btn">${icon("add")} Create profile</button>`;
  return `
    <div class="modal-head">
      <input class="modal-title-input" id="profile-name-input" placeholder="Profile name, e.g. Tomato · House 1" value="${escapeHtml(profile ? profile.name : "")}">
      <div class="row">
        ${actions}
        <button class="icon-button" data-close><span class="icon">close</span></button>
      </div>
    </div>
    <div class="modal-body split">
      <nav class="modal-nav">
        <button class="modal-nav-item" data-tab="crop"><span class="icon">psychiatry</span><span>Crop</span></button>
        <button class="modal-nav-item" data-tab="data"><span class="icon">cloud_download</span><span>Data</span></button>
      </nav>
      <div class="modal-pane">
        <div class="tab" id="tab-crop"></div>
        <div class="tab" id="tab-data"></div>
      </div>
    </div>`;
}

function wireEditorHeader(profile) {
  const nameInput = $("#profile-name-input");
  if (profile) {
    nameInput.addEventListener("change", async () => {
      const name = nameInput.value.trim();
      if (!name) { nameInput.value = profile.name; return; }
      if (name === profile.name) return;
      await saveProfile(profile, { name }, "Profile name saved");
    });
  }
  $("#profile-switch-btn")?.addEventListener("click", () => {
    stopPreview();
    modalState.mode = "switch";
    renderProfileModal();
  });
  $("#profile-delete-btn")?.addEventListener("click", () => deleteProfile(profile));
  $("#profile-create-btn")?.addEventListener("click", createProfileFromForm);
}

function switchModalTab(tab) {
  modalState.tab = tab;
  document.querySelectorAll(".modal-nav-item").forEach((item) => item.classList.toggle("active", item.dataset.tab === tab));
  document.querySelectorAll("#profile-modal .tab").forEach((pane) => pane.classList.toggle("active", pane.id === `tab-${tab}`));
  if (modalState.mode === "add") {
    if (!modalState.addRendered) {
      renderCropTab();
      renderDataTab();
      modalState.addRendered = true;
    }
    if (tab === "data") startPreviewTimer();
    return;
  }
  if (tab === "crop") {
    stopPreview();
    renderCropTab();
  }
  if (tab === "data") renderDataTab();
}

function bandFieldsHtml(key, label, unit, profile) {
  const value = (name) => (profile && profile[name] !== null && profile[name] !== undefined ? profile[name] : "");
  return `
    <div class="band-block">
      <div class="band-head"><h3 class="section-title">${escapeHtml(label)}</h3>${help("topic:thresholds")}</div>
      <div class="field-row">
        <label class="field">Optimal from (${escapeHtml(unit)})<input type="number" step="any" id="crop-${key}-min" value="${escapeHtml(value(`${key}_min`))}"></label>
        <label class="field">Optimal to (${escapeHtml(unit)})<input type="number" step="any" id="crop-${key}-max" value="${escapeHtml(value(`${key}_max`))}"></label>
      </div>
      <label class="field">Reference for this band
        <textarea id="crop-${key}-reference" placeholder="Author (year), title, page or table.">${escapeHtml(value(`${key}_reference`))}</textarea>
      </label>
    </div>`;
}

function renderCropTab() {
  const host = $("#tab-crop");
  const profile = modalState.mode === "edit" ? editingProfile() : null;
  const stageId = profile?.stage || "vegetative";
  const custom = profile ? profile.vpd_min !== null && profile.vpd_max !== null : false;
  host.innerHTML = `
    <p class="tip">One crop and one growth stage per profile. Temperature and humidity bands have no defaults: enter them with the source they come from.</p>
    <div class="field-row">
      <label class="field">Crop<input type="text" id="crop-name" value="${escapeHtml(profile?.crop_name || "")}" placeholder="Tomato"></label>
      <label class="field">Growth stage<select id="crop-stage">${dss.STAGES.map((stage) =>
        `<option value="${stage.id}" ${stage.id === stageId ? "selected" : ""}>${escapeHtml(stage.label)}</option>`).join("")}</select></label>
    </div>
    ${bandFieldsHtml("temperature", "Temperature", "°C", profile)}
    ${bandFieldsHtml("humidity", "Relative humidity", "%", profile)}
    <div class="band-block">
      <div class="band-head"><h3 class="section-title">VPD</h3>${help("topic:vpd")}</div>
      <div class="radios">
        <label class="radio"><input type="radio" name="crop-vpd" value="stage" ${custom ? "" : "checked"}>
          <span>Reference value for this stage: <strong id="crop-vpd-default"></strong></span>
          <button type="button" class="help" id="crop-vpd-default-help" data-help="stage:${stageId}" aria-label="Formula and source">?</button>
        </label>
        <label class="radio"><input type="radio" name="crop-vpd" value="custom" ${custom ? "checked" : ""}><span>My own band</span></label>
      </div>
      <div id="crop-vpd-custom" ${custom ? "" : "hidden"}>
        <div class="field-row">
          <label class="field">Optimal from (kPa)<input type="number" step="any" id="crop-vpd-min" value="${escapeHtml(profile?.vpd_min ?? "")}"></label>
          <label class="field">Optimal to (kPa)<input type="number" step="any" id="crop-vpd-max" value="${escapeHtml(profile?.vpd_max ?? "")}"></label>
        </div>
        <label class="field">Reference for this band
          <textarea id="crop-vpd-reference" placeholder="Author (year), title, page or table.">${escapeHtml(profile?.vpd_reference || "")}</textarea>
        </label>
      </div>
    </div>
    ${profile ? `<div class="form-actions"><button class="primary" id="crop-save">Save crop</button></div>` : ""}`;

  const showDefault = () => {
    const stage = dss.stageById($("#crop-stage").value);
    $("#crop-vpd-default").textContent = bandText(stage.vpd.min, stage.vpd.max, "kPa", 2);
    $("#crop-vpd-default-help").dataset.help = `stage:${stage.id}`;
  };
  showDefault();
  $("#crop-stage").addEventListener("change", showDefault);
  host.querySelectorAll('input[name="crop-vpd"]').forEach((input) => {
    input.addEventListener("change", () => {
      $("#crop-vpd-custom").hidden = host.querySelector('input[name="crop-vpd"]:checked').value !== "custom";
    });
  });
  $("#crop-save")?.addEventListener("click", async () => {
    const body = collectCropForm();
    const problems = cropProblems(body);
    if (problems.length) { toast(problems.join("; "), true); return; }
    await saveProfile(profile, body, "Crop saved");
  });
}

function collectCropForm() {
  const custom = document.querySelector('#tab-crop input[name="crop-vpd"]:checked')?.value === "custom";
  const text = (id) => $(id).value.trim();
  return {
    crop_name: text("#crop-name"),
    stage: $("#crop-stage").value,
    temperature_min: numberOrNull($("#crop-temperature-min").value),
    temperature_max: numberOrNull($("#crop-temperature-max").value),
    temperature_reference: text("#crop-temperature-reference"),
    humidity_min: numberOrNull($("#crop-humidity-min").value),
    humidity_max: numberOrNull($("#crop-humidity-max").value),
    humidity_reference: text("#crop-humidity-reference"),
    vpd_min: custom ? numberOrNull($("#crop-vpd-min").value) : null,
    vpd_max: custom ? numberOrNull($("#crop-vpd-max").value) : null,
    vpd_reference: custom ? text("#crop-vpd-reference") : null,
    customVpd: custom,
  };
}

function cropProblems(body) {
  const problems = [];
  if (!body.crop_name) problems.push("enter the crop");
  for (const [key, label] of [["temperature", "temperature"], ["humidity", "humidity"]]) {
    if (body[`${key}_min`] === null || body[`${key}_max`] === null) problems.push(`enter the ${label} band`);
    else if (body[`${key}_min`] >= body[`${key}_max`]) problems.push(`the ${label} minimum must be below the maximum`);
    if (!body[`${key}_reference`]) problems.push(`enter the reference for the ${label} band`);
  }
  if (body.customVpd) {
    if (body.vpd_min === null || body.vpd_max === null) problems.push("enter your VPD band");
    else if (body.vpd_min >= body.vpd_max) problems.push("the VPD minimum must be below the maximum");
    if (!body.vpd_reference) problems.push("enter the reference for your VPD band");
  }
  return problems;
}

function withoutFormFlags(body) {
  const { customVpd, ...rest } = body;
  return rest;
}

function sourceLeafLabel(leaf) {
  const shown = typeof leaf.value === "string" ? `"${leaf.value}"` : String(leaf.value);
  return `${leaf.pointer} = ${shown.length > 40 ? `${shown.slice(0, 37)}…` : shown}`;
}

function optionsHtml(leaves, selected, emptyLabel) {
  const pointers = new Set(leaves.map((leaf) => leaf.pointer));
  const kept = selected && !pointers.has(selected)
    ? `<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)} (not in the latest reading)</option>` : "";
  return `${emptyLabel !== null ? `<option value="">${escapeHtml(emptyLabel)}</option>` : ""}${kept}${leaves.map((leaf) =>
    `<option value="${escapeHtml(leaf.pointer)}" ${leaf.pointer === selected ? "selected" : ""}>${escapeHtml(sourceLeafLabel(leaf))}</option>`).join("")}`;
}

function renderDataTab() {
  const host = $("#tab-data");
  stopPreview();
  const profile = modalState.mode === "edit" ? editingProfile() : null;
  const mode = profile?.pressure_mode || "standard";
  const polled = profile?.last_polled_at ? `Last fetched by the server ${timeLabel(profile.last_polled_at)}` : "Not fetched yet";
  host.innerHTML = `
    <p class="tip">Paste a link that returns JSON. PsychroMol reads it, lists the values it finds, and you choose which is the temperature and which the humidity. The server then fetches the link on this interval and stores each new reading, even while no browser is open.</p>
    <div class="field-row source-row">
      <label class="field">JSON link<input type="url" id="src-url" placeholder="https://example.com/greenhouse.json" value="${escapeHtml(profile?.source_url || "")}"></label>
      <label class="field">Fetch every (s)<input type="number" id="src-interval" min="1" step="1" value="${profile?.poll_interval_seconds ?? 60}"></label>
    </div>
    <p class="hint" id="src-status"></p>
    <h3 class="section-title">Fields</h3>
    <div class="field-row">
      <label class="field">Time<select id="src-time"></select></label>
      <label class="field">Temperature (°C)<select id="src-temperature"></select></label>
      <label class="field">Relative humidity (%)<select id="src-humidity"></select></label>
    </div>
    <p class="hint">A time without a time zone is read as UTC. Without a time field, each reading takes the moment the server receives it.</p>
    <div class="band-head"><h3 class="section-title">Pressure</h3>${help("topic:pressure")}</div>
    <div class="radios">
      <label class="radio"><input type="radio" name="src-pressure" value="standard" ${mode === "standard" ? "checked" : ""}><span>Standard atmosphere, 101.325 kPa</span></label>
      <label class="radio"><input type="radio" name="src-pressure" value="fixed" ${mode === "fixed" ? "checked" : ""}><span>A fixed value</span></label>
      <label class="radio"><input type="radio" name="src-pressure" value="field" ${mode === "field" ? "checked" : ""}><span>A value in the link</span></label>
    </div>
    <div class="field-row" id="src-pressure-fixed" ${mode === "fixed" ? "" : "hidden"}>
      <label class="field">Pressure (kPa)<input type="number" step="any" id="src-pressure-kpa" value="${escapeHtml(profile?.pressure_kpa ?? "")}"></label>
    </div>
    <div class="field-row" id="src-pressure-field" ${mode === "field" ? "" : "hidden"}>
      <label class="field">Pressure field<select id="src-pressure-pointer"></select></label>
      <label class="field">Unit<select id="src-pressure-unit">${Object.keys(PRESSURE_UNITS).map((unit) =>
        `<option value="${unit}" ${unit === (profile?.pressure_unit || "kPa") ? "selected" : ""}>${unit}</option>`).join("")}</select></label>
    </div>
    <h3 class="section-title">Preview</h3>
    <div id="src-preview" class="preview"><p class="hint">Paste a link to see what will be read.</p></div>
    ${profile ? `<div class="form-actions spread">
      <span class="hint inline">${escapeHtml(polled)}${profile.last_poll_error ? ` · <span class="bad-text">${escapeHtml(profile.last_poll_error)}</span>` : ""}</span>
      <span class="row">
        <button class="ghost" id="src-refresh">${icon("refresh")} Fetch now</button>
        <button class="primary" id="src-save">Save data source</button>
      </span>
    </div>` : ""}`;

  const selected = {
    time: profile?.field_time || "",
    temperature: profile?.field_temperature || "",
    humidity: profile?.field_humidity || "",
    pressure: profile?.field_pressure || "",
  };
  fillFieldSelects(selected);

  host.querySelectorAll('input[name="src-pressure"]').forEach((input) => {
    input.addEventListener("change", () => {
      const chosen = pressureMode();
      $("#src-pressure-fixed").hidden = chosen !== "fixed";
      $("#src-pressure-field").hidden = chosen !== "field";
      renderPreview();
    });
  });
  ["#src-time", "#src-temperature", "#src-humidity", "#src-pressure-pointer", "#src-pressure-unit", "#src-pressure-kpa"].forEach((id) => {
    $(id).addEventListener("change", renderPreview);
  });
  $("#src-url").addEventListener("input", () => {
    clearTimeout(detectTimer);
    detectTimer = setTimeout(() => readSource(true), DETECT_DELAY_MS);
  });
  $("#src-interval").addEventListener("change", startPreviewTimer);

  $("#src-save")?.addEventListener("click", async () => {
    const body = collectDataForm();
    const problems = dataProblems(body);
    if (problems.length) { toast(problems.join("; "), true); return; }
    await saveProfile(profile, body, "Data source saved");
  });
  $("#src-refresh")?.addEventListener("click", async () => {
    try {
      const result = await api.refresh(profile.id);
      mergeProfile(result.profile);
      if (state.profile?.id === profile.id) {
        state.latest = result.latest;
        reassess();
        renderLive();
      }
      toast(result.error ? `The server could not read the link: ${result.error}` : result.stored ? "A new reading was stored" : "No new reading: the link still shows the last one", Boolean(result.error));
      renderDataTab();
    } catch (error) { toast(error.message, true); }
  });

  if ($("#src-url").value.trim()) readSource(false);
  startPreviewTimer();
}

function pressureMode() {
  return document.querySelector('#tab-data input[name="src-pressure"]:checked')?.value || "standard";
}

function currentSelections() {
  return {
    time: $("#src-time")?.value ?? "",
    temperature: $("#src-temperature")?.value ?? "",
    humidity: $("#src-humidity")?.value ?? "",
    pressure: $("#src-pressure-pointer")?.value ?? "",
  };
}

function fillFieldSelects(selected, guess = null) {
  const found = modalState.source.document === null ? null : fields.detect(modalState.source.document);
  const pick = (key) => selected[key] || guess?.[key] || "";
  const numbers = found ? found.numbers : [];
  const times = found ? found.times : [];
  $("#src-time").innerHTML = optionsHtml(times, pick("time"), "When the server receives it");
  $("#src-temperature").innerHTML = optionsHtml(numbers, pick("temperature"), "Choose…");
  $("#src-humidity").innerHTML = optionsHtml(numbers, pick("humidity"), "Choose…");
  $("#src-pressure-pointer").innerHTML = optionsHtml(numbers, pick("pressure"), "Choose…");
  if (guess?.pressure && !selected.pressure && found?.pressureUnit) $("#src-pressure-unit").value = found.pressureUnit;
}

async function fetchSourceDocument(url) {
  let response;
  try {
    response = await fetch(url, { cache: "no-store" });
  } catch {
    const result = await api.fetchThroughServer(url);
    if (!result.ok) throw new Error(result.error);
    return { document: result.document, via: "server" };
  }
  if (!response.ok) throw new Error(`the link returned HTTP ${response.status}`);
  try {
    return { document: await response.json(), via: "browser" };
  } catch {
    throw new Error("the link did not return valid JSON");
  }
}

async function readSource(fresh) {
  const input = $("#src-url");
  if (!input) return;
  const url = input.value.trim();
  const status = $("#src-status");
  if (!url) {
    modalState.source = { url: "", document: null, via: null, error: null, readAt: null };
    status.textContent = "";
    fillFieldSelects(currentSelections());
    renderPreview();
    return;
  }
  if (!/^https?:\/\//i.test(url)) {
    status.innerHTML = `<span class="bad-text">The link must start with http:// or https://</span>`;
    return;
  }
  const before = currentSelections();
  const changedLink = modalState.source.url !== url;
  try {
    const { document, via } = await fetchSourceDocument(url);
    if ($("#src-url")?.value.trim() !== url) return;
    modalState.source = { url, document, via, error: null, readAt: new Date().toISOString() };
    status.textContent = via === "browser"
      ? "Read directly from the link."
      : "Read through the server, because this link does not let browsers read it directly.";
  } catch (error) {
    if ($("#src-url")?.value.trim() !== url) return;
    modalState.source = { url, document: null, via: null, error: error.message, readAt: null };
    status.innerHTML = `<span class="bad-text">Could not read the link: ${escapeHtml(error.message)}</span>`;
  }
  if (fresh || changedLink) {
    const guess = modalState.source.document === null ? null : fields.detect(modalState.source.document).guess;
    fillFieldSelects(changedLink && fresh ? { time: "", temperature: "", humidity: "", pressure: "" } : before, guess);
  } else {
    fillFieldSelects(before);
  }
  renderPreview();
}

function collectDataForm() {
  const url = $("#src-url").value.trim();
  const mode = pressureMode();
  return {
    source_url: url || null,
    poll_interval_seconds: Math.max(1, Math.round(Number($("#src-interval").value) || 60)),
    field_time: url ? $("#src-time").value || null : null,
    field_temperature: url ? $("#src-temperature").value || null : null,
    field_humidity: url ? $("#src-humidity").value || null : null,
    pressure_mode: mode,
    pressure_kpa: mode === "fixed" ? numberOrNull($("#src-pressure-kpa").value) : null,
    field_pressure: mode === "field" ? $("#src-pressure-pointer").value || null : null,
    pressure_unit: $("#src-pressure-unit").value,
  };
}

function dataProblems(body) {
  const problems = [];
  if (body.source_url && !(body.field_temperature && body.field_humidity)) problems.push("choose the temperature and humidity fields");
  if (body.pressure_mode === "fixed" && (body.pressure_kpa === null || body.pressure_kpa < 20 || body.pressure_kpa > 200)) {
    problems.push("enter a fixed pressure between 20 and 200 kPa");
  }
  if (body.pressure_mode === "field" && !body.source_url) problems.push("pressure from the link needs a JSON link");
  if (body.pressure_mode === "field" && !body.field_pressure) problems.push("choose the pressure field");
  return problems;
}

function renderPreview() {
  const box = $("#src-preview");
  if (!box) return;
  const source = modalState.source;
  if (!source.url) {
    box.innerHTML = `<p class="hint">Paste a link to see what will be read.</p>`;
    return;
  }
  if (source.document === null) {
    box.innerHTML = `<p class="hint">${escapeHtml(source.error ? "Nothing to preview until the link can be read." : "Reading the link…")}</p>`;
    return;
  }
  const form = collectDataForm();
  const mapping = {
    time: form.field_time,
    temperature: form.field_temperature,
    humidity: form.field_humidity,
    pressure: form.pressure_mode === "field" ? form.field_pressure : null,
    pressure_unit: form.pressure_unit,
  };
  const { reading, errors } = fields.extract(source.document, mapping, source.readAt);
  const draft = {
    pressure_mode: form.pressure_mode,
    pressure_kpa: form.pressure_kpa,
    temperature_min: 0, temperature_max: 1, humidity_min: 0, humidity_max: 1, stage: "vegetative",
  };
  const computed = errors.length ? null : dss.stateFor(draft, reading);
  const pressure = computed?.pressure || dss.pressureFor(draft, reading);
  const cells = [
    ["Time", reading.measured_at ? timeLabel(reading.measured_at) : "—"],
    ["Temperature", `${number(reading.temperature_c, 1)} °C`],
    ["Humidity", `${number(reading.relative_humidity_percent, 1)} %`],
    ["Pressure", `${number(kpaFromPa(pressure.pa), 3)} kPa`],
    ["VPD", computed?.state ? `${number(kpaFromPa(computed.state.vapourPressureDeficit), 2)} kPa` : "—"],
  ];
  box.innerHTML = `
    <div class="grid preview-grid">${cells.map(([label, value]) => `<div class="tile"><span class="label">${label}</span><div class="value small">${escapeHtml(value)}</div></div>`).join("")}</div>
    ${errors.length ? `<ul class="problems">${errors.map((error) => `<li>${escapeHtml(`${error.field}: ${error.message}`)}</li>`).join("")}</ul>` : ""}
    ${computed?.error ? `<p class="bad-text">${escapeHtml(computed.error)}</p>` : ""}
    ${pressure.source === "standard-fallback" ? `<p class="hint">No pressure in this reading, so the standard atmosphere is used.</p>` : ""}
    <p class="hint">Refreshes every ${escapeHtml(String(collectDataForm().poll_interval_seconds))} s while this tab is open.</p>`;
}

function startPreviewTimer() {
  clearInterval(previewTimer);
  const seconds = Math.max(1, Number($("#src-interval")?.value) || 60);
  previewTimer = setInterval(() => {
    if ($("#profile-modal").hidden || !$("#tab-data")?.classList.contains("active")) return;
    if ($("#src-url")?.value.trim()) readSource(false);
  }, seconds * 1000);
}

async function saveProfile(profile, changes, message) {
  try {
    const updated = await api.updateProfile(profile.id, profileBody(profile, withoutFormFlags(changes)));
    mergeProfile(updated);
    if (state.profile?.id === updated.id) {
      geometryCache.clear();
      reassess();
      renderLive();
      startLive();
      await refreshViewData();
    }
    if (!$("#profile-modal").hidden && modalState.mode === "edit") {
      if (modalState.tab === "data") renderDataTab();
      if (modalState.tab === "crop") renderCropTab();
    }
    toast(message);
    return updated;
  } catch (error) {
    toast(error.message, true);
    return null;
  }
}

async function createProfileFromForm() {
  const name = $("#profile-name-input").value.trim();
  const crop = collectCropForm();
  const data = collectDataForm();
  const cropIssues = cropProblems(crop);
  const dataIssues = dataProblems(data);
  if (!name) { toast("Give the profile a name", true); $("#profile-name-input").focus(); return; }
  if (cropIssues.length) { toast(cropIssues.join("; "), true); switchModalTab("crop"); return; }
  if (dataIssues.length) { toast(dataIssues.join("; "), true); switchModalTab("data"); return; }
  try {
    const created = await api.addProfile({ name, ...withoutFormFlags(crop), ...data });
    state.profiles = await api.profiles();
    closeProfileModal();
    await selectProfile(state.profiles.find((item) => item.id === created.id));
    toast("Profile created");
  } catch (error) {
    toast(error.message, true);
  }
}

async function deleteProfile(profile) {
  if (!confirm(`Delete "${profile.name}" with its readings and rules?`)) return;
  try {
    await api.deleteProfile(profile.id);
    state.profiles = await api.profiles();
    closeProfileModal();
    if (state.profile?.id === profile.id) {
      if (state.profiles.length) await selectProfile(state.profiles[0]);
      else showNoProfile();
    }
    toast("Profile deleted");
  } catch (error) { toast(error.message, true); }
}

function showNoProfile() {
  clearInterval(state.timer);
  state.profile = null;
  state.latest = null;
  state.assessment = null;
  state.rules = [];
  renderChip();
  renderLive();
  renderRules();
  $("#advice-panel").innerHTML = `<div class="empty">${icon("psychiatry")}<h3>No profile yet</h3><p>A profile is one greenhouse: its crop, growth stage and JSON link.</p><button class="primary" id="empty-create">Create a profile</button></div>`;
  $("#empty-create").addEventListener("click", () => openProfileModal("add"));
  $("#mini-chart").textContent = "";
  $("#mini-trend").textContent = "";
}

function columnChecks(chosen, withDecisions) {
  const check = (item) => `
    <label class="check ${chosen.has(item.id) ? "on" : ""}">
      <input type="checkbox" value="${item.id}" ${chosen.has(item.id) ? "checked" : ""}>
      <span>${escapeHtml(item.label)}${item.unit ? ` (${escapeHtml(item.unit)})` : ""}</span>
    </label>`;
  return `
    <h3 class="section-title">Measured and calculated</h3>
    <div class="checks">${QUANTITIES.map(check).join("")}</div>
    ${withDecisions ? `<h3 class="section-title">Assessment</h3><div class="checks">${DECISIONS.map(check).join("")}</div>` : ""}`;
}

function bindChecks(host) {
  host.querySelectorAll(".check input").forEach((input) => {
    input.addEventListener("change", () => input.closest(".check").classList.toggle("on", input.checked));
  });
}

function chosenIn(host) {
  return [...host.querySelectorAll(".check input:checked")].map((input) => input.value);
}

function openColumnsModal() {
  $("#columns-form").innerHTML = `
    <p class="tip">Temperature and humidity are measured; every other value is calculated in this browser from them and the pressure. The assessment columns use the current bands and rules. The chart plots numbers only.</p>
    ${columnChecks(new Set(state.columns), true)}
    <div class="form-actions">
      <button class="ghost" data-close>Cancel</button>
      <button class="primary" id="columns-save">Save</button>
    </div>`;
  $("#columns-modal").hidden = false;
  bindChecks($("#columns-form"));
  $("#columns-save").addEventListener("click", async () => {
    const picked = chosenIn($("#columns-form"));
    if (!picked.length) { toast("Choose at least one column", true); return; }
    state.columns = picked;
    storageSet("psychromol.columns", JSON.stringify(picked));
    $("#columns-modal").hidden = true;
    await reloadData();
  });
}

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function exportValue(quantity, reading, computed) {
  const value = valueOf(quantity, reading, computed);
  if (!Number.isFinite(value)) return null;
  return quantity.measured ? value : Number(value.toFixed(6));
}

async function download(parameters, format, chosen) {
  const quantities = QUANTITIES.filter((quantity) => chosen.includes(quantity.id));
  const decisions = DECISIONS.filter((decision) => chosen.includes(decision.id));
  const rows = [];
  let offset = 0;
  let total = Infinity;
  while (offset < total) {
    const page = await api.readings(state.profile.id, { ...parameters, limit: EXPORT_PAGE, offset, order: "asc" });
    total = page.total;
    for (const reading of page.items) {
      const computed = stateOfReading(reading);
      const row = { measured_at: reading.measured_at };
      for (const quantity of quantities) row[quantity.key] = exportValue(quantity, reading, computed);
      if (decisions.length) {
        const decided = decisionValues(reading);
        for (const decision of decisions) row[decision.key] = decided[decision.id] || null;
      }
      rows.push(row);
    }
    offset += page.items.length;
    if (!page.items.length) break;
    if (total > EXPORT_PAGE) toast(`Preparing ${Math.min(offset, total)} of ${total} readings…`);
  }
  const keys = ["measured_at", ...quantities.map((quantity) => quantity.key), ...decisions.map((decision) => decision.key)];
  const profile = state.profile;
  const content = format === "json"
    ? JSON.stringify({
      profile: profile.name,
      crop: profile.crop_name,
      stage: stageLabel(profile),
      pressure: profile.pressure_mode,
      generated_at: new Date().toISOString(),
      readings: rows,
    }, null, 2)
    : [keys.join(","), ...rows.map((row) => keys.map((key) => csvCell(row[key])).join(","))].join("\n");
  const blob = new Blob([content], { type: format === "json" ? "application/json" : "text/csv" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${profile.name.replace(/[^\w.-]+/g, "_")}-${new Date().toISOString().slice(0, 10)}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 10000);
  toast(`${rows.length} readings downloaded`);
}

function openDownloadModal() {
  if (!state.profile) return;
  $("#download-form").innerHTML = `
    <div class="field-row">
      <label class="field">Range<select id="dl-range">
        <option value="current">The range shown</option>
        <option value="24">Last 24 hours</option>
        <option value="168">Last 7 days</option>
        <option value="720">Last 30 days</option>
        <option value="all">Everything</option>
      </select></label>
      <label class="field">Format<select id="dl-format">
        <option value="csv">CSV</option>
        <option value="json">JSON</option>
      </select></label>
    </div>
    <p class="tip">Values are calculated in this browser while the file is prepared; a long range at a fast fetch interval can take a while.</p>
    ${columnChecks(new Set(state.columns), true)}
    <div class="form-actions">
      <button class="ghost" data-close>Cancel</button>
      <button class="primary" id="dl-go">${icon("download")} Download</button>
    </div>`;
  $("#download-modal").hidden = false;
  bindChecks($("#download-form"));
  $("#dl-go").addEventListener("click", async () => {
    const chosen = chosenIn($("#download-form"));
    if (!chosen.length) { toast("Choose at least one column", true); return; }
    const range = $("#dl-range").value;
    const parameters = range === "current" ? rangeParameters() : range === "all" ? {} : { start: hoursAgo(Number(range)) };
    const format = $("#dl-format").value;
    $("#download-modal").hidden = true;
    try {
      await download(parameters, format, chosen);
    } catch (error) { toast(error.message, true); }
  });
}

function loadStoredColumns() {
  try {
    const stored = JSON.parse(storageGet("psychromol.columns") || "null");
    const known = new Set([...QUANTITIES, ...DECISIONS].map((item) => item.id));
    if (Array.isArray(stored)) {
      const valid = stored.filter((id) => known.has(id));
      if (valid.length) return valid;
    }
  } catch {}
  return [...DEFAULT_COLUMNS];
}

function wire() {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => showView(item.dataset.view));
  });
  $("#menu-toggle").addEventListener("click", () => {
    $("#sidebar").classList.toggle("open");
    $("#scrim").classList.toggle("open");
  });
  $("#scrim").addEventListener("click", closeMenu);

  $("#profile-chip").addEventListener("click", () => {
    if (state.profile) openProfileModal("edit", state.profile.id);
    else openProfileModal("add");
  });

  const closeModal = (modal) => {
    if (modal.id === "profile-modal") stopPreview();
    modal.hidden = true;
  };

  document.addEventListener("click", (event) => {
    const helper = event.target.closest("[data-help]");
    if (helper) {
      event.preventDefault();
      event.stopPropagation();
      openHelp(helper.dataset.help);
      return;
    }
    if (event.target.closest("[data-close]")) {
      closeModal(event.target.closest(".modal"));
      return;
    }
    const opener = event.target.closest("[data-open]");
    if (opener?.dataset.open === "columns") openColumnsModal();
    if (opener?.dataset.open === "download") openDownloadModal();
  }, true);

  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal(modal);
    });
  });

  $("#mini-switch").addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.miniKind = button.dataset.kind;
    $("#mini-switch").querySelectorAll("button").forEach((item) => item.classList.toggle("on", item === button));
    $("#mini-chart-title").textContent = state.miniKind === "mollier" ? "Mollier" : "Psychrometric";
    setChartHelp("#mini-chart-help", state.miniKind);
    await loadMiniChart();
  });

  $("#full-switch").addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    stopPlayback();
    state.fullKind = button.dataset.kind;
    $("#full-switch").querySelectorAll("button").forEach((item) => item.classList.toggle("on", item === button));
    setChartHelp("#full-chart-help", state.fullKind);
    charts.full?.destroy();
    charts.full = null;
    $("#full-chart").textContent = "";
    await loadFullChart().catch((error) => toast(error.message, true));
  });

  $("#chart-reset").addEventListener("click", () => charts.full?.reset());
  $("#history-play").addEventListener("click", () => {
    if (playback.timer) stopPlayback();
    else startPlayback();
  });
  $("#history-scrub").addEventListener("input", () => {
    if (playback.timer) stopPlayback();
    playbackFrame(Number($("#history-scrub").value));
  });

  $("#rule-add").addEventListener("click", () => openRuleModal(null));
  $("#rules-reset").addEventListener("click", resetRules);

  renderRangeControls();
  wireRangeControls();
  wireTable();
}

function guessServerUrl() {
  return `${location.protocol}//${location.hostname}:8888/api/v1`;
}

function openConnectModal(auto) {
  const current = api.getBase();
  $("#connect-url").value = current === "/api/v1" ? guessServerUrl() : current;
  $("#connect-status").textContent = auto
    ? "Could not reach a server at the default address. Enter the server's address below."
    : "";
  $("#connect-modal").hidden = false;
  $("#connect-url").focus();
}

function wireConnect() {
  $("#connect-btn").addEventListener("click", () => openConnectModal(false));
  $("#connect-save").addEventListener("click", async () => {
    const url = $("#connect-url").value.trim();
    if (!url) { $("#connect-status").textContent = "Enter a server address."; return; }
    $("#connect-status").textContent = "Connecting…";
    try {
      await api.probeBase(url);
      api.setBase(url);
      $("#connect-modal").hidden = true;
      toast("Connected");
      await boot();
    } catch (error) {
      $("#connect-status").textContent = `Could not connect: ${error.message}`;
    }
  });
}

async function boot() {
  try {
    state.profiles = await api.profiles();
  } catch (error) {
    toast(error.message, true);
    return;
  }
  state.columns = loadStoredColumns();
  const remembered = Number(storageGet("psychromol.profile"));
  const chosen = state.profiles.find((item) => item.id === remembered) || state.profiles[0];
  if (!chosen) {
    showNoProfile();
    openProfileModal("add");
    return;
  }
  await selectProfile(chosen);
}

async function start() {
  wire();
  wireConnect();
  try {
    await api.probeBase(api.getBase());
  } catch {
    openConnectModal(true);
    return;
  }
  await boot();
}

start();
