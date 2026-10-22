(() => {
  const DEFAULT_API = "https://upae-ff1k.onrender.com";
  const DEFAULT_LIMIT = 50;
  const MAX_LIMIT = 300;
  const PAGE_SIZE = 300;
  const SOFT_CAP = 5000;

  const form = document.getElementById("search-form");
  const hint = document.getElementById("form-hint");
  const submitBtn = document.getElementById("submit-btn");
  const exampleBtn = document.getElementById("example-btn");
  const clearBtn = document.getElementById("clear-btn");
  const topBtn = document.getElementById("top-btn");
  const statusEl = document.getElementById("status");
  const resultsEl = document.getElementById("results");
  const sectionNav = document.getElementById("section-nav");
  const sectionNavList = document.getElementById("section-nav-list");
  let sectionScrollBound = false;

  topBtn?.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    history.replaceState(null, "", window.location.pathname + window.location.search);
  });

  /** @type {{ cancel: boolean, busy: boolean, ctx: object | null }} */
  const paging = { cancel: false, busy: false, ctx: null };

  /** @type {Array<{name:string,rank:string,t_age:number,b_age:number,color:string}>|null} */
  let icsIntervals = null;
  let icsLoadPromise = null;
  const CHRONO_RANKS = ["Eon", "Era", "Period", "Epoch", "Age"];
  const PHANEROZOIC_OLDER = 541;
  /** @type {{ full: boolean, payload: object | null }} */
  const agesChartState = { full: false, payload: null };

  function loadIcsIntervals() {
    if (icsIntervals) return Promise.resolve(icsIntervals);
    if (!icsLoadPromise) {
      icsLoadPromise = fetch("./ics-intervals.json?v=geo-ranks-v1")
        .then((r) => (r.ok ? r.json() : { intervals: [] }))
        .then((j) => {
          icsIntervals = Array.isArray(j.intervals) ? j.intervals : [];
          return icsIntervals;
        })
        .catch(() => {
          icsIntervals = [];
          return icsIntervals;
        });
    }
    return icsLoadPromise;
  }

  loadIcsIntervals();

  function numOrNull(v) {
    if (v === "" || v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function queryAgeBounds(data, query) {
    const gts = data?.query?.gts_normalized_age || {};
    let younger = numOrNull(gts.age_min_ma);
    let older = numOrNull(gts.age_max_ma);
    if (younger == null) younger = numOrNull(query?.ageMin);
    if (older == null) older = numOrNull(query?.ageMax);
    if (younger != null && older != null && younger > older) {
      const tmp = younger;
      younger = older;
      older = tmp;
    }
    return { younger, older };
  }

  function intervalContains(iv, age) {
    const lo = Math.min(iv.t_age, iv.b_age);
    const hi = Math.max(iv.t_age, iv.b_age);
    return age >= lo && age <= hi;
  }

  function nameAtChronoRank(ageMa, rank, intervals) {
    if (ageMa == null || !Number.isFinite(ageMa) || !intervals?.length) return null;
    const hits = intervals.filter((i) => i.rank === rank && intervalContains(i, ageMa));
    if (!hits.length) return null;
    hits.sort(
      (a, b) => Math.abs(a.b_age - a.t_age) - Math.abs(b.b_age - b.t_age) || a.name.localeCompare(b.name)
    );
    return hits[0].name;
  }

  /** Resolve Eon→Age; ranges become "Oligocene–Pliocene" when bounds differ. */
  function resolveChronostratRange(older, younger, intervals) {
    const hi = older != null ? older : younger;
    const lo = younger != null ? younger : older;
    if (hi == null || !intervals?.length) return null;
    const out = {};
    for (const rank of CHRONO_RANKS) {
      const nOld = nameAtChronoRank(hi, rank, intervals);
      const nYoung = nameAtChronoRank(lo, rank, intervals);
      if (!nOld && !nYoung) continue;
      out[rank] = nOld && nYoung && nOld !== nYoung ? `${nOld}–${nYoung}` : nOld || nYoung;
    }
    return Object.keys(out).length ? out : null;
  }

  function formatMaPair(older, younger) {
    if (older == null && younger == null) return "";
    if (older != null && younger != null) {
      if (older === younger) return `${older} Ma`;
      return `${older}–${younger} Ma`;
    }
    if (older != null) return `${older} Ma`;
    return `${younger} Ma`;
  }

  function chronostratPlainListHtml(older, younger, intervals, heading) {
    const chrono = resolveChronostratRange(older, younger, intervals);
    if (!chrono && older == null && younger == null) return "";
    const maLine = formatMaPair(older, younger);
    const ranksHtml = chrono
      ? `<ol class="taxonomy-tree chrono-tree">${CHRONO_RANKS.filter((r) => chrono[r])
          .map(
            (r) =>
              `<li><span class="tax-rank">${esc(r)}</span> <span class="tax-name">${esc(
                chrono[r]
              )}</span></li>`
          )
          .join("")}</ol>`
      : "";
    return `<div class="chrono-plain">
      ${heading ? `<p class="sub">${esc(heading)}</p>` : ""}
      ${maLine ? `<p class="chrono-ma">${esc(maLine)}</p>` : ""}
      ${ranksHtml}
    </div>`;
  }

  function chronostratTaxonomyHtml(data, query, intervals) {
    const { younger, older } = queryAgeBounds(data, query);
    if (younger == null && older == null) return "";
    return chronostratPlainListHtml(older, younger, intervals, "Chronostratigraphy");
  }

  function collectAgeLayers(data, query) {
    const bounds = queryAgeBounds(data, query);
    const pbdb = [];
    for (const f of data.occurrences?.features || []) {
      const p = f.properties || {};
      if ((p.database_source || "").toUpperCase() !== "PBDB") continue;
      let older = numOrNull(p.max_ma);
      let younger = numOrNull(p.min_ma);
      if (older == null && younger == null) continue;
      if (older == null) older = younger;
      if (younger == null) younger = older;
      if (younger > older) {
        const t = younger;
        younger = older;
        older = t;
      }
      pbdb.push({
        older,
        younger,
        label: p.taxon_name || p.accepted_name || "PBDB",
      });
    }
    const macro = [];
    for (const u of data.geology?.macrostrat_units || []) {
      let older = numOrNull(u.age_bottom_ma);
      let younger = numOrNull(u.age_top_ma);
      if (older == null && younger == null) continue;
      if (older == null) older = younger;
      if (younger == null) younger = older;
      if (younger > older) {
        const t = younger;
        younger = older;
        older = t;
      }
      macro.push({
        older,
        younger,
        label: u.unit_name || "Unit",
      });
    }
    return { bounds, pbdb, macro };
  }

  function agesDomain(layers, full) {
    if (full) return { older: PHANEROZOIC_OLDER, younger: 0 };
    const ages = [];
    if (layers.bounds.older != null) ages.push(layers.bounds.older);
    if (layers.bounds.younger != null) ages.push(layers.bounds.younger);
    for (const r of layers.pbdb) {
      ages.push(r.older, r.younger);
    }
    for (const r of layers.macro) {
      ages.push(r.older, r.younger);
    }
    if (!ages.length) return { older: PHANEROZOIC_OLDER, younger: 0 };
    let older = Math.max(...ages);
    let younger = Math.min(...ages);
    const pad = Math.max((older - younger) * 0.08, 0.5);
    older = Math.min(PHANEROZOIC_OLDER, older + pad);
    younger = Math.max(0, younger - pad);
    if (older - younger < 1) {
      older = Math.min(PHANEROZOIC_OLDER, older + 0.5);
      younger = Math.max(0, younger - 0.5);
    }
    return { older, younger };
  }

  function icsColumnBands(rank, intervals, younger, older, yOf, x, width, showLabels) {
    const spanMin = Math.max((older - younger) * 0.02, 0.05);
    return (intervals || [])
      .filter((i) => i.rank === rank)
      .map((i) => {
        const top = Math.max(younger, Math.min(i.t_age, i.b_age));
        const bot = Math.min(older, Math.max(i.t_age, i.b_age));
        if (bot <= top) return "";
        const y1 = yOf(top);
        const y2 = yOf(bot);
        const h = Math.max(1, y2 - y1);
        const label =
          showLabels && h >= 12
            ? `<text x="${x + width / 2}" y="${y1 + Math.min(h / 2 + 3, h - 2)}" text-anchor="middle" class="ages-band-label">${esc(
                i.name
              )}</text>`
            : "";
        return `<rect x="${x}" y="${y1}" width="${width}" height="${h}" fill="${esc(
          i.color
        )}" stroke="rgba(12,18,16,0.4)" stroke-width="0.4">
          <title>${esc(i.name)} · ${esc(i.b_age)}–${esc(i.t_age)} Ma</title>
        </rect>${label}`;
      })
      .join("");
  }

  function overlayRange(x, width, y1, y2, fill, stroke, title) {
    const top = Math.min(y1, y2);
    const h = Math.max(2, Math.abs(y2 - y1));
    return `<rect x="${x}" y="${top}" width="${width}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width="1.25" rx="2">
      <title>${esc(title)}</title>
    </rect>`;
  }

  /** Multi-column ICS chronostrat chart (CGMW colors) with range overlays. */
  function buildAgesChartSvg(layers, intervals, full) {
    const { older, younger } = agesDomain(layers, full);
    const span = older - younger || 1;
    const padT = 22;
    const padB = 32;
    const H = 480;
    const plotTop = padT;
    const plotH = H - padT - padB;
    const yOf = (age) => plotTop + ((age - younger) / span) * plotH;

    const cols = [
      { rank: "Eon", w: 44 },
      { rank: "Era", w: 52 },
      { rank: "Period", w: 70 },
      { rank: "Epoch", w: 78 },
      { rank: "Age", w: span <= 80 ? 86 : 0 },
    ].filter((c) => c.w > 0);

    let x = 8;
    const headers = [];
    const bands = [];
    for (const col of cols) {
      headers.push(
        `<text x="${x + col.w / 2}" y="${padT - 8}" text-anchor="middle" class="ages-track-label">${esc(
          col.rank
        )}</text>`
      );
      bands.push(
        icsColumnBands(col.rank, intervals, younger, older, yOf, x, col.w, col.rank !== "Age" || span <= 40)
      );
      x += col.w + 2;
    }

    const chartRight = x + 6;
    const axisX = chartRight;
    const ticks = [];
    const niceSteps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100];
    let step = 10;
    for (const s of niceSteps) {
      if (span / s <= 9) {
        step = s;
        break;
      }
    }
    const startTick = Math.ceil(younger / step) * step;
    for (let a = startTick; a <= older + 1e-9; a += step) {
      const y = yOf(a);
      ticks.push(
        `<line x1="${axisX}" y1="${y}" x2="${axisX + 5}" y2="${y}" stroke="rgba(232,239,230,0.4)"/>
         <text x="${axisX + 8}" y="${y + 3}" class="ages-tick">${esc(Number(a.toFixed(4)))}</text>`
      );
    }

    let trackX = axisX + 44;
    const trackW = 36;
    const trackGap = 14;
    const overlays = [];

    if (layers.bounds.older != null || layers.bounds.younger != null) {
      const qOld = layers.bounds.older ?? layers.bounds.younger;
      const qYoung = layers.bounds.younger ?? layers.bounds.older;
      overlays.push(
        `<text x="${trackX + trackW / 2}" y="${padT - 8}" text-anchor="middle" class="ages-track-label">Query</text>`
      );
      overlays.push(
        overlayRange(
          trackX,
          trackW,
          yOf(qYoung),
          yOf(qOld),
          "rgba(224,164,90,0.45)",
          "#e0a45a",
          `Query ${formatMaPair(qOld, qYoung)}`
        )
      );
      // Highlight band across ICS columns
      overlays.push(
        overlayRange(
          8,
          chartRight - 14,
          yOf(qYoung),
          yOf(qOld),
          "rgba(224,164,90,0.12)",
          "rgba(224,164,90,0.35)",
          `Query ${formatMaPair(qOld, qYoung)}`
        )
      );
      trackX += trackW + trackGap;
    }

    if (layers.pbdb.length) {
      overlays.push(
        `<text x="${trackX + trackW / 2}" y="${padT - 8}" text-anchor="middle" class="ages-track-label">PBDB</text>`
      );
      layers.pbdb.forEach((r, i) => {
        const inset = layers.pbdb.length > 1 ? (i / (layers.pbdb.length - 1 || 1)) * (trackW - 8) : trackW / 2 - 2;
        const xx = trackX + 4 + inset;
        overlays.push(`<line x1="${xx}" y1="${yOf(r.younger)}" x2="${xx}" y2="${yOf(r.older)}" stroke="#6fbfa6" stroke-width="2.4" stroke-linecap="round">
          <title>${esc(r.label)} ${esc(formatMaPair(r.older, r.younger))}</title>
        </line>`);
      });
      trackX += trackW + trackGap;
    }

    if (layers.macro.length) {
      overlays.push(
        `<text x="${trackX + trackW / 2}" y="${padT - 8}" text-anchor="middle" class="ages-track-label">Macrostrat</text>`
      );
      layers.macro.forEach((r, i) => {
        const inset = layers.macro.length > 1 ? (i / (layers.macro.length - 1 || 1)) * (trackW - 8) : trackW / 2 - 2;
        const xx = trackX + 4 + inset;
        overlays.push(`<line x1="${xx}" y1="${yOf(r.younger)}" x2="${xx}" y2="${yOf(r.older)}" stroke="#c4d4c8" stroke-width="2.4" stroke-linecap="round">
          <title>${esc(r.label)} ${esc(formatMaPair(r.older, r.younger))}</title>
        </line>`);
      });
      trackX += trackW + trackGap;
    }

    const usedW = Math.max(620, trackX + 8);
    return `<svg class="ages-svg" viewBox="0 0 ${usedW} ${H}" role="img" aria-label="ICS chronostratigraphic chart with age overlays">
      ${headers.join("")}
      ${bands.join("")}
      <rect x="8" y="${plotTop}" width="${chartRight - 14}" height="${plotH}" fill="none" stroke="rgba(232,239,230,0.2)"/>
      <line x1="${axisX}" y1="${plotTop}" x2="${axisX}" y2="${plotTop + plotH}" stroke="rgba(232,239,230,0.35)"/>
      ${ticks.join("")}
      ${overlays.join("")}
      <text x="8" y="${H - 10}" class="ages-caption">ICS chronostratigraphy (CGMW colors) · older ↓</text>
    </svg>`;
  }

  function agesPlainTextBlocks(layers, intervals) {
    const blocks = [];
    if (layers.bounds.older != null || layers.bounds.younger != null) {
      blocks.push(
        chronostratPlainListHtml(
          layers.bounds.older,
          layers.bounds.younger,
          intervals,
          "Query age"
        )
      );
    }
    // Summarize PBDB as union span + per-row labels when few
    if (layers.pbdb.length) {
      const older = Math.max(...layers.pbdb.map((r) => r.older));
      const younger = Math.min(...layers.pbdb.map((r) => r.younger));
      blocks.push(chronostratPlainListHtml(older, younger, intervals, `PBDB fossils (${layers.pbdb.length})`));
      if (layers.pbdb.length <= 8) {
        const rows = layers.pbdb
          .map((r) => {
            const chrono = resolveChronostratRange(r.older, r.younger, intervals);
            const stage = chrono?.Age || chrono?.Epoch || "—";
            return `<li><span class="chrono-ma">${esc(formatMaPair(r.older, r.younger))}</span>
              <span class="item-meta"> · ${esc(stage)} · ${esc(r.label)}</span></li>`;
          })
          .join("");
        blocks.push(`<ul class="list chrono-occ-list">${rows}</ul>`);
      }
    }
    if (layers.macro.length) {
      const older = Math.max(...layers.macro.map((r) => r.older));
      const younger = Math.min(...layers.macro.map((r) => r.younger));
      blocks.push(
        chronostratPlainListHtml(older, younger, intervals, `Macrostrat units (${layers.macro.length})`)
      );
    }
    return blocks.filter(Boolean).join("");
  }

  function agesSectionHtml(data, query, intervals) {
    const layers = collectAgeLayers(data, query);
    const hasQuery = layers.bounds.older != null || layers.bounds.younger != null;
    const hasAny = hasQuery || layers.pbdb.length > 0 || layers.macro.length > 0;
    if (!hasAny) {
      return `<p class="empty">No numeric ages to plot (needs query bounds, PBDB Ma, or Macrostrat units).</p>`;
    }
    agesChartState.payload = { layers, intervals };
    const svg = buildAgesChartSvg(layers, intervals, agesChartState.full);
    const legend = [
      hasQuery ? `<span class="ages-leg query">Query bounds</span>` : "",
      layers.pbdb.length ? `<span class="ages-leg pbdb">PBDB · ${layers.pbdb.length}</span>` : "",
      layers.macro.length
        ? `<span class="ages-leg macro">Macrostrat · ${layers.macro.length}</span>`
        : "",
    ]
      .filter(Boolean)
      .join("");
    const plain = agesPlainTextBlocks(layers, intervals);
    return `<div class="ages-toolbar">
        <button type="button" class="linkish" id="ages-full-toggle">${
          agesChartState.full ? "Zoom to data" : "Full Phanerozoic"
        }</button>
        <div class="ages-legend">${legend}</div>
      </div>
      <div id="ages-chart-host" class="ages-chart-host">${svg}</div>
      <p class="ages-attribution item-meta">Interval names &amp; colours follow the ICS chronostratigraphic chart (CGMW colouring via Macrostrat international timescales).</p>
      <div class="ages-plain-wrap">${plain}</div>`;
  }

  function wireAgesChartToggle() {
    const btn = document.getElementById("ages-full-toggle");
    if (!btn || !agesChartState.payload) return;
    btn.addEventListener("click", () => {
      agesChartState.full = !agesChartState.full;
      const host = document.getElementById("ages-chart-host");
      if (host) {
        host.innerHTML = buildAgesChartSvg(
          agesChartState.payload.layers,
          agesChartState.payload.intervals,
          agesChartState.full
        );
      }
      btn.textContent = agesChartState.full ? "Zoom to data" : "Full Phanerozoic";
    });
  }

  function patchNeotomaDiagnostic(data, status, error, recordCount) {
    const diags = data.diagnostics || [];
    const idx = diags.findIndex((d) => d.provider === "NEOTOMA");
    const row = {
      provider: "NEOTOMA",
      status,
      error: error || null,
      record_count: recordCount || 0,
      elapsed_ms: null,
    };
    if (idx >= 0) diags[idx] = { ...diags[idx], ...row };
    else diags.push(row);
    data.diagnostics = diags;
  }

  async function fetchDeferredNeotoma(apiBase, query, data) {
    const waiting = (data.diagnostics || []).some(
      (d) => d.provider === "NEOTOMA" && d.status === "waiting"
    );
    if (!waiting) return;
    if (!query?.taxon) {
      patchNeotomaDiagnostic(data, "skipped", "taxon required", 0);
      renderStatus(data);
      return;
    }

    renderStatus(data);
    try {
      const qs = new URLSearchParams({
        provider: "NEOTOMA",
        taxon: query.taxon,
        limit: String(query.limit || DEFAULT_LIMIT),
      });
      if (query.lat !== "" && query.lat != null) qs.set("lat", query.lat);
      if (query.lng !== "" && query.lng != null) qs.set("lng", query.lng);
      if (query.radius !== "" && query.radius != null) qs.set("radius_km", query.radius);
      if (query.ageMin) qs.set("age_min", query.ageMin);
      if (query.ageMax) qs.set("age_max", query.ageMax);

      const resp = await fetch(`${apiBase}/api/v1/occurrences?${qs.toString()}`);
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok || body.status === "error") {
        patchNeotomaDiagnostic(
          data,
          "error",
          body.detail || body.error || `HTTP ${resp.status}`,
          0
        );
        renderStatus(data);
        return;
      }

      const feats = (Array.isArray(body.features) ? body.features : []).filter((f) => {
        const p = f?.properties || {};
        const coords = f?.geometry?.coordinates;
        const hasCoords = Array.isArray(coords) && coords.length >= 2;
        const hasName = Boolean(p.taxon_name || p.accepted_name);
        const hasId = Boolean(p.occurrence_id);
        return hasCoords && (hasName || hasId);
      });
      data.occurrences = data.occurrences || { features: [], source_totals: [] };
      data.occurrences.features = [...(data.occurrences.features || []), ...feats];

      const totals = data.occurrences.source_totals || [];
      const ti = totals.findIndex((s) => s.provider === "NEOTOMA");
      const neoTotal = { provider: "NEOTOMA", returned: feats.length, total: null };
      if (ti >= 0) totals[ti] = neoTotal;
      else totals.push(neoTotal);
      data.occurrences.source_totals = totals;

      // Recompute available total from source_totals (prefer upstream totals).
      data.occurrences.total_records = totals.reduce((sum, s) => {
        if (s.total != null && Number.isFinite(Number(s.total))) return sum + Number(s.total);
        return sum + (Number(s.returned) || 0);
      }, 0);

      patchNeotomaDiagnostic(
        data,
        "ok",
        feats.length ? null : "No Neotoma occurrences for this taxon",
        feats.length
      );
      renderStatus(data);

      const tbody = document.getElementById("occ-tbody");
      if (tbody && feats.length) {
        tbody.insertAdjacentHTML("beforeend", feats.map(occRowHtml).join(""));
      }
      const progress = document.getElementById("occ-progress");
      if (progress) {
        const n = (data.occurrences.features || []).length;
        progress.innerHTML = `Showing <strong>${n.toLocaleString()}</strong> loaded occurrence(s) (Neotoma updated)`;
      }
      if (paging.ctx) paging.ctx.loadedRows = (data.occurrences.features || []).length;
    } catch (err) {
      patchNeotomaDiagnostic(data, "error", String(err.message || err), 0);
      renderStatus(data);
    }
  }

  function resolveApiBase() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = (params.get("api") || "").trim().replace(/\/$/, "");
    return fromQuery || DEFAULT_API;
  }

  function fieldIds() {
    return ["taxon", "lat", "lng", "radius_km", "age_min", "age_max", "limit"];
  }

  exampleBtn.addEventListener("click", () => {
    document.getElementById("taxon").value = "Canis dirus";
    document.getElementById("lat").value = "34.05";
    document.getElementById("lng").value = "-118.25";
    document.getElementById("radius_km").value = "500";
    document.getElementById("age_min").value = "";
    document.getElementById("age_max").value = "";
    document.getElementById("limit").value = String(DEFAULT_LIMIT);
  });

  clearBtn.addEventListener("click", () => {
    paging.cancel = true;
    paging.busy = false;
    paging.ctx = null;
    for (const id of fieldIds()) {
      const el = document.getElementById(id);
      if (!el) continue;
      el.value = id === "limit" ? String(DEFAULT_LIMIT) : "";
    }
    const loadAll = document.getElementById("load_all");
    if (loadAll) loadAll.checked = false;
    hint.textContent = "Provide a taxon/mineral and/or lat + lng.";
    hint.classList.remove("error");
    statusEl.hidden = true;
    statusEl.innerHTML = "";
    resultsEl.hidden = true;
    resultsEl.innerHTML = "";
    hideSectionNav();
    document.getElementById("taxon").focus();
  });

  /** Read only the typed value — never the placeholder attribute. */
  function fieldValue(id) {
    const el = document.getElementById(id);
    if (!el) return "";
    const raw = el.value;
    if (raw == null) return "";
    return String(raw).trim();
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hint.textContent = "";
    hint.classList.remove("error");
    paging.cancel = true;
    paging.busy = false;

    const taxon = fieldValue("taxon");
    const lat = fieldValue("lat");
    const lng = fieldValue("lng");
    const radius = fieldValue("radius_km");
    const ageMin = fieldValue("age_min");
    const ageMax = fieldValue("age_max");
    const limitRaw = fieldValue("limit");
    const limit = limitRaw === "" ? DEFAULT_LIMIT : Number(limitRaw);
    const loadAll = Boolean(document.getElementById("load_all")?.checked);

    if (!taxon && !(lat && lng)) {
      hint.textContent = "Provide a taxon/mineral and/or both latitude and longitude.";
      hint.classList.add("error");
      return;
    }
    if ((lat && !lng) || (!lat && lng)) {
      hint.textContent = "Provide both latitude and longitude, or leave both blank.";
      hint.classList.add("error");
      return;
    }
    if ((ageMin !== "" && Number(ageMin) < 0) || (ageMax !== "" && Number(ageMax) < 0)) {
      hint.textContent = "Age bounds must be ≥ 0 Ma (million years ago).";
      hint.classList.add("error");
      return;
    }
    if (ageMin !== "" && ageMax !== "" && Number(ageMin) > Number(ageMax)) {
      hint.textContent = "Age min (younger) cannot be greater than age max (older).";
      hint.classList.add("error");
      return;
    }
    const allowedLimits = new Set([10, 25, 50, 100, 200, 300]);
    if (!allowedLimits.has(limit)) {
      hint.textContent = "Choose how many to display from the dropdown.";
      hint.classList.add("error");
      return;
    }

    const apiBase = resolveApiBase();
    const query = { taxon, lat, lng, radius, ageMin, ageMax, limit };

    const qs = new URLSearchParams();
    if (taxon) qs.set("taxon", taxon);
    // Only include optional filters when the user actually typed a value.
    if (lat !== "") qs.set("lat", lat);
    if (lng !== "") qs.set("lng", lng);
    if (radius !== "") qs.set("radius_km", radius);
    if (ageMin !== "") qs.set("age_min", ageMin);
    if (ageMax !== "") qs.set("age_max", ageMax);
    qs.set("limit", String(limit));

    const url = `${apiBase}/api/v1/synthesize?${qs.toString()}`;
    submitBtn.disabled = true;
    submitBtn.textContent = "Synthesizing…";
    statusEl.hidden = false;
    statusEl.innerHTML = `<p class="hint">Querying upstream sources… first hits after Render sleep can take ~30–60s.</p>`;
    resultsEl.hidden = true;
    resultsEl.innerHTML = "";
    hideSectionNav();

    try {
      const resp = await fetch(url);
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(formatApiError(body) || body.status || `HTTP ${resp.status}`);
      }
      if (body.status !== "success") {
        throw new Error(body.detail || "Synthesize failed");
      }
      renderStatus(body);
      await loadIcsIntervals();
      renderResults(body, limit, { apiBase, query, loadAll });
    } catch (err) {
      hint.textContent = String(err.message || err);
      hint.classList.add("error");
      statusEl.hidden = true;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Synthesize";
    }
  });

  function formatApiError(body) {
    const d = body?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
    return "";
  }

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function occurrenceAvailableCount(data) {
    const totals = data.occurrences?.source_totals;
    if (Array.isArray(totals) && totals.length) {
      return totals.reduce((sum, s) => {
        if (s.total != null && Number.isFinite(Number(s.total))) {
          return sum + Number(s.total);
        }
        return sum + (Number(s.returned) || 0);
      }, 0);
    }
    return Number(data.occurrences?.total_records) || 0;
  }

  function renderStatus(data) {
    const pills = (data.diagnostics || [])
      .map((d) => {
        const cls =
          d.status === "ok"
            ? "ok"
            : d.status === "error"
              ? "error"
              : d.status === "waiting"
                ? "waiting"
                : "skipped";
        const title = d.error ? ` title="${esc(d.error)}"` : "";
        const count =
          d.status === "ok" && Number(d.record_count) > 0 ? ` · ${esc(d.record_count)}` : "";
        const label = d.status === "waiting" ? "waiting…" : d.status;
        return `<span class="pill ${cls}"${title}>${esc(d.provider)} · ${esc(label)}${count}</span>`;
      })
      .join("");

    const loaded = (data.occurrences?.features || []).length;
    const available = occurrenceAvailableCount(data);
    const occLabel =
      loaded > 0 && available > loaded
        ? `Occurrences <strong>${esc(loaded.toLocaleString())}</strong> of <strong>${esc(
            available.toLocaleString()
          )}</strong>`
        : `Occurrences <strong>${esc(available.toLocaleString())}</strong>`;

    statusEl.hidden = false;
    statusEl.innerHTML = `
      <div class="status-meta">
        <span><strong>${esc(Math.round(data.execution_time_ms))} ms</strong> wall time</span>
        <span>Cache <strong>${esc(data.cache_status)}</strong></span>
        <span>${occLabel}</span>
        <span>Literature <strong>${esc((data.literature || []).length)}</strong></span>
      </div>
      <div class="pills">${pills}</div>
    `;
  }

  function sectionId(title) {
    return `section-${String(title)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")}`;
  }

  function block(title, sub, inner) {
    if (!inner) return "";
    const id = sectionId(title);
    return `
      <section class="block" id="${esc(id)}" data-section-title="${esc(title)}">
        <h2>${esc(title)}</h2>
        ${sub ? `<p class="sub">${sub}</p>` : ""}
        ${inner}
      </section>
    `;
  }

  function hideSectionNav() {
    if (sectionNav) sectionNav.hidden = true;
    if (sectionNavList) sectionNavList.innerHTML = "";
  }

  function setActiveSectionLink(sectionId) {
    if (!sectionNavList || !sectionId) return;
    sectionNavList.querySelectorAll("a").forEach((a) => {
      a.classList.toggle("is-active", a.dataset.target === sectionId);
    });
  }

  function updateActiveSectionFromScroll() {
    if (!sectionNav || sectionNav.hidden || !resultsEl) return;
    const sections = [...resultsEl.querySelectorAll(".block[id]")];
    if (!sections.length) return;

    // Account for fixed footer so the last section can still win.
    const footerH = document.querySelector(".foot")?.getBoundingClientRect().height || 0;
    const docBottom = window.scrollY + window.innerHeight;
    const pageBottom = document.documentElement.scrollHeight - footerH - 24;
    if (docBottom >= pageBottom) {
      setActiveSectionLink(sections[sections.length - 1].id);
      return;
    }

    const marker = Math.min(160, window.innerHeight * 0.28);
    let active = sections[0];
    for (const sec of sections) {
      if (sec.getBoundingClientRect().top <= marker) active = sec;
    }
    setActiveSectionLink(active.id);
  }

  function renderSectionNav() {
    if (!sectionNav || !sectionNavList) return;
    const sections = [...resultsEl.querySelectorAll(".block[id]")];
    if (!sections.length) {
      hideSectionNav();
      return;
    }

    sectionNavList.innerHTML = sections
      .map((sec) => {
        const title = sec.dataset.sectionTitle || sec.querySelector("h2")?.textContent || sec.id;
        return `<li><a href="#${esc(sec.id)}" data-target="${esc(sec.id)}">${esc(title)}</a></li>`;
      })
      .join("");
    sectionNav.hidden = false;

    sectionNavList.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const target = document.getElementById(link.dataset.target);
        if (!target) return;
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        setActiveSectionLink(link.dataset.target);
        history.replaceState(null, "", `#${link.dataset.target}`);
      });
    });

    if (!sectionScrollBound) {
      sectionScrollBound = true;
      window.addEventListener("scroll", updateActiveSectionFromScroll, { passive: true });
      window.addEventListener("resize", updateActiveSectionFromScroll, { passive: true });
    }
    updateActiveSectionFromScroll();
  }

  function occRowHtml(f) {
    const p = f.properties || {};
    const coords = f.geometry?.coordinates;
    const where =
      Array.isArray(coords) && coords.length >= 2
        ? `${Number(coords[1]).toFixed(3)}, ${Number(coords[0]).toFixed(3)}`
        : "—";
    const paleo =
      p.paleolat != null && p.paleolng != null
        ? `${Number(p.paleolat).toFixed(2)}, ${Number(p.paleolng).toFixed(2)}`
        : "—";
    return `<tr>
      <td>${esc(p.database_source)}</td>
      <td>${esc(p.taxon_name || p.accepted_name || "—")}</td>
      <td>${esc(where)}</td>
      <td>${esc(paleo)}</td>
      <td>${esc(p.max_ma ?? "—")}–${esc(p.min_ma ?? "—")}</td>
    </tr>`;
  }

  const PIE_COLORS = [
    "#6fbfa6",
    "#e0a45a",
    "#7ec98a",
    "#d4b35a",
    "#5a9e8a",
    "#c4894a",
    "#8ebf9a",
    "#e8c07a",
    "#4a7d6e",
    "#b8734a",
    "#9aafa3",
    "#c4a882",
  ];

  function countField(rows, key) {
    const counts = {};
    for (const row of rows || []) {
      const label = String(row?.[key] ?? "").trim() || "Unknown";
      counts[label] = (counts[label] || 0) + 1;
    }
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }

  function pieFigure(slices, title) {
    const total = slices.reduce((sum, s) => sum + s.count, 0);
    if (!total) return "";
    const R = 40;
    const CX = 50;
    const CY = 50;
    let angle = -Math.PI / 2;
    const paths = [];
    slices.forEach((slice, i) => {
      const frac = slice.count / total;
      if (frac <= 0) return;
      const color = PIE_COLORS[i % PIE_COLORS.length];
      const tip = `${slice.name}: ${slice.count} (${Math.round(frac * 100)}%)`;
      if (frac >= 0.999) {
        paths.push(
          `<circle cx="${CX}" cy="${CY}" r="${R}" fill="${color}"><title>${esc(tip)}</title></circle>`
        );
        return;
      }
      const next = angle + frac * 2 * Math.PI;
      const x1 = CX + R * Math.cos(angle);
      const y1 = CY + R * Math.sin(angle);
      const x2 = CX + R * Math.cos(next);
      const y2 = CY + R * Math.sin(next);
      const large = frac > 0.5 ? 1 : 0;
      paths.push(
        `<path d="M ${CX} ${CY} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x2.toFixed(
          2
        )} ${y2.toFixed(2)} Z" fill="${color}"><title>${esc(tip)}</title></path>`
      );
      angle = next;
    });
    const legend = slices
      .map((s, i) => {
        const pct = Math.round((s.count / total) * 100);
        return `<li>
          <span class="pie-swatch" style="background:${PIE_COLORS[i % PIE_COLORS.length]}"></span>
          <span class="pie-label">${esc(s.name)}</span>
          <span class="pie-count">${esc(s.count)} · ${esc(pct)}%</span>
        </li>`;
      })
      .join("");
    return `<figure class="pie-chart">
      <figcaption>${esc(title)}</figcaption>
      <div class="pie-body">
        <svg viewBox="0 0 100 100" role="img" aria-label="${esc(title)} composition">${paths.join(
          ""
        )}</svg>
        <ul class="pie-legend">${legend}</ul>
      </div>
    </figure>`;
  }

  function formatTotals(sourceTotals, features) {
    if (sourceTotals?.length) {
      return sourceTotals
        .filter((s) => (Number(s.returned) || 0) > 0 || s.total != null)
        .map((s) => {
          const returned = Number(s.returned) || 0;
          if (returned <= 0 && (s.total == null || Number(s.total) === 0)) return null;
          if (s.total != null && Number.isFinite(Number(s.total))) {
            return `${esc(s.provider)} ${esc(returned)} of ${esc(Number(s.total).toLocaleString())}`;
          }
          return returned > 0 ? `${esc(s.provider)} ${esc(returned)}` : null;
        })
        .filter(Boolean)
        .join(" · ");
    }
    const counts = {};
    for (const f of features || []) {
      const src = (f.properties || {}).database_source || "Unknown";
      counts[src] = (counts[src] || 0) + 1;
    }
    return Object.entries(counts)
      .filter(([, n]) => n > 0)
      .map(([src, n]) => `${esc(src)} ${esc(n)}`)
      .join(" · ");
  }

  function countGbifFeatures(features) {
    return (features || []).filter((f) => (f.properties || {}).database_source === "GBIF").length;
  }

  function resolveGbifState(features, sourceTotals, pageLimit) {
    const hasSourceTotals = Array.isArray(sourceTotals) && sourceTotals.length > 0;
    const fromApi = hasSourceTotals
      ? sourceTotals.find((s) => s.provider === "GBIF")
      : null;
    const returned = fromApi
      ? Number(fromApi.returned) || 0
      : countGbifFeatures(features);
    const total = fromApi && fromApi.total != null ? Number(fromApi.total) : null;
    let hasMore;
    if (total != null && Number.isFinite(total)) {
      hasMore = returned < total;
    } else if (!hasSourceTotals) {
      // Old synthesize payload without source_totals — offer paging and let GBIF decide.
      hasMore = returned > 0;
    } else {
      // Totals present but GBIF count missing: more likely if this page was full.
      hasMore = returned > 0 && returned >= pageLimit;
    }
    return { returned, total, hasMore, offset: returned };
  }

  function renderResults(data, limit = DEFAULT_LIMIT, opts = {}) {
    const units = data.geology?.macrostrat_units || [];
    const features = data.occurrences?.features || [];
    const specimens = data.specimens?.records || [];
    const media = data.media_3d?.records || [];
    const minerals = data.minerals?.minerals || [];
    const localities = data.minerals?.localities || [];
    const literature = data.literature || [];
    const studies = data.paleoclimate_proxy?.studies || [];
    const parses = data.name_parse?.parses || [];
    const hierarchy = data.taxonomy?.hierarchy || [];
    const pbdbHier = data.taxonomy?.pbdb_hierarchy || [];
    const sourceTotals = data.occurrences?.source_totals || [];
    const show = Math.max(1, Math.min(Number(limit) || DEFAULT_LIMIT, MAX_LIMIT));
    const gbif = resolveGbifState(features, sourceTotals, show);

    const nameHtml = parses.length
      ? `<ul class="list">${parses
          .map(
            (n) => `<li>
              <div class="item-title">${esc(n.canonical_simple || n.verbatim || "Name")}</div>
              <div class="item-meta">
                ${esc(n.rank || "")}
                ${n.genus ? ` · genus ${esc(n.genus)}` : ""}
                ${n.species ? ` · species ${esc(n.species)}` : ""}
                ${n.authorship_normalized ? ` · ${esc(n.authorship_normalized)}` : ""}
                ${n.url ? ` · <a href="${esc(n.url)}" target="_blank" rel="noopener">GNparser</a>` : ""}
              </div>
            </li>`
          )
          .join("")}</ul>`
      : `<p class="empty">No name parse.</p>`;

    const chronoTaxHtml = chronostratTaxonomyHtml(data, opts.query, icsIntervals || []);
    const taxHtml = hierarchy.length
      ? `<ol class="taxonomy-tree">${hierarchy
          .map(
            (r) =>
              `<li><span class="tax-rank">${esc(r.rank)}</span> <span class="tax-name">${esc(
                r.name
              )}</span> <span class="item-meta">${esc(r.source || "")}</span></li>`
          )
          .join("")}</ol>
        <p class="item-meta">
          ${data.taxonomy?.scientific_name ? esc(data.taxonomy.scientific_name) : ""}
          ${data.taxonomy?.taxonomic_status ? ` · ${esc(data.taxonomy.taxonomic_status)}` : ""}
          ${data.taxonomy?.gbif_url ? ` · <a href="${esc(data.taxonomy.gbif_url)}" target="_blank" rel="noopener">GBIF</a>` : ""}
          ${data.taxonomy?.pbdb_url ? ` · <a href="${esc(data.taxonomy.pbdb_url)}" target="_blank" rel="noopener">PBDB</a>` : ""}
        </p>
        ${
          pbdbHier.length
            ? `<p class="sub">PBDB paleo classification</p><ol class="taxonomy-tree">${pbdbHier
                .map(
                  (r) =>
                    `<li><span class="tax-rank">${esc(r.rank)}</span> <span class="tax-name">${esc(
                      r.name
                    )}</span></li>`
                )
                .join("")}</ol>`
            : ""
        }
        ${chronoTaxHtml}`
      : `${chronoTaxHtml || `<p class="empty">No taxonomy hierarchy.</p>`}`;

    const lithSlices = countField(units, "lithology");
    const envSlices = countField(units, "environment");
    const geologyCharts =
      units.length && (lithSlices.length || envSlices.length)
        ? `<div class="pie-row">
            ${pieFigure(lithSlices, "Lithology")}
            ${pieFigure(envSlices, "Environment")}
          </div>`
        : "";
    const geologyHtml = units.length
      ? `${geologyCharts}<ul class="list">${units
          .map(
            (u) => `<li>
              <div class="item-title">${esc(u.unit_name || "Unit")}</div>
              <div class="item-meta">${esc(u.lithology || "—")} · ${esc(u.age_top_ma ?? "?")}–${esc(
                u.age_bottom_ma ?? "?"
              )} Ma · ${esc(u.environment || "")}</div>
            </li>`
          )
          .join("")}</ul>`
      : `<p class="empty">No Macrostrat units.</p>`;

    const browse = (data.occurrences?.browse_links || [])
      .map(
        (l) =>
          `<a class="occ-link" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(
            l.label || l.provider
          )}</a>`
      )
      .join("");
    const viewAllApi = data.occurrences?.view_all_url
      ? `<a class="occ-link" href="${esc(data.occurrences.view_all_url)}" target="_blank" rel="noopener">Full JSON response</a>`
      : "";
    const totalsLine = formatTotals(sourceTotals, features);
    const canPageGbif = Boolean(gbif.hasMore);
    const noMoreMsg =
      gbif.returned === 0
        ? `<span class="sub">No GBIF occurrences in this result to page.</span>`
        : `<span class="sub">No further GBIF pages for this query (loaded ${gbif.returned}${
            gbif.total != null ? ` of ${Number(gbif.total).toLocaleString()}` : ""
          }).</span>`;

    const occHtml = features.length
      ? `<div class="table-wrap"><table>
          <thead><tr><th>Source</th><th>Taxon</th><th>Lat, lng</th><th>Paleolat, paleolng</th><th>Ma</th></tr></thead>
          <tbody id="occ-tbody">${features.map(occRowHtml).join("")}</tbody>
        </table></div>
        <p class="occ-progress" id="occ-progress">Showing <strong>${features.length}</strong> loaded occurrence(s)${
          gbif.total != null
            ? ` · GBIF <strong>${gbif.returned.toLocaleString()}</strong> of <strong>${Number(gbif.total).toLocaleString()}</strong>`
            : ""
        }</p>
        <p class="occ-links" id="occ-links">
          ${
            canPageGbif
              ? `<button type="button" class="linkish" id="occ-load-more">Load more GBIF</button>
                 <button type="button" class="linkish" id="occ-load-all" hidden>Continue loading</button>
                 <button type="button" class="linkish" id="occ-stop" hidden>Stop</button>`
              : noMoreMsg
          }
          ${viewAllApi}
          ${browse}
        </p>`
      : `<p class="empty">No occurrences.</p>`;

    const specimenHtml = specimens.length
      ? `<ul class="list">${specimens
          .slice(0, show)
          .map(
            (s) => `<li>
              <div class="item-title">${esc(s.scientific_name || "Specimen")}</div>
              <div class="item-meta">${esc(s.institution_code || "")} ${esc(
                s.catalog_number || ""
              )}${s.url ? ` · <a href="${esc(s.url)}" target="_blank" rel="noopener">link</a>` : ""}</div>
            </li>`
          )
          .join("")}</ul>`
      : `<p class="empty">No specimen vouchers.</p>`;

    const mediaHtml = media.length
      ? `<ul class="list">${media
          .slice(0, show)
          .map(
            (m) => `<li>
              <div class="item-title">${esc(m.title || m.media_id || "Media")}</div>
              <div class="item-meta">${esc(m.modality || m.media_type || "")} · ${esc(
                m.physical_object_taxonomy || ""
              )}${m.url ? ` · <a href="${esc(m.url)}" target="_blank" rel="noopener">open</a>` : ""}</div>
            </li>`
          )
          .join("")}</ul>`
      : `<p class="empty">No 3D / CT media.</p>`;

    const mineralHtml =
      minerals.length || localities.length
        ? `<ul class="list">${minerals
            .map(
              (m) => `<li>
                <div class="item-title">${esc(m.name || "Mineral")}</div>
                <div class="item-meta">${esc(m.formula || "")}${
                  m.url ? ` · <a href="${esc(m.url)}" target="_blank" rel="noopener">Mindat</a>` : ""
                }</div>
              </li>`
            )
            .join("")}${localities
            .map(
              (loc) => `<li>
                <div class="item-title">${esc(loc.name || "Locality")}</div>
                <div class="item-meta">${esc(loc.country || "")} · ${esc(loc.lat ?? "")}, ${esc(
                  loc.lon ?? ""
                )}</div>
              </li>`
            )
            .join("")}</ul>`
        : `<p class="empty">No minerals / localities.</p>`;

    const litHtml = literature.length
      ? `<ul class="list">${literature
          .slice(0, show)
          .map((L) => {
            const authors = (L.authors || []).slice(0, 3).join(", ");
            const href = L.url || (L.doi ? `https://doi.org/${L.doi}` : null);
            const title = href
              ? `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(L.title || L.doi || "Work")}</a>`
              : esc(L.title || "Work");
            return `<li>
              <div class="item-title">${title}</div>
              <div class="item-meta">${esc(L.provider || "")} · ${esc(authors)}${
                L.year ? ` · ${esc(L.year)}` : ""
              }${L.cited_by_count != null ? ` · cited ${esc(L.cited_by_count)}` : ""}</div>
            </li>`;
          })
          .join("")}</ul>`
      : `<p class="empty">No literature hits.</p>`;

    const climateHtml = studies.length
      ? `<ul class="list">${studies
          .slice(0, show)
          .map(
            (s) => `<li>
              <div class="item-title">${esc(s.study_name || s.study_id || "Study")}</div>
              <div class="item-meta">${esc(s.data_type || "")} · ${esc(s.site_name || "")}${
                s.url ? ` · <a href="${esc(s.url)}" target="_blank" rel="noopener">open</a>` : ""
              }</div>
            </li>`
          )
          .join("")}</ul>`
      : `<p class="empty">No paleoclimate studies.</p>`;

    const availableOcc = occurrenceAvailableCount(data);
    const occSub = `${features.length.toLocaleString()} loaded${
      availableOcc > features.length
        ? ` of ${availableOcc.toLocaleString()} available`
        : ""
    }${totalsLine ? ` · ${totalsLine}` : ""}`;

    const ageLayers = collectAgeLayers(data, opts.query);
    const agesCount =
      (ageLayers.bounds.older != null || ageLayers.bounds.younger != null ? 1 : 0) +
      ageLayers.pbdb.length +
      ageLayers.macro.length;
    agesChartState.full = false;
    const agesHtml = agesSectionHtml(data, opts.query, icsIntervals || []);

    resultsEl.hidden = false;
    resultsEl.innerHTML = [
      block(
        "Taxonomy",
        data.taxonomy?.accepted_name
          ? `Accepted: ${data.taxonomy.accepted_name}`
          : "Full rank hierarchy",
        taxHtml
      ),
      block("Name parse", `${parses.length} GNparser result(s)`, nameHtml),
      block("Geology", `${units.length} Macrostrat unit(s)`, geologyHtml),
      block(
        "Ages",
        agesCount ? `ICS chronostrat chart · query, PBDB, Macrostrat` : "No ages in this result",
        agesHtml
      ),
      block("Occurrences", occSub, occHtml),
      block("Specimens", `${data.specimens?.voucher_count ?? 0} voucher(s)`, specimenHtml),
      block("3D media", data.media_3d?.has_3d_assets ? "MorphoSource hits" : "None", mediaHtml),
      block(
        "Minerals",
        `${data.minerals?.mineral_count ?? 0} mineral(s), ${data.minerals?.locality_count ?? 0} localities`
          + (data.minerals?.link_mode ? ` · linked via ${data.minerals.link_mode}` : "")
          + (data.minerals?.linked_taxon ? ` · taxon ${data.minerals.linked_taxon}` : ""),
        mineralHtml
      ),
      block("Paleoclimate", `${data.paleoclimate_proxy?.study_count ?? 0} NOAA study(ies)`, climateHtml),
      block("Literature", `${literature.length} work(s)`, litHtml),
    ].join("");
    renderSectionNav();
    wireAgesChartToggle();

    if (!opts.apiBase) return;

    void fetchDeferredNeotoma(opts.apiBase, opts.query, data);

    paging.cancel = false;
    paging.ctx = {
      apiBase: opts.apiBase,
      query: opts.query,
      offset: gbif.offset,
      total: gbif.total,
      hasMore: gbif.hasMore,
      loadedRows: features.length,
      gbifLoaded: gbif.returned,
    };

    wireOccControls(Boolean(opts.loadAll) && gbif.hasMore);
  }

  function setOccButtons({ loadMore, loadAll, stop }) {
    const moreBtn = document.getElementById("occ-load-more");
    const allBtn = document.getElementById("occ-load-all");
    const stopBtn = document.getElementById("occ-stop");
    if (moreBtn) moreBtn.hidden = !loadMore;
    if (allBtn) allBtn.hidden = !loadAll;
    if (stopBtn) stopBtn.hidden = !stop;
  }

  function updateOccProgress(message) {
    const el = document.getElementById("occ-progress");
    if (el) el.innerHTML = message;
  }

  function wireOccControls(autoLoadAll) {
    const moreBtn = document.getElementById("occ-load-more");
    const allBtn = document.getElementById("occ-load-all");
    const stopBtn = document.getElementById("occ-stop");

    if (moreBtn) {
      moreBtn.addEventListener("click", () => {
        void runPaging({ continuous: false });
      });
    }
    if (allBtn) {
      allBtn.addEventListener("click", () => {
        void runPaging({ continuous: true });
      });
    }
    if (stopBtn) {
      stopBtn.addEventListener("click", () => {
        paging.cancel = true;
      });
    }

    if (autoLoadAll && paging.ctx?.hasMore) {
      void runPaging({ continuous: true });
    }
  }

  function mapGbifRecord(rec) {
    const lat = rec.decimalLatitude;
    const lng = rec.decimalLongitude;
    const key = rec.key;
    return {
      type: "Feature",
      geometry:
        lat != null && lng != null
          ? { type: "Point", coordinates: [lng, lat] }
          : null,
      properties: {
        occurrence_id: key != null ? `gbif:occ:${key}` : null,
        database_source: "GBIF",
        taxon_name: rec.scientificName || rec.species,
        accepted_name: rec.acceptedScientificName || rec.scientificName,
        dwc_eventDate: rec.eventDate || (rec.year != null ? String(rec.year) : null),
        max_ma: null,
        min_ma: null,
        basis_of_record: rec.basisOfRecord,
        country: rec.country,
        dataset_key: rec.datasetKey,
        gbif_url: key != null ? `https://www.gbif.org/occurrence/${key}` : null,
      },
    };
  }

  async function fetchGbifDirect(ctx) {
    const q = ctx.query || {};
    const qs = new URLSearchParams();
    qs.set("limit", String(PAGE_SIZE));
    qs.set("offset", String(ctx.offset));
    qs.set("hasCoordinate", "true");
    if (q.taxon) qs.set("scientificName", q.taxon);
    if (q.lat && q.lng) {
      const r = q.radius || "10";
      qs.set("geoDistance", `${q.lat},${q.lng},${r}km`);
    }
    const resp = await fetch(`https://api.gbif.org/v1/occurrence/search?${qs.toString()}`);
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(payload.message || `GBIF HTTP ${resp.status}`);
    }
    const features = (payload.results || []).map(mapGbifRecord);
    const total = payload.count != null ? Number(payload.count) : null;
    const nextOffset = ctx.offset + features.length;
    const end = Boolean(payload.endOfRecords) || (total != null && nextOffset >= total);
    const windowHit = nextOffset >= 100000;
    const hasMore = !end && features.length > 0 && !windowHit && (total == null || nextOffset < total);
    return {
      status: "success",
      provider: "GBIF",
      features,
      returned: features.length,
      total,
      offset: ctx.offset,
      next_offset: hasMore ? nextOffset : null,
      has_more: hasMore,
      window_exhausted: windowHit && total != null && total > 100000,
    };
  }

  async function fetchOccPage(ctx) {
    const qs = new URLSearchParams();
    qs.set("provider", "GBIF");
    qs.set("offset", String(ctx.offset));
    qs.set("limit", String(PAGE_SIZE));
    const q = ctx.query || {};
    if (q.taxon) qs.set("taxon", q.taxon);
    if (q.lat) qs.set("lat", q.lat);
    if (q.lng) qs.set("lng", q.lng);
    if (q.radius) qs.set("radius_km", q.radius);
    if (q.ageMin) qs.set("age_min", q.ageMin);
    if (q.ageMax) qs.set("age_max", q.ageMax);

    const resp = await fetch(`${ctx.apiBase}/api/v1/occurrences?${qs.toString()}`);
    if (resp.status === 404) {
      // Render may still be on a build without /occurrences — page GBIF directly.
      return fetchGbifDirect(ctx);
    }
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok || body.status !== "success") {
      throw new Error(formatApiError(body) || body.detail || `HTTP ${resp.status}`);
    }
    return body;
  }

  async function runPaging({ continuous }) {
    if (!paging.ctx || paging.busy) return;
    const ctx = paging.ctx;
    if (!ctx.hasMore) return;

    paging.busy = true;
    paging.cancel = false;
    setOccButtons({ loadMore: false, loadAll: false, stop: true });

    const tbody = document.getElementById("occ-tbody");
    try {
      do {
        if (paging.cancel) break;
        if (ctx.loadedRows >= SOFT_CAP) {
          updateOccProgress(
            `Paused at soft display cap of <strong>${SOFT_CAP.toLocaleString()}</strong> rows · GBIF loaded <strong>${ctx.gbifLoaded.toLocaleString()}</strong>${
              ctx.total != null ? ` of <strong>${Number(ctx.total).toLocaleString()}</strong>` : ""
            }. Continue to load more, or browse GBIF for the full catalog.`
          );
          setOccButtons({ loadMore: true, loadAll: true, stop: false });
          paging.busy = false;
          return;
        }

        updateOccProgress(
          `Paging GBIF… loaded <strong>${ctx.gbifLoaded.toLocaleString()}</strong>${
            ctx.total != null ? ` of <strong>${Number(ctx.total).toLocaleString()}</strong>` : ""
          }`
        );

        const page = await fetchOccPage(ctx);
        const feats = page.features || [];
        if (tbody && feats.length) {
          tbody.insertAdjacentHTML("beforeend", feats.map(occRowHtml).join(""));
        }
        ctx.loadedRows += feats.length;
        ctx.gbifLoaded += feats.length;
        ctx.offset = page.next_offset != null ? page.next_offset : ctx.offset + feats.length;
        ctx.total = page.total != null ? page.total : ctx.total;
        ctx.hasMore = Boolean(page.has_more);

        if (page.window_exhausted) {
          updateOccProgress(
            `Loaded <strong>${ctx.gbifLoaded.toLocaleString()}</strong> GBIF rows (search API window max 100,000). Catalog total <strong>${
              ctx.total != null ? Number(ctx.total).toLocaleString() : "?"
            }</strong> — use Browse all on GBIF for the rest.`
          );
          break;
        }

        if (!continuous) break;
      } while (ctx.hasMore && !paging.cancel);

      if (paging.cancel) {
        updateOccProgress(
          `Stopped. Showing <strong>${ctx.loadedRows.toLocaleString()}</strong> rows · GBIF <strong>${ctx.gbifLoaded.toLocaleString()}</strong>${
            ctx.total != null ? ` of <strong>${Number(ctx.total).toLocaleString()}</strong>` : ""
          }.`
        );
      } else if (!ctx.hasMore) {
        updateOccProgress(
          `Showing <strong>${ctx.loadedRows.toLocaleString()}</strong> loaded occurrence(s) · GBIF <strong>${ctx.gbifLoaded.toLocaleString()}</strong>${
            ctx.total != null ? ` of <strong>${Number(ctx.total).toLocaleString()}</strong>` : ""
          }${
            ctx.total != null && ctx.gbifLoaded < ctx.total
              ? " (remaining beyond search API — use browse link)"
              : ""
          }.`
        );
      } else {
        updateOccProgress(
          `Showing <strong>${ctx.loadedRows.toLocaleString()}</strong> rows · GBIF <strong>${ctx.gbifLoaded.toLocaleString()}</strong>${
            ctx.total != null ? ` of <strong>${Number(ctx.total).toLocaleString()}</strong>` : ""
          }.`
        );
      }
    } catch (err) {
      updateOccProgress(`Paging error: ${esc(err.message || err)}`);
    } finally {
      paging.busy = false;
      setOccButtons({
        loadMore: Boolean(ctx.hasMore),
        loadAll: Boolean(ctx.hasMore),
        stop: false,
      });
    }
  }
})();
