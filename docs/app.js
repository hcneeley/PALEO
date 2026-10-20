(() => {
  const DEFAULT_API = "https://upae-ff1k.onrender.com";

  const form = document.getElementById("search-form");
  const hint = document.getElementById("form-hint");
  const submitBtn = document.getElementById("submit-btn");
  const exampleBtn = document.getElementById("example-btn");
  const statusEl = document.getElementById("status");
  const resultsEl = document.getElementById("results");

  function resolveApiBase() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = (params.get("api") || "").trim().replace(/\/$/, "");
    return fromQuery || DEFAULT_API;
  }

  exampleBtn.addEventListener("click", () => {
    document.getElementById("taxon").value = "Canis dirus";
    document.getElementById("lat").value = "34.05";
    document.getElementById("lng").value = "-118.25";
    document.getElementById("radius_km").value = "500";
    document.getElementById("age_min").value = "";
    document.getElementById("age_max").value = "";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hint.textContent = "";
    hint.classList.remove("error");

    const taxon = (document.getElementById("taxon").value || "").trim();
    const lat = (document.getElementById("lat").value || "").trim();
    const lng = (document.getElementById("lng").value || "").trim();
    const radius = (document.getElementById("radius_km").value || "").trim();
    const ageMin = (document.getElementById("age_min").value || "").trim();
    const ageMax = (document.getElementById("age_max").value || "").trim();

    if (!taxon && !(lat && lng)) {
      hint.textContent = "Provide a taxon/mineral and/or both latitude and longitude.";
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

    const apiBase = resolveApiBase();

    const qs = new URLSearchParams();
    if (taxon) qs.set("taxon", taxon);
    if (lat) qs.set("lat", lat);
    if (lng) qs.set("lng", lng);
    if (radius) qs.set("radius_km", radius);
    if (ageMin) qs.set("age_min", ageMin);
    if (ageMax) qs.set("age_max", ageMax);

    const url = `${apiBase}/api/v1/synthesize?${qs.toString()}`;
    submitBtn.disabled = true;
    submitBtn.textContent = "Synthesizing…";
    statusEl.hidden = false;
    statusEl.innerHTML = `<p class="hint">Querying upstream sources… first hits after Render sleep can take ~30–60s.</p>`;
    resultsEl.hidden = true;
    resultsEl.innerHTML = "";

    try {
      const resp = await fetch(url);
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(body.detail || body.status || `HTTP ${resp.status}`);
      }
      if (body.status !== "success") {
        throw new Error(body.detail || "Synthesize failed");
      }
      renderStatus(body);
      renderResults(body);
    } catch (err) {
      hint.textContent = String(err.message || err);
      hint.classList.add("error");
      statusEl.hidden = true;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Synthesize";
    }
  });

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

  function block(title, sub, inner) {
    if (!inner) return "";
    return `
      <section class="block">
        <h2>${esc(title)}</h2>
        ${sub ? `<p class="sub">${sub}</p>` : ""}
        ${inner}
      </section>
    `;
  }

  function renderResults(data) {
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


    const nameHtml = parses.length
      ? `<ul class="list">${parses
          .map((n) => `<li>
              <div class="item-title">${esc(n.canonical_simple || n.verbatim || "Name")}</div>
              <div class="item-meta">
                ${esc(n.rank || "")}
                ${n.genus ? ` · genus ${esc(n.genus)}` : ""}
                ${n.species ? ` · species ${esc(n.species)}` : ""}
                ${n.authorship_normalized ? ` · ${esc(n.authorship_normalized)}` : ""}
                ${n.url ? ` · <a href="${esc(n.url)}" target="_blank" rel="noopener">GNparser</a>` : ""}
              </div>
            </li>`)
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

    const PREVIEW = 40;
    const occRow = (f) => {
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
    };
    const occPreview = features.slice(0, PREVIEW).map(occRow).join("");
    const occAll = features.map(occRow).join("");
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

    const occHtml = features.length
      ? `<div class="table-wrap" id="occ-preview"><table>
          <thead><tr><th>Source</th><th>Taxon</th><th>Lat, lng</th><th>Paleolat, paleolng</th><th>Ma</th></tr></thead>
          <tbody>${occPreview}</tbody>
        </table></div>
        <div class="table-wrap" id="occ-all" hidden><table>
          <thead><tr><th>Source</th><th>Taxon</th><th>Lat, lng</th><th>Paleolat, paleolng</th><th>Ma</th></tr></thead>
          <tbody>${occAll}</tbody>
        </table></div>
        <p class="occ-links">
          ${
            features.length > PREVIEW
              ? `<button type="button" class="linkish" id="occ-expand">View all ${features.length} occurrences in this result</button>`
              : `<span class="sub">Showing all ${features.length} occurrence(s) returned.</span>`
          }
          ${viewAllApi}
          ${browse}
        </p>`
      : `<p class="empty">No occurrences.</p>`;

    const specimenHtml = specimens.length
      ? `<ul class="list">${specimens
          .slice(0, 25)
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
          .slice(0, 20)
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
          .slice(0, 30)
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
          .slice(0, 15)
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
      block("Occurrences", `${features.length} GeoJSON feature(s)`, occHtml),
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

    const expandBtn = document.getElementById("occ-expand");
    if (expandBtn) {
      expandBtn.addEventListener("click", () => {
        document.getElementById("occ-preview").hidden = true;
        document.getElementById("occ-all").hidden = false;
        expandBtn.hidden = true;
      });
    }
  }
})();
