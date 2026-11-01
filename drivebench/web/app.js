"use strict";
const $ = id => document.getElementById(id);
let selected = null, active = null, catalogLoaded = false, submitting = false, lastHistory = "", lastRun = "", refreshBusy = false, simulationEnabled = true;
function element(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
async function api(path, options) { const res = await fetch(path, options); const data = await res.json(); if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`); return data; }
function showError(message) { $("error").textContent = message || ""; $("error").hidden = !message; }
function setBusy() { document.querySelectorAll("[data-scenario]").forEach(button => button.disabled = Boolean(active || submitting || !simulationEnabled)); $("run-all").firstChild.textContent = active || submitting ? "Suite in progress " : "Run full suite "; }
function formatTime(value) { return new Date(value).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"}); }
function renderCatalog(scenarios) {
  const container = $("scenarios"); container.replaceChildren();
  scenarios.forEach((scenario, index) => {
    const card = element("article", "scenario-card"), top = element("div", "card-top");
    top.append(element("span", "", `TC / ${String(index + 1).padStart(2, "0")}`), element("span", "", scenario.subsystem));
    const button = element("button", "card-run", "RUN SCENARIO ↗"); button.dataset.scenario = scenario.id; button.setAttribute("aria-label", `Run ${scenario.name}`);
    card.append(top, element("h3", "", scenario.name), element("p", "", scenario.description), button); container.append(card);
  }); catalogLoaded = true;
}
function renderTelemetry(simulator) {
  $("connection").textContent = simulator.enabled === false ? "Garage mode" : simulator.connected ? "Simulator connected" : "Simulator offline";
  $("connection-dot").classList.toggle("idle", simulator.enabled === false);
  $("lab-mode-note").hidden = simulator.enabled !== false;
  $("connection-dot").classList.toggle("connected", simulator.connected); $("endpoint").textContent = simulator.endpoint;
  const state = simulator.telemetry, signals = state?.sensors;
  [["temperature", "temperature_c", 160], ["voltage", "battery_v", 20], ["speed", "speed_kph", 240]].forEach(([id, key, max]) => {
    const value = signals?.[key]; $(id).textContent = Number.isFinite(value) ? value.toFixed(1) : "—";
    $(id + "-meter").style.width = `${Number.isFinite(value) ? Math.max(0, Math.min(100, value / max * 100)) : 0}%`;
  });
  $("ignition").textContent = `IGNITION ${state ? (state.ignition ? "ON" : "OFF") : "—"}`;
  $("fault-count").textContent = state ? String(state.active_faults.length).padStart(2, "0") : "—";
  $("faults").textContent = state ? state.active_faults.join(", ") || "No active faults" : "Simulator unavailable";
  $("stored").textContent = `Stored codes: ${state ? state.stored_faults.join(", ") || "none" : "—"}`;
}
function renderHistory(history) {
  const key = JSON.stringify([selected, history]); if (key === lastHistory) return; lastHistory = key;
  $("run-count").textContent = history.length; const container = $("history"); container.replaceChildren();
  if (!history.length) container.append(element("p", "muted", "Your test runs will appear here."));
  history.forEach(run => {
    const button = element("button", "history-item" + (selected === run.id ? " selected" : "")); button.setAttribute("aria-pressed", String(selected === run.id));
    button.append(element("span", "history-name", run.name)); const sub = element("span", "history-sub");
    sub.append(element("span", "", formatTime(run.started_at)), element("span", run.status, run.status.toUpperCase())); button.append(sub);
    button.addEventListener("click", () => { selected = run.id; lastRun = ""; refresh(); }); container.append(button);
  });
}
function renderRun(run) {
  const key = JSON.stringify(run); if (key === lastRun) return; lastRun = key;
  $("empty").hidden = true; $("run-content").hidden = false;
  $("run-status").className = `status ${run.status}`; $("run-status").textContent = run.status.toUpperCase();
  $("run-id").textContent = `RUN / ${run.id.slice(0, 12)}`; $("run-name").textContent = run.name;
  $("run-meta").textContent = `${formatTime(run.started_at)} · ${run.passed || 0} assertions passed · ${run.failed || 0} failed${run.duration_ms !== undefined ? ` · ${run.duration_ms.toFixed(0)} ms` : ""}`;
  $("exports").hidden = run.status === "running";
  $("download-json").href = `/api/runs/${run.id}/export.json`; $("download-xml").href = `/api/runs/${run.id}/junit.xml`;
  $("run-error").hidden = !run.error; $("run-error").textContent = run.error || "";
  const assertions = $("assertions"), trace = $("trace"); assertions.replaceChildren(); trace.replaceChildren(); let traceCount = 0;
  (run.results || []).forEach(result => {
    const group = element("div", "result-group"), heading = element("div", "result-heading");
    heading.append(element("span", "", result.name), element("span", "label", result.status)); group.append(heading);
    result.steps.forEach(step => {
      const row = element("div", `step ${step.status}`), description = element("div", "step-name", step.name);
      if (step.error) description.append(element("span", "step-error", step.error));
      if (step.observed) { const details = element("details", "observation"); details.append(element("summary", "", "Observed response"), element("pre", "", JSON.stringify(step.observed, null, 2))); description.append(details); }
      row.append(element("span", "step-icon", step.status === "passed" ? "✓" : "×"), description, element("small", "", `${step.duration_ms.toFixed(1)} ms`)); group.append(row);
    }); assertions.append(group);
    trace.append(element("p", "trace-scenario", result.name.toUpperCase()));
    result.trace.forEach(event => {
      traceCount++; const details = element("details", "trace-entry"), summary = element("summary");
      summary.append(element("span", "trace-direction" + (event.direction === "ERROR" ? " error" : ""), event.direction), element("span", "", event.payload.command || event.payload.error?.code || event.payload.type || (event.payload.ok ? "OK" : "REJECTED")), element("span", "trace-id", `${event.request_id.slice(0, 8)}${event.duration_ms !== null ? ` · ${event.duration_ms.toFixed(1)} ms` : ""}`));
      details.append(summary, element("pre", "", JSON.stringify(event, null, 2))); trace.append(details);
    });
  });
  if (run.status === "running") assertions.append(element("p", "running-note", `Running: ${run.current_scenario || "Preparing simulator"}…`));
  if (!(run.results || []).length && run.status !== "running") assertions.append(element("p", "muted", "No completed scenario results are available."));
  $("trace-count").textContent = traceCount;
}
async function refresh() {
  if (refreshBusy) return; refreshBusy = true;
  try {
    const status = await api("/api/status"); active = status.active_id; simulationEnabled = status.simulator.enabled; renderTelemetry(status.simulator);
    if (!catalogLoaded) renderCatalog(status.scenarios);
    if (!selected && status.history.length) selected = active || status.history[0].id;
    renderHistory(status.history); setBusy();
    if (selected) { const requested = selected, run = await api(`/api/runs/${requested}`); if (requested === selected) renderRun(run); }
    showError("");
  } catch (error) { showError(`Cannot refresh lab: ${error.message}. Check the server terminal.`); }
  finally { refreshBusy = false; }
}
document.addEventListener("click", async event => {
  const button = event.target.closest("[data-scenario]"); if (!button || button.disabled || submitting || active) return;
  submitting = true; setBusy(); showError("");
  try { const run = await api("/api/runs", {method: "POST", headers: {"Content-Type": "application/json", "X-DriveBench": "1"}, body: JSON.stringify({scenario: button.dataset.scenario})}); selected = run.id; active = run.id; lastRun = ""; renderRun(run); }
  catch (error) { showError(error.message); }
  finally { submitting = false; setBusy(); refresh(); }
});
function selectTab(name) { ["assertions", "trace"].forEach(id => { $(id).hidden = id !== name; $(id + "-tab").setAttribute("aria-selected", String(id === name)); $(id + "-tab").tabIndex = id === name ? 0 : -1; }); }
["assertions", "trace"].forEach(id => { $(id + "-tab").addEventListener("click", () => selectTab(id)); $(id + "-tab").addEventListener("keydown", event => { if (["ArrowLeft", "ArrowRight"].includes(event.key)) { event.preventDefault(); const next = id === "trace" ? "assertions" : "trace"; selectTab(next); $(next + "-tab").focus(); } }); });
selectTab("assertions"); refresh(); setInterval(refresh, 1000);
