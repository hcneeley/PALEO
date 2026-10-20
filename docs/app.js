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
  /** @type {IntersectionObserver | null} */
  let sectionObserver = null;

  topBtn?.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    history.replaceState(null, "", window.location.pathname + window.location.search);
  });

  /** @type {{ cancel: boolean, busy: boolean, ctx: object | null }} */
  const paging = { cancel: false, busy: false, ctx: null };

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

  function renderStatus(data) {
    const pills = (data.diagnostics || [])
      .map((d) => {
        const cls = d.status === "ok" ? "ok" : d.status === "error" ? "error" : "skipped";
        const title = d.error ? ` title="${esc(d.error)}"` : "";
        return `<span class="pill ${cls}"${title}>${esc(d.provider)} · ${esc(d.status)}${
          d.record_count ? ` · ${esc(d.record_count)}` : ""
        }</span>`;
      })
      .join("");

    statusEl.hidden = false;
    statusEl.innerHTML = `
      <div class="status-meta">
        <span><strong>${esc(Math.round(data.execution_time_ms))} ms</strong> wall time</span>
        <span>Cache <strong>${esc(data.cache_status)}</strong></span>
        <span>Occurrences <strong>${esc(data.occurrences?.total_records ?? 0)}</strong></span>
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
    if (sectionObserver) {
      sectionObserver.disconnect();
      sectionObserver = null;
    }
    if (sectionNav) sectionNav.hidden = true;
    if (sectionNavList) sectionNavList.innerHTML = "";
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
        sectionNavList.querySelectorAll("a").forEach((a) => a.classList.remove("is-active"));
        link.classList.add("is-active");
        history.replaceState(null, "", `#${link.dataset.target}`);
      });
    });

    if (sectionObserver) sectionObserver.disconnect();
    sectionObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible?.target?.id) return;
        sectionNavList.querySelectorAll("a").forEach((a) => {
          a.classList.toggle("is-active", a.dataset.target === visible.target.id);
        });
      },
      { rootMargin: "-20% 0px -55% 0px", threshold: [0.1, 0.25, 0.5] }
    );
    sections.forEach((sec) => sectionObserver.observe(sec));
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

  function formatTotals(sourceTotals, features) {
    if (sourceTotals?.length) {
      return sourceTotals
        .map((s) => {
          const total = s.total != null ? Number(s.total).toLocaleString() : "?";
          return `${esc(s.provider)} ${esc(s.returned)} of ${esc(total)}`;
        })
        .join(" · ");
    }
    const counts = {};
    for (const f of features || []) {
      const src = (f.properties || {}).database_source || "Unknown";
      counts[src] = (counts[src] || 0) + 1;
    }
    return Object.entries(counts)
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
        }`
      : `<p class="empty">No taxonomy hierarchy.</p>`;

    const geologyHtml = units.length
      ? `<ul class="list">${units
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
      ? `${
          totalsLine ? `<p class="occ-totals">${totalsLine}</p>` : ""
        }<div class="table-wrap"><table>
          <thead><tr><th>Source</th><th>Taxon</th><th>Lat, lng</th><th>Paleolat, paleolng</th><th>Ma</th></tr></thead>
          <tbody id="occ-tbody">${features.map(occRowHtml).join("")}</tbody>
        </table></div>
        <p class="occ-progress" id="occ-progress">Showing <strong>${features.length}</strong> loaded occurrence(s)${
          gbif.total != null
            ? ` · GBIF catalog <strong>${Number(gbif.total).toLocaleString()}</strong>`
            : gbif.returned
              ? ` · GBIF in page <strong>${gbif.returned}</strong>`
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

    const occSub = totalsLine
      ? `${features.length} loaded · ${totalsLine}`
      : `${features.length} GeoJSON feature(s)`;

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

    if (!opts.apiBase) return;

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
