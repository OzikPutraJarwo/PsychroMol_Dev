import { api } from "./api.js";
import { Chart } from "./chart.js";
import { Trend } from "./trend.js";

const $ = (selector) => document.querySelector(selector);

const PRIMARY = [
  { key: "temperature_c", label: "Temperature", unit: "°C", target: "temperature", digits: 1 },
  { key: "relative_humidity_percent", label: "Humidity", unit: "%", target: "relative_humidity", digits: 0 },
];

const PROPERTIES = [
  { key: "vpd_kpa", label: "VPD", unit: "kPa", digits: 2 },
  { key: "dew_point_c", label: "Dew point", unit: "°C", digits: 1 },
  { key: "dew_point_depression_k", label: "Dew point margin", unit: "K", digits: 1 },
  { key: "wet_bulb_c", label: "Wet bulb", unit: "°C", digits: 1 },
  { key: "humidity_ratio_g_kg", label: "Humidity ratio", unit: "g/kg", digits: 2 },
  { key: "enthalpy_kj_kg", label: "Enthalpy", unit: "kJ/kg", digits: 1 },
  { key: "absolute_humidity_g_m3", label: "Absolute humidity", unit: "g/m³", digits: 2 },
  { key: "specific_volume_m3_kg", label: "Specific volume", unit: "m³/kg", digits: 3 },
  { key: "density_kg_m3", label: "Density", unit: "kg/m³", digits: 3 },
  { key: "degree_of_saturation_percent", label: "Degree of saturation", unit: "%", digits: 1 },
  { key: "vapour_pressure_kpa", label: "Vapour pressure", unit: "kPa", digits: 3 },
  { key: "saturation_vapour_pressure_kpa", label: "Saturation pressure", unit: "kPa", digits: 3 },
];

const STATUS_ICON = {
  ok: "check_circle",
  info: "info",
  warning: "warning",
  critical: "e911_emergency",
};

const state = {
  meta: null,
  profiles: [],
  profile: null,
  current: null,
  rules: [],
  crops: [],
  facilities: [],
  view: "dashboard",
  miniKind: "psychrometric",
  fullKind: "psychrometric",
  range: { hours: 24, start: null, end: null },
  readings: null,
  dataColumns: ["temperature", "relative_humidity"],
  timer: null,
};

const charts = { mini: null, full: null, miniTrend: null, dataTrend: null };

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function number(value, digits) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function toast(message, bad = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("bad", bad);
  node.hidden = false;
  clearTimeout(node.dataset.timer);
  node.dataset.timer = setTimeout(() => { node.hidden = true; }, 3200);
}

function icon(name, extra = "") {
  return `<span class="icon ${extra}">${name}</span>`;
}

