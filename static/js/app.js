// Segundo Cérebro — frontend (vanilla JS, sem dependências externas)
"use strict";

const state = {
  view: "notas",       // notas | ideia | jogo | livro | grafo
  query: "",
  tag: "",
  currentNoteId: null,
  types: {},
  listCache: [],
  sortKey: null,
  sortDir: 1,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(path, opts) {
  const res = await fetch(path, Object.assign(
    { headers: { "Content-Type": "application/json" } }, opts || {}
  ));
  if (!res.ok && res.status !== 404) {
    throw new Error(`Erro ${res.status} em ${path}`);
  }
  return res.json();
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2200);
}

// ---------------------------------------------------------------- boot
async function boot() {
  state.types = await api("/api/types");
  await Promise.all([loadTags(), loadStats()]);
  bindGlobalEvents();
  setView("notas");
}

function bindGlobalEvents() {
  $$(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });

  $("#btn-new-nota").addEventListener("click", () => createQuick("nota"));
  $("#btn-new-jogo").addEventListener("click", () => createQuick("jogo"));
  $("#btn-new-livro").addEventListener("click", () => createQuick("livro"));

  let searchTimer;
  $("#search-input").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value;
    searchTimer = setTimeout(() => {
      state.query = q;
      loadList();
    }, 220);
  });

  $("#btn-save").addEventListener("click", saveCurrentNote);
  $("#btn-delete").addEventListener("click", deleteCurrentNote);

  $$(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  $("#editor-preview").addEventListener("click", onPreviewClick);
}

// ---------------------------------------------------------------- nav / view
function setView(view) {
  state.view = view;
  state.sortKey = null;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === view));

  const titles = { notas: "Todas as notas", ideia: "Ideias", jogo: "Jogos", livro: "Livros", grafo: "Grafo" };
  $("#list-title").textContent = titles[view] || "";

  const app = $("#app");
  if (view === "grafo") {
    app.classList.add("grafo-mode");
    $("#list-pane").classList.add("hidden");
    showGraph();
  } else {
    app.classList.remove("grafo-mode");
    $("#list-pane").classList.remove("hidden");
    loadList();
  }
}

// ---------------------------------------------------------------- tags
async function loadTags() {
  const tags = await api("/api/tags");
  const box = $("#tags-list");
  box.innerHTML = "";
  Object.entries(tags).forEach(([tag, count]) => {
    const chip = document.createElement("button");
    chip.className = "tag-chip" + (state.tag === tag ? " active" : "");
    chip.textContent = `${tag} · ${count}`;
    chip.addEventListener("click", () => {
      state.tag = state.tag === tag ? "" : tag;
      loadTags();
      loadList();
    });
    box.appendChild(chip);
  });
}

async function loadStats() {
  const s = await api("/api/stats");
  const byType = Object.entries(s.by_type || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
  $("#stats").textContent = `${s.total} notas · ${s.tags} tags\n${byType}`;
}

// ---------------------------------------------------------------- lista
async function loadList() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.tag) params.set("tag", state.tag);
  if (["ideia", "jogo", "livro"].includes(state.view)) params.set("type", state.view);

  const notes = await api(`/api/notes?${params.toString()}`);
  state.listCache = notes;

  if (["jogo", "livro"].includes(state.view) && !state.query) {
    renderTable(notes, state.view);
  } else {
    renderCards(notes);
  }
}

