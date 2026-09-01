/* SocialAI Control Center frontend (T06).
 * Polls /api/state + /ws/dashboard, updates panels, wires actions.
 */
"use strict";

const $ = (sel) => document.querySelector(sel);

const QUICK_TEMPLATES = [
  { label: "Status", text: "ACTION: GET_STATUS" },
  { label: "Benchmark", text: "Please produce a short product benchmark line." },
  { label: "Health", text: "Reply with a single-line system health summary." },
];

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    throw new Error(`${path}: ${res.status}`);
  }
  return res.json();
}

function stateBadges(state) {
  const on = state.campaign && state.campaign.status === "RUNNING";
  const el = $("#badge-campaign");
  el.textContent = on ? "Campaign ON" : "Campaign OFF";
  el.classList.toggle("on", !!on);
}

function renderCampaign(state) {
  const camp = state.campaign;
  const box = $("#campaign-meta");
  if (!camp) {
    box.innerHTML = '<p class="muted">No campaign running.</p>';
    return;
  }
  const badge =
    camp.status === "RUNNING"
      ? '<span class="status busy">RUNNING</span>'
      : `<span class="status idle">${camp.status}</span>`;
  box.innerHTML = `
    <div class="kv-list">
      <li><span>Name</span><span>${camp.name} ${badge}</span></li>
      <li><span>Manifest</span><span>${camp.manifest}</span></li>
      <li><span>Target AI</span><span>${camp.target_recipient}</span></li>
    </div>`;
}

function renderWorkers(state) {
  const comps = state.components || {};
  const workers = Object.values(comps).filter((c) => c.kind === "worker_tab");
  const list = $("#worker-list");
  if (!workers.length) {
    list.innerHTML = '<li class="muted">No worker tabs attached.</li>';
    return;
  }
  list.innerHTML = workers
    .map(
      (w) =>
        `<li><span>${w.id} <span class="muted">(${w.assigned_ai || "-"})</span></span>` +
        `<span class="status ${(w.status || "IDLE").toLowerCase()}">${w.status || "IDLE"}` +
        `${w.used_by ? ` · by ${w.used_by}` : ""}</span></li>`
    )
    .join("");
}

function renderComponents(state) {
  const comps = Object.values(state.components || {});
  const list = $("#component-list");
  if (!comps.length) {
    list.innerHTML = '<li class="muted">No components registered.</li>';
    return;
  }
  list.innerHTML = comps
    .map(
      (c) =>
        `<li><span>${c.id} <span class="muted">(${c.kind})</span></span>` +
        `<span class="status ${(c.status || "IDLE").toLowerCase()}">${c.status || "IDLE"}</span></li>`
    )
    .join("");
}

function renderRecipients(state) {
  const comps = Object.keys(state.components || {});
  const sel = $("#relay-recipient");
  const target = state.campaign ? state.campaign.target_recipient : null;
  const keep = sel.value;
  sel.innerHTML = "";
  if (target) {
    const opt = document.createElement("option");
    opt.value = target;
    opt.textContent = `${target} (target)`;
    sel.appendChild(opt);
  }
  comps
    .filter((id) => id !== target)
    .forEach((id) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      sel.appendChild(opt);
    });
  const restore = [...sel.options].some((o) => o.value === keep);
  sel.value = restore ? keep : (sel.options[0] && sel.options[0].value) || "";
}

function renderRelay(state) {
  const log = $("#relay-log");
  const entries = state.relay || [];
  log.innerHTML = entries
    .slice(-30)
    .map((e) => {
      const replies = (e.replies || []).length
        ? `<div class="reply">↳ ${e.replies.map((r) => r).join(" | ")}</div>`
        : "";
      return `<div class="msg"><b>${e.from}</b> → ${e.to}: ${e.text}${replies}</div>`;
    })
    .join("");
  log.scrollTop = log.scrollHeight;
}

function render(state) {
  stateBadges(state);
  renderCampaign(state);
  renderWorkers(state);
  renderComponents(state);
  renderRecipients(state);
  renderRelay(state);
}

async function refresh() {
  try {
    const state = await api("/api/state");
    render(state);
    $("#badge-conn").textContent = "Connected & Registered";
    $("#badge-conn").classList.add("on");
  } catch {
    $("#badge-conn").textContent = "Disconnected";
    $("#badge-conn").classList.remove("on");
  }
}

function openSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/dashboard`);
  ws.onmessage = (ev) => {
    try {
      render(JSON.parse(ev.data));
      $("#badge-conn").textContent = "Connected & Registered";
      $("#badge-conn").classList.add("on");
    } catch {
      /* ignore malformed push */
    }
  };
  ws.onclose = () => setTimeout(openSocket, 3000);
}

async function refreshManifests() {
  try {
    const names = await api("/api/manifests");
    const sel = $("#manifest-select");
    sel.innerHTML = "";
    names.forEach((n) => {
      const opt = document.createElement("option");
      opt.value = n;
      opt.textContent = n;
      sel.appendChild(opt);
    });
    if (names.length) sel.value = names[0];
  } catch {
    /* service not up yet */
  }
}

function wireActions() {
  $("#btn-launch").addEventListener("click", async () => {
    const name = $("#manifest-select").value;
    if (!name) return;
    await api(`/api/campaigns/${name}/launch`, { method: "POST" });
    refresh();
  });

  $("#btn-stop").addEventListener("click", async () => {
    await api("/api/campaigns/stop", { method: "POST" });
    refresh();
  });

  $("#btn-relay").addEventListener("click", async () => {
    const text = $("#relay-input").value.trim();
    if (!text) return;
    const recipient = $("#relay-recipient").value || null;
    await api("/api/relay", {
      method: "POST",
      body: JSON.stringify({ text, sender: "operator", recipient }),
    });
    $("#relay-input").value = "";
    refresh();
  });

  $("#relay-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#btn-relay").click();
  });

  const tplBox = $("#template-buttons");
  QUICK_TEMPLATES.forEach((t) => {
    const btn = document.createElement("button");
    btn.textContent = t.label;
    btn.addEventListener("click", () => {
      api("/api/relay", {
        method: "POST",
        body: JSON.stringify({ text: t.text, sender: "operator", recipient: null }),
      }).then(refresh);
    });
    tplBox.appendChild(btn);
  });
}

refreshManifests();
refresh();
setInterval(refresh, 3000);
wireActions();
openSocket();