function showView(name) {
  state.view = name;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${name}`);
  });
  closeMenu();
  if (name === "chart") loadFullChart();
  if (name === "data") loadReadings();
  if (name === "rules") renderRules();
}

function closeMenu() {
  $("#sidebar").classList.remove("open");
  $("#scrim").classList.remove("open");
}

function renderCards() {
  const host = $("#primary-cards");
  const current = state.current;
  if (!current) {
    host.innerHTML = "";
    return;
  }
  const targets = current.targets || {};
  host.innerHTML = PRIMARY.map((entry) => {
    const value = current[entry.key];
    const band = targets[entry.target];
    let out = false;
    let note = "";
    if (band && typeof value === "number") {
      const low = band.min;
      const high = band.max;
      out = (low !== null && value < low) || (high !== null && value > high);
      note = `Target ${number(low, entry.digits)}–${number(high, entry.digits)} ${entry.unit}`;
    }
    return `<div class="card ${out ? "out" : ""}">
      <div class="label">${escapeHtml(entry.label)}</div>
      <div class="value">${number(value, entry.digits)}<small>${escapeHtml(entry.unit)}</small></div>
      <div class="target">${escapeHtml(note)}</div>
    </div>`;
  }).join("");
}

function renderPointDetail() {
  const host = $("#point-detail");
  const current = state.current;
  if (!current) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = `
    <div class="grid point-grid">
      ${PROPERTIES.map((entry) => `
        <div class="tile">
          <div class="label">${escapeHtml(entry.label)}</div>
          <div class="value">${number(current[entry.key], entry.digits)}<small>${escapeHtml(entry.unit)}</small></div>
        </div>`).join("")}
    </div>`;
}

function renderAction() {
  const host = $("#action-panel");
  const current = state.current;
  if (!current) {
    host.innerHTML = "";
    return;
  }
  const assessment = current.assessment;
  const status = assessment.status;
  const leading = assessment.matches.find((match) => match.name === assessment.headline)
    || assessment.matches[0];
  const detail = leading ? leading.recommendation : "No action needed right now.";

  host.innerHTML = `
    <div class="status ${escapeHtml(status)}">
      ${icon(STATUS_ICON[status] || "info")}
      <span class="status-body">
        <h3>${escapeHtml(assessment.headline)}</h3>
        <p>${escapeHtml(detail)}</p>
      </span>
    </div>`;
}

async function loadMiniChart() {
  if (!state.profile) return;
  if (!charts.mini) {
    charts.mini = new Chart($("#mini-chart"), {
      width: 560, height: 400, interactive: false,
    });
  }
  const geometry = await api.chart(state.profile.id, state.miniKind);
  charts.mini.setGeometry(geometry);
  charts.mini.setCurrent(state.current);
}

async function loadFullChart() {
  if (!state.profile) return;
  if (!charts.full) {
    charts.full = new Chart($("#full-chart"), { width: 880, height: 560 });
  }
  const geometry = await api.chart(state.profile.id, state.fullKind);
  charts.full.setGeometry(geometry);
  charts.full.setCurrent(state.current);
  await refreshChartHistory();
}

async function refreshChartHistory() {
  if (!state.profile || !charts.full) return;
  const payload = await api.readings(
    state.profile.id,
    "hours=24&fields=temperature&fields=relative_humidity&fields=humidity_ratio&fields=mollier_ordinate&fields=vpd"
  );
  stopPlayback();
  charts.full.setHistory(payload.readings);
  const scrub = $("#history-scrub");
  scrub.max = Math.max(0, payload.readings.length - 1);
  scrub.value = scrub.max;
}

const playback = { timer: null, index: 0 };

function stopPlayback() {
  if (playback.timer) clearInterval(playback.timer);
  playback.timer = null;
  const button = $("#history-play");
  if (button) button.innerHTML = `${icon("play_arrow")} Play history`;
  if (charts.full) charts.full.setPlaybackPoint(null);
  $("#history-scrub-time").textContent = "";
}

function playbackFrame(index) {
  const rows = charts.full ? charts.full.historyRows : [];
  if (!rows.length) return;
  const bounded = Math.max(0, Math.min(index, rows.length - 1));
  const row = rows[bounded];
  const mollier = charts.full.geometry && charts.full.geometry.mode === "mollier";
  const x = mollier ? row.humidity_ratio_g_kg : row.temperature_c;
  const y = mollier ? row.mollier_ordinate_kj_kg : row.humidity_ratio_g_kg;
  charts.full.setPlaybackPoint({ x, y });
  $("#history-scrub").value = bounded;
  $("#history-scrub-time").textContent = new Date(row.measured_at).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function startPlayback() {
  const rows = charts.full ? charts.full.historyRows : [];
  if (!rows.length) { toast("No history to play back yet", true); return; }
  playback.index = Number($("#history-scrub").value);
  if (playback.index >= rows.length - 1) playback.index = 0;
  $("#history-play").innerHTML = `${icon("pause")} Pause`;
  playback.timer = setInterval(() => {
    playbackFrame(playback.index);
    playback.index += 1;
    if (playback.index >= rows.length) stopPlayback();
  }, 150);
}

async function loadMiniTrend() {
  if (!state.profile) return;
  if (!charts.miniTrend) {
    charts.miniTrend = new Trend($("#mini-trend"), { width: 560, height: 400 });
  }
  const payload = await api.readings(
    state.profile.id,
    "hours=24&fields=temperature&fields=relative_humidity"
  );
  charts.miniTrend.setData(payload.readings, [
    { key: "temperature_c", label: "Temperature", unit: "°C" },
    { key: "relative_humidity_percent", label: "Humidity", unit: "%" },
  ]);
}

function rangeQuery(extra = []) {
  const parts = [...extra];
  if (state.range.start && state.range.end) {
    parts.push(`start=${encodeURIComponent(state.range.start)}`);
    parts.push(`end=${encodeURIComponent(state.range.end)}`);
  } else {
    parts.push(`hours=${state.range.hours}`);
  }
  return parts.join("&");
}

function fieldMeta(id) {
  return (state.meta?.fields || []).find((item) => item.id === id) || { id, label: id, unit: "" };
}

async function loadReadings() {
  if (!state.profile) return;
  const fieldParams = state.dataColumns.map((id) => `fields=${encodeURIComponent(id)}`);
  const payload = await api.readings(state.profile.id, rangeQuery(fieldParams));
  state.readings = payload;

  if (!charts.dataTrend) {
    charts.dataTrend = new Trend($("#data-trend"), { width: 880, height: 320 });
  }
  const columns = payload.fields.map((field) => ({
    key: field.key, label: fieldMeta(field.id).label, unit: field.unit,
  }));
  charts.dataTrend.setData(payload.readings, columns);

  const tableColumns = [{ key: "measured_at", label: "Time", unit: "" }, ...columns];
  const rows = payload.readings.slice(-200).reverse();
  $("#data-table").innerHTML = `
    <thead><tr>${tableColumns.map((column) =>
      `<th>${escapeHtml(column.label)}${column.unit ? ` (${escapeHtml(column.unit)})` : ""}</th>`
    ).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${tableColumns.map((column) => {
      if (column.key === "measured_at") {
        return `<td>${escapeHtml(new Date(row.measured_at).toLocaleString())}</td>`;
      }
      const value = row[column.key];
      return `<td>${typeof value === "number" ? value.toFixed(2) : "—"}</td>`;
    }).join("")}</tr>`).join("")}</tbody>`;

  const shown = Math.min(rows.length, 200);
  $("#data-summary").textContent =
    `${payload.count} readings in range. Showing the most recent ${shown}.`;
}

function conditionText(condition) {
  const metric = (state.meta?.metrics || []).find((item) => item.id === condition.metric);
  const label = metric ? metric.label : condition.metric;
  const unit = metric ? metric.unit : "";
  let right;
  if (condition.target) {
    const [name, edge] = condition.target.split(".");
    const metricName = (state.meta?.metrics || []).find((item) => item.id === name);
    right = `crop ${edge} ${metricName ? metricName.label.toLowerCase() : name}`;
    if (condition.offset) {
      right += ` ${condition.offset > 0 ? "+" : "−"} ${Math.abs(condition.offset)}`;
    }
  } else {
    right = `${condition.value} ${unit}`;
  }
  return `${label} ${condition.operator} ${right}`;
}

function renderRules() {
  const host = $("#rules-list");
  if (!state.rules.length) {
    host.innerHTML = `<div class="empty">
      ${icon("rule")}
      <h3>No rules yet</h3>
      <p>Rules turn the measured air into advice on the dashboard.</p>
      <button class="primary" id="rules-restore">Restore the default rules</button>
    </div>`;
    $("#rules-restore")?.addEventListener("click", resetRules);
    return;
  }
  host.innerHTML = `<div class="list">${state.rules.map((rule) => `
    <div class="list-item">
      <div class="grow">
        <div class="name">
          <span class="badge ${escapeHtml(rule.severity)}">${escapeHtml(rule.severity)}</span>
          ${escapeHtml(rule.name)}
          ${rule.enabled ? "" : '<span class="badge muted">off</span>'}
        </div>
        <div class="sub">${escapeHtml(rule.conditions.map(conditionText).join("  AND  "))}</div>
        <div class="sub">${escapeHtml(rule.recommendation)}</div>
      </div>
      <button class="icon-button" data-edit="${rule.id}">${icon("edit")}</button>
      <button class="icon-button" data-delete="${rule.id}">${icon("delete")}</button>
    </div>`).join("")}</div>`;

  host.querySelectorAll("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => openRuleModal(Number(button.dataset.edit)));
  });
  host.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const rule = state.rules.find((item) => item.id === Number(button.dataset.delete));
      if (!confirm(`Delete the rule "${rule.name}"?`)) return;
      await api.deleteRule(rule.id);
      state.rules = await api.rules();
      renderRules();
      toast("Rule deleted");
    });
  });
}