function renderCards(notes) {
  const body = $("#list-body");
  body.innerHTML = "";
  if (!notes.length) {
    body.innerHTML = `<div class="empty-list">Nada por aqui ainda.</div>`;
    return;
  }
  notes.forEach((n) => {
    const card = document.createElement("div");
    card.className = "note-card" + (n.id === state.currentNoteId ? " active" : "");
    const typeLabel = (state.types[n.type] || {}).label || n.type;
    card.innerHTML = `
      <div class="nc-title">${escapeHtml(n.title)}</div>
      <div class="nc-excerpt">${escapeHtml(n.excerpt || "")}</div>
      <div class="nc-meta">
        <span class="badge">${escapeHtml(typeLabel)}</span>
        ${(n.tags || []).slice(0, 4).map((t) => `<span class="badge">#${escapeHtml(t)}</span>`).join("")}
      </div>`;
    card.addEventListener("click", () => openNote(n.id));
    body.appendChild(card);
  });
}

function renderTable(notes, type) {
  const body = $("#list-body");
  const cfg = state.types[type];
  const cols = [{ key: "title", label: "Título" }].concat(
    (cfg.fields || []).map((f) => ({ key: f.key, label: f.label }))
  );

  if (state.sortKey) {
    const dir = state.sortDir;
    notes = notes.slice().sort((a, b) => {
      const va = fieldValue(a, state.sortKey);
      const vb = fieldValue(b, state.sortKey);
      if (va == null) return 1;
      if (vb == null) return -1;
      return va > vb ? dir : va < vb ? -dir : 0;
    });
  }

  if (!notes.length) {
    body.innerHTML = `<div class="empty-list">Nada por aqui ainda. Use "+ ${cfg.label}" na barra lateral.</div>`;
    return;
  }

  const table = document.createElement("table");
  table.className = "data-table";
  table.innerHTML = `
    <thead><tr>${cols.map((c) => `<th data-key="${c.key}">${escapeHtml(c.label)}</th>`).join("")}</tr></thead>
    <tbody></tbody>`;
  const tbody = table.querySelector("tbody");

  notes.forEach((n) => {
    const tr = document.createElement("tr");
    tr.innerHTML = cols.map((c) => `<td>${renderCell(n, c.key)}</td>`).join("");
    tr.addEventListener("click", () => openNote(n.id));
    tbody.appendChild(tr);
  });

  table.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      state.sortDir = state.sortKey === key ? -state.sortDir : 1;
      state.sortKey = key;
      renderTable(state.listCache, state.view);
    });
  });

  body.innerHTML = "";
  body.appendChild(table);
}

function fieldValue(note, key) {
  if (key === "title") return note.title.toLowerCase();
  const v = (note.frontmatter || {})[key];
  return v === undefined || v === null || v === "" ? null : v;
}

function renderCell(note, key) {
  if (key === "title") return escapeHtml(note.title);
  const v = (note.frontmatter || {})[key];
  if (v === undefined || v === null || v === "") return `<span style="color:var(--text-muted)">—</span>`;
  if (key === "nota") return `<span class="stars">${"★".repeat(Math.round(v))}${"☆".repeat(10 - Math.round(v))}</span> <span style="color:var(--text-muted)">${v}/10</span>`;
  return escapeHtml(String(v));
}

// ---------------------------------------------------------------- editor
async function openNote(id) {
  const note = await api(`/api/notes/${encodeURIComponent(id)}`);
  if (note.error) { toast("Nota não encontrada"); return; }
  state.currentNoteId = note.id;

  $("#empty-state").classList.add("hidden");
  $("#graph-canvas").classList.add("hidden");
  $("#editor").classList.remove("hidden");

  $("#editor-title").value = note.title;
  $("#editor-tags").value = (note.tags || []).join(", ");
  $("#editor-body").value = note.body || "";
  $("#editor-preview").innerHTML = note.html || "";

  renderFields(note);
  renderBacklinks(note.backlinks || []);
  switchTab("editar");

  $$(".note-card").forEach((c) => c.classList.remove("active"));
  loadListHighlight(id);
}

function loadListHighlight(id) {
  $$(".note-card").forEach((c) => {});
  // re-render highlight cheaply by re-running current cache render if cards mode
  if (!["jogo", "livro"].includes(state.view) || state.query) {
    renderCards(state.listCache.map((n) => n));
  }
}

function renderFields(note) {
  const cfg = state.types[note.type] || { fields: [] };
  const box = $("#fields-box");
  box.innerHTML = "";
  (cfg.fields || []).forEach((f) => {
    const wrap = document.createElement("div");
    wrap.className = "field-item";
    const value = (note.frontmatter || {})[f.key];
    let input;
    if (f.type === "select") {
      input = document.createElement("select");
      (f.options || []).forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        if (opt === value) o.selected = true;
        input.appendChild(o);
      });
    } else {
      input = document.createElement("input");
      input.type = (f.type === "number" || f.type === "rating") ? "number" : "text";
      if (f.type === "rating") { input.min = 0; input.max = f.max || 10; }
      if (value !== undefined && value !== null) input.value = value;
    }
    input.dataset.fieldKey = f.key;
    const label = document.createElement("label");
    label.textContent = f.label;
    wrap.appendChild(label);
    wrap.appendChild(input);
    box.appendChild(wrap);
  });
}

function renderBacklinks(backlinks) {
  const box = $("#backlinks-list");
  box.innerHTML = "";
  if (!backlinks.length) {
    box.innerHTML = `<div class="no-backlinks">Nenhuma nota linka para esta ainda.</div>`;
    return;
  }
  backlinks.forEach((n) => {
    const div = document.createElement("div");
    div.className = "backlink-item";
    div.textContent = `← ${n.title}`;
    div.addEventListener("click", () => openNote(n.id));
    box.appendChild(div);
  });
}

function switchTab(tab) {
  $$(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  if (tab === "editar") {
    $("#editor-body").classList.remove("hidden");
    $("#editor-preview").classList.add("hidden");
  } else {
    renderPreviewLive();
    $("#editor-body").classList.add("hidden");
    $("#editor-preview").classList.remove("hidden");
  }
}

async function renderPreviewLive() {
  const body = $("#editor-body").value;
  const res = await api("/api/render", { method: "POST", body: JSON.stringify({ body }) });
  $("#editor-preview").innerHTML = res.html;
}

function onPreviewClick(e) {
  const a = e.target.closest("a.wikilink");
  if (!a) return;
  e.preventDefault();
  const targetId = a.dataset.targetId;
  const targetTitle = a.dataset.targetTitle;
  if (targetId) {
    openNote(targetId);
  } else if (confirm(`A nota "${targetTitle}" ainda não existe. Criar agora?`)) {
    createAndOpen(targetTitle, "nota");
  }
}

async function createQuick(type) {
  const cfg = state.types[type];
  const title = prompt(`Título d${type === "jogo" ? "o" : "a"} nov${type === "jogo" ? "o" : "a"} ${cfg.label.toLowerCase()}:`);
  if (!title || !title.trim()) return;
  await createAndOpen(title.trim(), type);
}

async function createAndOpen(title, type) {
  const note = await api("/api/notes", {
    method: "POST",
    body: JSON.stringify({ title, type }),
  });
  await Promise.all([loadTags(), loadStats()]);
  if (["nota", "ideia", "jogo", "livro"].includes(type)) {
    if (state.view !== type && !(type === "nota" && state.view === "notas")) {
      // mantém a view atual, só recarrega a lista em segundo plano
    }
  }
  await loadList();
  openNote(note.id);
  toast("Criado!");
}

async function saveCurrentNote() {
  if (!state.currentNoteId) return;
  const title = $("#editor-title").value.trim() || "Sem título";
  const body = $("#editor-body").value;
  const tags = $("#editor-tags").value.split(",").map((t) => t.trim()).filter(Boolean);

  const frontmatter = { tags };
  $$("#fields-box [data-field-key]").forEach((input) => {
    let v = input.value;
    if (input.type === "number" && v !== "") v = Number(v);
    if (v === "") v = null;
    frontmatter[input.dataset.fieldKey] = v;
  });

  const updated = await api(`/api/notes/${encodeURIComponent(state.currentNoteId)}`, {
    method: "PUT",
    body: JSON.stringify({ title, body, frontmatter }),
  });

  state.currentNoteId = updated.id; // pode mudar se o arquivo for renomeado no futuro
  $("#editor-preview").innerHTML = updated.html;
  await Promise.all([loadTags(), loadStats(), loadList()]);
  toast("Salvo ✓");
}

async function deleteCurrentNote() {
  if (!state.currentNoteId) return;
  if (!confirm("Apagar esta nota para sempre?")) return;
  await api(`/api/notes/${encodeURIComponent(state.currentNoteId)}`, { method: "DELETE" });
  state.currentNoteId = null;
  $("#editor").classList.add("hidden");
  $("#empty-state").classList.remove("hidden");
  await Promise.all([loadTags(), loadStats(), loadList()]);
  toast("Apagado");
}

// ---------------------------------------------------------------- grafo
async function showGraph() {
  $("#empty-state").classList.add("hidden");
  $("#editor").classList.add("hidden");
  const canvas = $("#graph-canvas");
  canvas.classList.remove("hidden");
  const data = await api("/api/graph");
  runGraph(canvas, data);
}

function runGraph(canvas, data) {
  const dpr = window.devicePixelRatio || 1;
  const resize = () => {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
  };
  resize();
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const W = () => canvas.width / dpr;
  const H = () => canvas.height / dpr;

  const colors = { nota: "#6a4fd6", ideia: "#3fa796", jogo: "#e0824a", livro: "#4a90d9" };

  const nodes = data.nodes.map((n) => ({
    ...n,
    x: W() / 2 + (Math.random() - 0.5) * 200,
    y: H() / 2 + (Math.random() - 0.5) * 200,
    vx: 0, vy: 0,
  }));
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const edges = data.edges.filter((e) => byId[e.source] && byId[e.target]);

  let dragging = null;
  let running = true;

  function tick() {
    const w = W(), h = H();
    // repulsão
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = a.x - b.x, dy = a.y - b.y;
        let dist2 = dx * dx + dy * dy || 0.01;
        let force = 1800 / dist2;
        let dist = Math.sqrt(dist2);
        dx /= dist; dy /= dist;
        a.vx += dx * force; a.vy += dy * force;
        b.vx -= dx * force; b.vy -= dy * force;
      }
    }
    // atração pelas arestas
    edges.forEach((e) => {
      const a = byId[e.source], b = byId[e.target];
      let dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (dist - 110) * 0.01;
      dx /= dist; dy /= dist;
      a.vx += dx * force; a.vy += dy * force;
      b.vx -= dx * force; b.vy -= dy * force;
    });
    // centro + amortecimento + integração
    nodes.forEach((n) => {
      if (n === dragging) return;
      n.vx += (w / 2 - n.x) * 0.0015;
      n.vy += (h / 2 - n.y) * 0.0015;
      n.vx *= 0.85; n.vy *= 0.85;
      n.x += n.vx; n.y += n.vy;
      n.x = Math.max(20, Math.min(w - 20, n.x));
      n.y = Math.max(20, Math.min(h - 20, n.y));
    });
  }

  function draw() {
    ctx.clearRect(0, 0, W(), H());
    ctx.strokeStyle = "rgba(150,140,160,0.35)";
    ctx.lineWidth = 1;
    edges.forEach((e) => {
      const a = byId[e.source], b = byId[e.target];
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    });
    nodes.forEach((n) => {
      ctx.beginPath();
      ctx.fillStyle = colors[n.type] || "#888";
      ctx.arc(n.x, n.y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--text") || "#333";
      ctx.font = "12px sans-serif";
      ctx.fillText(n.title, n.x + 10, n.y + 4);
    });
  }

  function loop() {
    if (!running) return;
    tick();
    draw();
    requestAnimationFrame(loop);
  }
  loop();

  function pos(evt) {
    const rect = canvas.getBoundingClientRect();
    return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  }
  function findNode(p) {
    return nodes.find((n) => Math.hypot(n.x - p.x, n.y - p.y) < 12);
  }

  canvas.onmousedown = (e) => {
    const p = pos(e);
    const n = findNode(p);
    if (n) { dragging = n; canvas.style.cursor = "grabbing"; }
  };
  canvas.onmousemove = (e) => {
    if (dragging) {
      const p = pos(e);
      dragging.x = p.x; dragging.y = p.y; dragging.vx = 0; dragging.vy = 0;
    }
  };
  window.addEventListener("mouseup", () => { dragging = null; canvas.style.cursor = "grab"; });
  canvas.ondblclick = (e) => {
    const n = findNode(pos(e));
    if (n) openNote(n.id);
  };
  window.addEventListener("resize", resize);

  // pausa a simulação quando sai da view de grafo (evita loops infinitos escondidos)
  const observer = new MutationObserver(() => {
    if (canvas.classList.contains("hidden")) { running = false; observer.disconnect(); }
  });
  observer.observe(canvas, { attributes: true, attributeFilter: ["class"] });
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

boot();