async function resetRules() {
  state.rules = await api.resetRules();
  renderRules();
  toast("Default rules restored");
}

let linkPollInFlight = false;

async function pollLinkedSource() {
  if (!state.profile?.source_url || linkPollInFlight) return;
  linkPollInFlight = true;
  try {
    await api.refresh(state.profile.id);
  } catch {
  } finally {
    linkPollInFlight = false;
  }
}

async function refreshCurrent() {
  if (!state.profile) return;
  try {
    state.current = await api.current(state.profile.id);
  } catch {
    state.current = null;
  }
  renderCards();
  renderPointDetail();
  renderAction();
  if (charts.mini) charts.mini.setCurrent(state.current);
  if (charts.full) charts.full.setCurrent(state.current);
}

function startLive() {
  if (state.timer) clearInterval(state.timer);
  const seconds = state.profile?.source_url
    ? state.profile.poll_interval_seconds || 60
    : 15;
  state.timer = setInterval(async () => {
    await pollLinkedSource();
    await refreshCurrent();
    if (state.view === "dashboard") loadMiniTrend().catch(() => {});
    if (state.view === "data") loadReadings().catch(() => {});
    if (state.view === "chart") refreshChartHistory().catch(() => {});
  }, seconds * 1000);
}

function renderChip() {
  if (!state.profile) {
    $("#chip-name").textContent = "No profile";
    $("#chip-sub").textContent = "Tap to set up";
    return;
  }
  $("#chip-name").textContent = state.profile.name;
  $("#chip-sub").textContent = state.profile.crop ? state.profile.crop.name : "";
}

function showEmptyDashboard(message) {
  $("#primary-cards").innerHTML = "";
  $("#point-detail").innerHTML = "";
  $("#action-panel").innerHTML = `<div class="empty">
    ${icon("inbox")}
    <h3>No readings yet</h3>
    <p>${escapeHtml(message)}</p>
    <button class="primary" id="empty-open">Open profile settings</button>
  </div>`;
  $("#empty-open")?.addEventListener("click", () => {
    if (state.profile) openProfileModal("edit", state.profile.id, "data");
    else openProfileModal("add");
  });
  $("#mini-chart").innerHTML = "";
  $("#mini-trend").innerHTML = "";
}

async function selectProfile(profile) {
  state.profile = profile;
  localStorage.setItem("psychromol.profile", String(profile.id));
  renderChip();
  startLive();
  await pollLinkedSource();
  await refreshCurrent();
  if (!state.current) {
    showEmptyDashboard("Add a data link or upload a file to start seeing readings.");
    return;
  }
  await Promise.all([loadMiniChart(), loadMiniTrend()]);
  if (state.view === "chart") loadFullChart();
  if (state.view === "data") loadReadings();
}

export { state };

const modalState = {
  mode: "edit",
  editingProfileId: null,
  addRendered: false,
  tab: "crop",
};

function editingProfile() {
  return state.profiles.find((item) => item.id === modalState.editingProfileId) || null;
}

function openProfileModal(mode, profileId = null, startTab = null) {
  modalState.mode = mode;
  modalState.editingProfileId = mode === "edit" ? (profileId ?? state.profile?.id ?? null) : null;
  if (mode === "edit" && !state.profiles.some((item) => item.id === modalState.editingProfileId)) {
    mode = "add";
    modalState.mode = "add";
    modalState.editingProfileId = null;
  }
  if (mode === "add") {
    modalState.addRendered = false;
  }
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
  document.querySelectorAll(".modal-nav-item").forEach((item) => {
    item.addEventListener("click", () => switchModalTab(item.dataset.tab));
  });
  switchModalTab(modalState.tab);
}

function switchModeHtml() {
  const rows = state.profiles.map((profile) => `
    <div class="list-item" data-switch-to="${profile.id}">
      <div class="grow">
        <div class="name">${escapeHtml(profile.name)}</div>
        <div class="sub">${escapeHtml(profile.crop?.name || "no crop")} · ${escapeHtml(profile.facility?.name || "no facility")}</div>
      </div>
      ${profile.id === modalState.editingProfileId ? '<span class="badge ok">current</span>' : ""}
      <span class="icon">chevron_right</span>
    </div>`).join("");

  return `
    <div class="modal-head">
      <h2>Switch profile</h2>
      <button class="icon-button" data-close><span class="icon">close</span></button>
    </div>
    <div class="modal-body">
      ${rows ? `<div class="list">${rows}</div>` : `<div class="empty">${icon("workspaces")}
        <h3>No other profiles</h3><p>Add a new one below.</p></div>`}
      <button class="primary" id="switch-add-new" style="margin-top:14px; width:100%; justify-content:center">
        ${icon("add")} Add new profile
      </button>
    </div>`;
}

function wireSwitchMode(card) {
  card.querySelectorAll("[data-switch-to]").forEach((row) => {
    row.addEventListener("click", async () => {
      const target = state.profiles.find((item) => item.id === Number(row.dataset.switchTo));
      await selectProfile(target);
      closeProfileModal();
    });
  });
  $("#switch-add-new").addEventListener("click", () => openProfileModal("add"));
}

function editorModeHtml(profile) {
  const title = `<input class="modal-title-input" id="profile-name-input"
    placeholder="Profile name" value="${escapeHtml(profile ? profile.name : "")}">`;
  const actions = profile
    ? `<button class="danger" id="profile-delete-btn">${icon("delete")} Delete</button>
       <button class="ghost" id="profile-switch-btn">${icon("swap_horiz")} Switch profile</button>`
    : `<button class="primary" id="profile-create-btn">${icon("add")} Create profile</button>`;
  return `
    <div class="modal-head">
      ${title}
      <div class="row">
        ${actions}
        <button class="icon-button" data-close><span class="icon">close</span></button>
      </div>
    </div>
    <div class="modal-body split">
      <nav class="modal-nav">
        <button class="modal-nav-item" data-tab="crop"><span class="icon">psychiatry</span><span>Crop</span></button>
        <button class="modal-nav-item" data-tab="facility"><span class="icon">home_work</span><span>Facility</span></button>
        <button class="modal-nav-item" data-tab="data"><span class="icon">cloud_download</span><span>Data</span></button>
      </nav>
      <div class="modal-pane">
        <div class="tab" id="tab-crop"></div>
        <div class="tab" id="tab-facility"></div>
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
      try {
        await api.updateProfile(profile.id, {
          name,
          crop_id: profile.crop_id,
          facility_id: profile.facility_id,
          source_url: profile.source_url,
          source_note: profile.source_note,
          is_default: profile.is_default,
        });
        await reloadCatalogue();
        if (state.profile && state.profile.id === profile.id) {
          state.profile = state.profiles.find((item) => item.id === profile.id);
          renderChip();
        }
        toast("Profile name saved");
      } catch (error) {
        toast(error.message, true);
        nameInput.value = profile.name;
      }
    });
  }
  $("#profile-switch-btn")?.addEventListener("click", () => {
    modalState.mode = "switch";
    renderProfileModal();
  });
  $("#profile-delete-btn")?.addEventListener("click", () => deleteProfile(profile));
  $("#profile-create-btn")?.addEventListener("click", () => createProfileFromForm());
}

async function createProfileFromForm() {
  const name = ($("#profile-name-input").value || "").trim() || "New profile";
  const cropBody = collectCropForm();
  const facilityBody = collectFacilityForm();
  if (!cropBody.name) {
    toast("Give the crop a name", true);
    switchModalTab("crop");
    return;
  }
  if (!facilityBody.name) {
    toast("Give the facility a name", true);
    switchModalTab("facility");
    return;
  }
  const sourceUrl = ($("#src-url")?.value || "").trim();
  const pollIntervalSeconds = Math.max(1, Number($("#src-preview-interval")?.value) || 60);
  try {
    const crop = await api.addCrop(cropBody);
    const facility = await api.addFacility(facilityBody);
    const created = await api.addProfile({
      name,
      crop_id: crop.id,
      facility_id: facility.id,
      source_url: sourceUrl || null,
      poll_interval_seconds: pollIntervalSeconds,
      is_default: state.profiles.length === 0,
    });
    await reloadCatalogue();
    await selectProfile(state.profiles.find((item) => item.id === created.id));
    modalState.mode = "edit";
    modalState.editingProfileId = created.id;
    modalState.tab = "data";
    renderProfileModal();
    toast("Profile created");
  } catch (error) {
    toast(error.message, true);
  }
}

function switchModalTab(tab) {
  modalState.tab = tab;
  document.querySelectorAll(".modal-nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.tab === tab);
  });
  document.querySelectorAll(".tab").forEach((pane) => {
    pane.classList.toggle("active", pane.id === `tab-${tab}`);
  });
  if (modalState.mode === "add") {
    // All three tabs stay in the DOM together in `add` mode, since the
    // single header "Create profile" button reads all of them at once
    // regardless of which one is currently visible. Rendering only the
    // active tab (as `edit` mode does) would wipe out whatever the user
    // typed into the other two the moment they switched away.
    if (!modalState.addRendered) {
      renderCropTab();
      renderFacilityTab();
      renderDataTab();
      modalState.addRendered = true;
    }
    return;
  }
  if (tab === "crop") renderCropTab();
  if (tab === "facility") renderFacilityTab();
  if (tab === "data") renderDataTab();
}

async function reloadCatalogue() {
  [state.crops, state.facilities, state.profiles] = await Promise.all([
    api.crops(), api.facilities(), api.profiles(),
  ]);
}

function targetRows(extra) {
  return extra.map((entry, index) => `
    <div class="condition-row" data-target-row="${index}">
      <select data-target-metric>${(state.meta?.metrics || [])
        .filter((metric) => !["temperature", "relative_humidity"].includes(metric.id))
        .map((metric) => `<option value="${metric.id}" ${metric.id === entry.metric ? "selected" : ""}>${escapeHtml(metric.label)}</option>`)
        .join("")}</select>
      <span class="mono">min</span>
      <input type="number" step="any" data-target-min value="${entry.min ?? ""}">
      <input type="number" step="any" data-target-max value="${entry.max ?? ""}">
      <button class="icon-button" data-remove-target="${index}">${icon("close")}</button>
    </div>`).join("");
}

function tabCrop() {
  return modalState.mode === "edit" ? editingProfile()?.crop || null : null;
}

function renderCropTab() {
  const host = $("#tab-crop");
  const crop = tabCrop();
  const extra = crop ? crop.extra_targets : [];
  const isAdd = modalState.mode === "add";

  host.innerHTML = `
    <div class="field-row">
      <label class="field">Name<input type="text" id="crop-name" value="${escapeHtml(crop?.name || "")}" placeholder="Tomato"></label>
    </div>
    <div class="field-row">
      <label class="field">Min temperature (°C)<input type="number" step="any" id="crop-tmin" value="${crop?.temperature_min ?? 18}"></label>
      <label class="field">Max temperature (°C)<input type="number" step="any" id="crop-tmax" value="${crop?.temperature_max ?? 28}"></label>
      <label class="field">Min humidity (%)<input type="number" step="any" id="crop-hmin" value="${crop?.humidity_min ?? 60}"></label>
      <label class="field">Max humidity (%)<input type="number" step="any" id="crop-hmax" value="${crop?.humidity_max ?? 80}"></label>
    </div>
    <h3 class="section-title">Other targets</h3>
    <div id="crop-targets">${targetRows(extra)}</div>
    <button class="ghost" id="crop-add-target">${icon("add")} Add target</button>
    ${isAdd ? "" : `<div class="form-actions"><button class="primary" id="crop-save">Save crop</button></div>`}`;

  $("#crop-add-target").addEventListener("click", () => {
    const rows = readTargets();
    rows.push({ metric: "vpd", min: null, max: null });
    $("#crop-targets").innerHTML = targetRows(rows);
    bindTargetRemoval();
  });
  bindTargetRemoval();

  if (isAdd) return;

  $("#crop-save").addEventListener("click", async () => {
    const body = collectCropForm();
    if (!body.name) { toast("Give the crop a name", true); return; }
    try {
      await api.updateCrop(crop.id, body);
      toast("Crop saved");
      await reloadCatalogue();
      if (state.profile && state.profile.id === modalState.editingProfileId) {
        state.profile = state.profiles.find((item) => item.id === state.profile.id);
        renderChip();
        await refreshCurrent();
        if (charts.mini) await loadMiniChart();
      }
      renderCropTab();
    } catch (error) { toast(error.message, true); }
  });
}

function collectCropForm() {
  return {
    name: $("#crop-name").value.trim(),
    temperature_min: Number($("#crop-tmin").value),
    temperature_max: Number($("#crop-tmax").value),
    humidity_min: Number($("#crop-hmin").value),
    humidity_max: Number($("#crop-hmax").value),
    extra_targets: readTargets(),
  };
}

function bindTargetRemoval() {
  document.querySelectorAll("[data-remove-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const rows = readTargets();
      rows.splice(Number(button.dataset.removeTarget), 1);
      $("#crop-targets").innerHTML = targetRows(rows);
      bindTargetRemoval();
    });
  });
}

function readTargets() {
  return [...document.querySelectorAll("[data-target-row]")].map((row) => {
    const min = row.querySelector("[data-target-min]").value;
    const max = row.querySelector("[data-target-max]").value;
    return {
      metric: row.querySelector("[data-target-metric]").value,
      min: min === "" ? null : Number(min),
      max: max === "" ? null : Number(max),
    };
  });
}

function tabFacility() {
  return modalState.mode === "edit" ? editingProfile()?.facility || null : null;
}

function renderFacilityTab() {
  const host = $("#tab-facility");
  const facility = tabFacility();
  const chosen = new Set(facility?.equipment || []);
  const isAdd = modalState.mode === "add";

  host.innerHTML = `
    <div class="field-row">
      <label class="field">Name<input type="text" id="fac-name" value="${escapeHtml(facility?.name || "")}" placeholder="House 1"></label>
      <label class="field">Altitude (m)<input type="number" step="any" id="fac-altitude" value="${facility?.altitude_m ?? 0}"></label>
    </div>
    <p class="tip">Altitude sets the air pressure every calculation uses. At 1000 m the humidity ratio is about 12 % higher than at sea level for the same reading.</p>
    <h3 class="section-title">Equipment</h3>
    <div class="checks">${(state.meta?.equipment || []).map((item) => `
      <label class="check ${chosen.has(item.id) ? "on" : ""}">
        <input type="checkbox" value="${item.id}" ${chosen.has(item.id) ? "checked" : ""}>
        <span>${escapeHtml(item.label)}</span>
      </label>`).join("")}</div>
    ${isAdd ? "" : `<div class="form-actions"><button class="primary" id="fac-save">Save facility</button></div>`}`;

  host.querySelectorAll(".check input").forEach((input) => {
    input.addEventListener("change", () => {
      input.closest(".check").classList.toggle("on", input.checked);
    });
  });

  if (isAdd) return;

  $("#fac-save").addEventListener("click", async () => {
    const body = collectFacilityForm();
    if (!body.name) { toast("Give the facility a name", true); return; }
    try {
      await api.updateFacility(facility.id, body);
      toast("Facility saved");
      await reloadCatalogue();
      if (state.profile && state.profile.id === modalState.editingProfileId) {
        state.profile = state.profiles.find((item) => item.id === state.profile.id);
        await refreshCurrent();
        if (charts.mini) await loadMiniChart();
      }
      renderFacilityTab();
    } catch (error) { toast(error.message, true); }
  });
}

function collectFacilityForm() {
  return {
    name: $("#fac-name").value.trim(),
    altitude_m: Number($("#fac-altitude").value) || 0,
    equipment: [...document.querySelectorAll("#tab-facility .check input:checked")].map((input) => input.value),
  };
}

const PREVIEW_ROWS_HTML = (rows) => rows.map((row) => `
  <tr><td>${escapeHtml(new Date(row.measured_at).toLocaleString())}</td>
  <td>${row.temperature}</td><td>${row.relative_humidity}</td></tr>`).join("");

function livePreviewHtml(intervalSeconds) {
  return `
    <div class="field-row">
      <label class="field" style="max-width:160px">Fetch every
        <input type="number" id="src-preview-interval" min="1" step="1" value="${intervalSeconds}"> s
      </label>
    </div>
    <div id="src-preview"></div>`;
}

let previewTimer = null;

function stopPreview() {
  if (previewTimer) {
    clearInterval(previewTimer);
    previewTimer = null;
  }
}

function renderPreviewResult(result) {
  if (!result.ok) {
    return `<p class="hint" style="color:var(--critical)">${escapeHtml(result.error)}</p>`;
  }
  return `
    <p class="hint">${result.count} reading${result.count === 1 ? "" : "s"} found${result.skipped ? `, ${result.skipped} skipped` : ""}.</p>
    ${result.rows.length ? `<div class="table-scroll"><table>
      <thead><tr><th>Time</th><th>Temp °C</th><th>RH %</th></tr></thead>
      <tbody>${PREVIEW_ROWS_HTML(result.rows)}</tbody>
    </table></div>` : ""}`;
}

function wireLivePreview() {
  const urlInput = $("#src-url");
  const intervalInput = $("#src-preview-interval");
  const box = $("#src-preview");
  if (!urlInput || !intervalInput || !box) return;

  const tick = async () => {
    if (!$("#tab-data")?.classList.contains("active")) return;
    const url = urlInput.value.trim();
    if (!url) { box.innerHTML = ""; return; }
    try {
      box.innerHTML = renderPreviewResult(await api.previewSource(url));
    } catch (error) {
      box.innerHTML = `<p class="hint" style="color:var(--critical)">${escapeHtml(error.message)}</p>`;
    }
  };

  const restart = () => {
    stopPreview();
    if (!urlInput.value.trim()) { box.innerHTML = ""; return; }
    tick();
    const seconds = Math.max(1, Number(intervalInput.value) || 1);
    previewTimer = setInterval(tick, seconds * 1000);
  };

  urlInput.addEventListener("input", restart);
  intervalInput.addEventListener("change", restart);
  restart();
}

function renderDataTab() {
  const host = $("#tab-data");
  stopPreview();

  if (modalState.mode === "add") {
    host.innerHTML = `
      <h3 class="section-title">Live link</h3>
      <p class="tip">Paste a link that returns JSON. The server reads it on the interval below and stores anything new. Each row needs a time, a temperature and a humidity — nothing else. You can also add data after creating the profile.</p>
      <div class="field-row">
        <label class="field">JSON link<input type="url" id="src-url" placeholder="https://example.com/greenhouse.json"></label>
      </div>
      ${livePreviewHtml(1)}`;
    wireLivePreview();
    return;
  }

  const profile = editingProfile();
  if (!profile) {
    host.innerHTML = `<div class="empty">${icon("cloud_off")}
      <h3>Choose a profile first</h3>
      <p>Data belongs to a profile.</p></div>`;
    return;
  }

  const polled = profile.last_polled_at
    ? `Last checked ${new Date(profile.last_polled_at).toLocaleString()}`
    : "Not checked yet";

  host.innerHTML = `
    <h3 class="section-title">Live link</h3>
    <p class="tip">Paste a link that returns JSON. The server reads it on the interval below and stores anything new. Each row needs a time, a temperature and a humidity — nothing else.</p>
    <div class="field-row">
      <label class="field">JSON link
        <input type="url" id="src-url" placeholder="https://example.com/greenhouse.json"
               value="${escapeHtml(profile.source_url || "")}">
      </label>
    </div>
    ${livePreviewHtml(profile.poll_interval_seconds)}
    <div class="row">
      <button class="primary" id="src-save">${icon("link")} Save link</button>
      <button class="ghost" id="src-refresh">${icon("refresh")} Fetch now</button>
      <span class="hint">${escapeHtml(polled)}</span>
    </div>
    ${profile.last_poll_error
      ? `<p class="hint" style="color:var(--critical)">${escapeHtml(profile.last_poll_error)}</p>` : ""}

    <h3 class="section-title">Upload a file</h3>
    <p class="tip">JSON or CSV, same three columns.</p>
    <div class="row">
      <input type="file" id="src-file" accept=".json,.csv,.txt">
      <button class="primary" id="src-upload">${icon("upload_file")} Upload</button>
    </div>

    <h3 class="section-title">Paste</h3>
    <textarea id="src-paste" placeholder='[{"timestamp": "2026-09-14T08:00:00Z", "temperature": 24.5, "humidity": 68}]'></textarea>
    <div class="form-actions">
      <button class="primary" id="src-paste-save">Add readings</button>
    </div>`;
  wireLivePreview();

  $("#src-save").addEventListener("click", async () => {
    const url = $("#src-url").value.trim();
    const pollIntervalSeconds = Math.max(1, Number($("#src-preview-interval").value) || 60);
    try {
      await api.updateProfile(profile.id, {
        name: profile.name,
        crop_id: profile.crop_id,
        facility_id: profile.facility_id,
        source_url: url || null,
        source_note: profile.source_note,
        poll_interval_seconds: pollIntervalSeconds,
        is_default: profile.is_default,
      });
      await reloadCatalogue();
      if (state.profile && state.profile.id === profile.id) {
        state.profile = state.profiles.find((item) => item.id === profile.id);
        startLive();
      }
      renderDataTab();
      toast("Link saved");
    } catch (error) { toast(error.message, true); }
  });

  $("#src-refresh").addEventListener("click", async () => {
    try {
      const result = await api.refresh(profile.id);
      await afterImport(result, profile.id);
    } catch (error) { toast(error.message, true); }
  });

  $("#src-upload").addEventListener("click", async () => {
    const file = $("#src-file").files[0];
    if (!file) { toast("Choose a file first", true); return; }
    const form = new FormData();
    form.append("file", file);
    try {
      await afterImport(await api.upload(profile.id, form), profile.id);
    } catch (error) { toast(error.message, true); }
  });

  $("#src-paste-save").addEventListener("click", async () => {
    const text = $("#src-paste").value.trim();
    if (!text) { toast("Paste some data first", true); return; }
    try {
      await afterImport(await api.paste(profile.id, { text, filename: "" }), profile.id);
      $("#src-paste").value = "";
    } catch (error) { toast(error.message, true); }
  });

}

async function deleteProfile(profile) {
  if (!confirm(`Delete "${profile.name}" and its readings?`)) return;
  await api.deleteProfile(profile.id);
  await reloadCatalogue();
  if (state.profile && state.profile.id === profile.id) {
    state.profile = state.profiles[0] || null;
    if (state.profile) await selectProfile(state.profile);
    else { renderChip(); showEmptyDashboard("Create a profile to begin."); }
  }
  closeProfileModal();
  toast("Profile deleted");
}

async function afterImport(result, profileId) {
  await reloadCatalogue();
  if (state.profile && state.profile.id === profileId) {
    state.profile = state.profiles.find((item) => item.id === profileId);
    await selectProfile(state.profile);
  }
  renderDataTab();
  toast(`${result.stored} stored, ${result.duplicates} already known`);
}

function ruleConditionRow(condition, index) {
  const metrics = state.meta?.metrics || [];
  const usesTarget = Boolean(condition.target);
  return `<div class="condition-row" data-rule-row="${index}">
    <select data-rule-metric>${metrics.map((metric) =>
      `<option value="${metric.id}" ${metric.id === condition.metric ? "selected" : ""}>${escapeHtml(metric.label)}</option>`
    ).join("")}</select>
    <select data-rule-operator>${(state.meta?.operators || []).map((operator) =>
      `<option value="${operator}" ${operator === condition.operator ? "selected" : ""}>${operator}</option>`
    ).join("")}</select>
    <select data-rule-kind>
      <option value="value" ${usesTarget ? "" : "selected"}>a number</option>
      <option value="target" ${usesTarget ? "selected" : ""}>crop target</option>
    </select>
    <input type="number" step="any" data-rule-number
           value="${usesTarget ? (condition.offset ?? "") : (condition.value ?? "")}"
           placeholder="${usesTarget ? "offset" : "value"}">
    <button class="icon-button" data-remove-rule-row="${index}">${icon("close")}</button>
    <select data-rule-target ${usesTarget ? "" : "hidden"} style="grid-column: 1 / -1">
      ${["temperature.min", "temperature.max", "relative_humidity.min", "relative_humidity.max",
         "vpd.min", "vpd.max"].map((target) =>
        `<option value="${target}" ${target === condition.target ? "selected" : ""}>crop ${target.replace(".", " ")}</option>`
      ).join("")}
    </select>
  </div>`;
}

function readRuleConditions() {
  return [...document.querySelectorAll("[data-rule-row]")].map((row) => {
    const kind = row.querySelector("[data-rule-kind]").value;
    const raw = row.querySelector("[data-rule-number]").value;
    const condition = {
      metric: row.querySelector("[data-rule-metric]").value,
      operator: row.querySelector("[data-rule-operator]").value,
    };
    if (kind === "target") {
      condition.target = row.querySelector("[data-rule-target]").value;
      if (raw !== "") condition.offset = Number(raw);
    } else {
      condition.value = raw === "" ? null : Number(raw);
    }
    return condition;
  });
}

function openRuleModal(ruleId) {
  const rule = ruleId ? state.rules.find((item) => item.id === ruleId) : null;
  const conditions = rule ? rule.conditions : [{ metric: "temperature", operator: ">", value: 30 }];

  $("#rule-modal-title").textContent = rule ? "Edit rule" : "New rule";
  $("#rule-form").innerHTML = `
    <div class="field-row">
      <label class="field">Name<input type="text" id="rule-name" value="${escapeHtml(rule?.name || "")}" placeholder="Too hot"></label>
      <label class="field">Severity<select id="rule-severity">${(state.meta?.severities || []).map((severity) =>
        `<option value="${severity}" ${severity === rule?.severity ? "selected" : ""}>${severity}</option>`).join("")}</select></label>
      <label class="field">Order<input type="number" id="rule-priority" value="${rule?.priority ?? 50}"></label>
    </div>
    <h3 class="section-title">All of these must be true</h3>
    <div id="rule-conditions">${conditions.map(ruleConditionRow).join("")}</div>
    <button class="ghost" id="rule-add-condition">${icon("add")} Add condition</button>
    <h3 class="section-title">Advice</h3>
    <textarea id="rule-recommendation" placeholder="Increase ventilation.">${escapeHtml(rule?.recommendation || "")}</textarea>
    <div class="field-row" style="margin-top:14px">
      <label class="field">Needs equipment
        <select id="rule-equipment">
          <option value="">any</option>
          ${(state.meta?.equipment || []).map((item) =>
            `<option value="${item.id}" ${item.id === rule?.requires_equipment ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
        </select></label>
      <label class="field">Enabled
        <select id="rule-enabled">
          <option value="yes" ${rule && !rule.enabled ? "" : "selected"}>yes</option>
          <option value="no" ${rule && !rule.enabled ? "selected" : ""}>no</option>
        </select></label>
    </div>
    <div class="form-actions">
      <button class="ghost" data-close>Cancel</button>
      <button class="primary" id="rule-save">${rule ? "Save rule" : "Create rule"}</button>
    </div>`;

  $("#rule-modal").hidden = false;
  bindRuleRows();

  $("#rule-add-condition").addEventListener("click", () => {
    const rows = readRuleConditions();
    rows.push({ metric: "relative_humidity", operator: ">", value: 80 });
    $("#rule-conditions").innerHTML = rows.map(ruleConditionRow).join("");
    bindRuleRows();
  });

  $("#rule-save").addEventListener("click", async () => {
    const body = {
      name: $("#rule-name").value.trim(),
      conditions: readRuleConditions(),
      severity: $("#rule-severity").value,
      recommendation: $("#rule-recommendation").value.trim(),
      requires_equipment: $("#rule-equipment").value || null,
      priority: Number($("#rule-priority").value) || 50,
      enabled: $("#rule-enabled").value === "yes",
    };
    if (!body.name) { toast("Give the rule a name", true); return; }
    try {
      if (rule) await api.updateRule(rule.id, body);
      else await api.addRule(body);
      state.rules = await api.rules();
      $("#rule-modal").hidden = true;
      renderRules();
      await refreshCurrent();
      toast(rule ? "Rule saved" : "Rule created");
    } catch (error) { toast(error.message, true); }
  });
}

function bindRuleRows() {
  document.querySelectorAll("[data-rule-row]").forEach((row) => {
    const kind = row.querySelector("[data-rule-kind]");
    const target = row.querySelector("[data-rule-target]");
    const numberInput = row.querySelector("[data-rule-number]");
    kind.addEventListener("change", () => {
      const usesTarget = kind.value === "target";
      target.hidden = !usesTarget;
      numberInput.placeholder = usesTarget ? "offset" : "value";
    });
  });
  document.querySelectorAll("[data-remove-rule-row]").forEach((button) => {
    button.addEventListener("click", () => {
      const rows = readRuleConditions();
      if (rows.length <= 1) { toast("A rule needs at least one condition", true); return; }
      rows.splice(Number(button.dataset.removeRuleRow), 1);
      $("#rule-conditions").innerHTML = rows.map(ruleConditionRow).join("");
      bindRuleRows();
    });
  });
}

function openDownloadModal() {
  const fields = state.meta?.fields || [];
  const chosen = new Set(state.dataColumns);
  $("#download-form").innerHTML = `
    <div class="field-row">
      <label class="field">Range<select id="dl-range">
        <option value="24">Last 24 hours</option>
        <option value="72">Last 3 days</option>
        <option value="168">Last 7 days</option>
        <option value="720">Last 30 days</option>
        <option value="current">The range shown</option>
      </select></label>
      <label class="field">Format<select id="dl-format">
        <option value="csv">CSV</option>
        <option value="json">JSON</option>
      </select></label>
    </div>
    <h3 class="section-title">Columns</h3>
    <div class="checks">${fields.map((field) => `
      <label class="check ${chosen.has(field.id) ? "on" : ""}">
        <input type="checkbox" value="${field.id}" ${chosen.has(field.id) ? "checked" : ""}>
        <span>${escapeHtml(field.label)}</span>
      </label>`).join("")}</div>
    <div class="form-actions">
      <button class="ghost" data-close>Cancel</button>
      <button class="primary" id="dl-go">${icon("download")} Download</button>
    </div>`;
  $("#download-modal").hidden = false;

  $("#download-form").querySelectorAll(".check input").forEach((input) => {
    input.addEventListener("change", () => {
      input.closest(".check").classList.toggle("on", input.checked);
    });
  });

  $("#dl-go").addEventListener("click", () => {
    const chosen = [...$("#download-form").querySelectorAll(".check input:checked")]
      .map((input) => `fields=${encodeURIComponent(input.value)}`);
    if (!chosen.length) { toast("Choose at least one column", true); return; }
    const range = $("#dl-range").value;
    const parts = [...chosen, `format=${$("#dl-format").value}`];
    if (range === "current") {
      if (state.range.start && state.range.end) {
        parts.push(`start=${encodeURIComponent(state.range.start)}`);
        parts.push(`end=${encodeURIComponent(state.range.end)}`);
      } else {
        parts.push(`hours=${state.range.hours}`);
      }
    } else {
      parts.push(`hours=${range}`);
    }
    window.location.href = api.exportUrl(state.profile.id, parts.join("&"));
    $("#download-modal").hidden = true;
  });
}

function openColumnsModal() {
  const fields = state.meta?.fields || [];
  const chosen = new Set(state.dataColumns);
  $("#columns-form").innerHTML = `
    <p class="tip">Choose which calculated values to show in the chart and table below. Temperature and humidity are the raw readings; everything else comes from the psychrometric engine.</p>
    <div class="checks">${fields.map((field) => `
      <label class="check ${chosen.has(field.id) ? "on" : ""}">
        <input type="checkbox" value="${field.id}" ${chosen.has(field.id) ? "checked" : ""}>
        <span>${escapeHtml(field.label)}</span>
      </label>`).join("")}</div>
    <div class="form-actions">
      <button class="ghost" data-close>Cancel</button>
      <button class="primary" id="columns-save">Save</button>
    </div>`;
  $("#columns-modal").hidden = false;

  $("#columns-form").querySelectorAll(".check input").forEach((input) => {
    input.addEventListener("change", () => {
      input.closest(".check").classList.toggle("on", input.checked);
    });
  });

  $("#columns-save").addEventListener("click", async () => {
    const picked = [...$("#columns-form").querySelectorAll(".check input:checked")]
      .map((input) => input.value);
    if (!picked.length) { toast("Choose at least one column", true); return; }
    state.dataColumns = picked;
    localStorage.setItem("psychromol.columns", JSON.stringify(picked));
    $("#columns-modal").hidden = true;
    await loadReadings();
  });
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
    if (event.target.closest("[data-close]")) {
      closeModal(event.target.closest(".modal"));
    }
  });

  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeModal(modal);
    });
  });

  $("#mini-switch").addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.miniKind = button.dataset.kind;
    $("#mini-switch").querySelectorAll("button").forEach((item) => {
      item.classList.toggle("on", item === button);
    });
    $("#mini-chart-title").textContent =
      state.miniKind === "mollier" ? "Mollier" : "Psychrometric";
    await loadMiniChart();
  });

  $("#full-switch").addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    stopPlayback();
    state.fullKind = button.dataset.kind;
    $("#full-switch").querySelectorAll("button").forEach((item) => {
      item.classList.toggle("on", item === button);
    });
    charts.full?.destroy();
    charts.full = null;
    $("#full-chart").textContent = "";
    await loadFullChart();
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

  $("#range-switch").addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    $("#range-switch").querySelectorAll("button").forEach((item) => {
      item.classList.toggle("on", item === button);
    });
    if (button.dataset.custom) {
      $("#custom-range").hidden = false;
      return;
    }
    $("#custom-range").hidden = true;
    state.range = { hours: Number(button.dataset.hours), start: null, end: null };
    await loadReadings();
  });

  $("#range-apply").addEventListener("click", async () => {
    const start = $("#range-start").value;
    const end = $("#range-end").value;
    if (!start || !end) { toast("Choose both dates", true); return; }
    state.range = {
      hours: null,
      start: new Date(start).toISOString(),
      end: new Date(end).toISOString(),
    };
    await loadReadings();
  });

  $("#download-open").addEventListener("click", openDownloadModal);
  $("#columns-open").addEventListener("click", openColumnsModal);
  $("#rule-add").addEventListener("click", () => openRuleModal(null));
  $("#rules-reset").addEventListener("click", resetRules);
}

function loadStoredColumns() {
  try {
    const stored = JSON.parse(localStorage.getItem("psychromol.columns") || "null");
    if (Array.isArray(stored) && stored.length) return stored;
  } catch {
    // ignore a corrupted value and fall through to the default
  }
  return null;
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
    state.meta = await api.meta();
    await reloadCatalogue();
    state.rules = await api.rules();
  } catch (error) {
    toast(error.message, true);
    return;
  }

  state.dataColumns =
    loadStoredColumns() || state.meta.default_display_fields || state.dataColumns;

  const remembered = Number(localStorage.getItem("psychromol.profile"));
  const chosen =
    state.profiles.find((item) => item.id === remembered) ||
    state.profiles.find((item) => item.is_default) ||
    state.profiles[0];

  if (!chosen) {
    renderChip();
    showEmptyDashboard("Create a crop, a facility and a profile to begin.");
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
