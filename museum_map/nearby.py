"""The map's nearby control: museums within a radius of a named place.

The map arranges museums by what they are about, so a radius drawn on the globe
lands as scattered points all over it. That is the point of the control rather
than a defect of it — it answers "what is this city's museum scene *about*",
which a list of addresses cannot. It filters rather than pans.

Two things here are not obvious.

**It is injected as `custom_html`/`custom_css`/`custom_js`, not as a
`WidgetBase`.** datamapplot has a widget system and this is exactly the shape of
thing it is for, but passing `widgets=` switches `render_html` off its legacy
path (`interactive_rendering.py`, "Convert legacy parameters to widgets" — it is
an `else`). Everything p13 configures the old way, the title, the search box and
the whole palette control, is built by that branch, and the default widget config
cannot rebuild them because every entry in it is `_positional_only`. So passing
one widget would cost all of them. The `custom_*` parameters survive the legacy
path untouched. The control still lands in the right place because
`.stack.top-left` is rendered on both paths and only its *contents* are gated, so
the JS moves itself into that stack at load and stacks under the search box.

**Selection, not a private overlay.** It calls `datamap.addSelection` under its
own item id, which is what the search box does, so the two compose: the manager
intersects across items (`data_selection_manager.js`), and "within 20 km of
Kyoto" plus a search for "art" means both. Unselected points are *hidden*, not
dimmed — the point layer filters on `getFilterValue` with a range that excludes
them — so this reads as a filter to a visitor even though it is a selection
underneath.
"""

from __future__ import annotations

import json

import pandas as pd

# Slider bounds, in kilometres, on a log scale: one decade below a city and one
# above it. 1 km is inside a single district, 1000 km is most of a country.
MIN_KM = 1.0
MAX_KM = 1000.0
# Where the slider starts when a place is picked. Metro-scale for most of the
# gazetteer: generous for a town, tight for Tokyo. There is nothing deeper to it
# than that — a place's own extent would set this better, but Wikidata's P2046 is
# not fetched and one constant is not worth a second network stage.
DEFAULT_KM = 25.0

# How many suggestions the typeahead offers. The gazetteer is ordered by museum
# count, so a short list is the *large* matches rather than an arbitrary prefix.
MAX_SUGGESTIONS = 8


def _payload(places: pd.DataFrame) -> str:
    """Gazetteer as `[name, region, country, lat, lon]` rows, in typeahead order.

    Arrays rather than objects, and coordinates at four decimals (~11 m, far
    finer than a settlement's centroid means anything), because this ships inside
    the HTML: on the full corpus it is thousands of entries and the keys would
    cost more than the values. `n_museums` is not carried — it ordered the frame
    in p09 and the order is the only thing the control needs it for.

    `region` is the first-level subdivision containing the place. It is not
    selectable: it tells the two Portlands apart in the list, and it is matched
    against, so typing a region's name finds the settlements inside it.
    """
    rows = [
        [r.name, r.region, r.country, round(float(r.lat), 4), round(float(r.lon), 4)]
        for r in places.itertuples(index=False)
    ]
    # A label containing `</script>` would otherwise close the block it sits in.
    return json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")


class NearbyControl:
    """Renders to the three `custom_*` strings `render_html` accepts.

    `no_coord` is the sentinel p13 writes into the `lat`/`lon` point metadata for
    a museum Wikidata has no P625 for. It cannot be NaN: the metadata is shipped
    as JSON and parsed with a strict `JSON.parse` in a worker
    (`data_workers.js`), which rejects the bare `NaN` that `json.dumps` emits,
    and the failure is the whole map loading without any metadata at all.
    """

    def __init__(
        self,
        places: pd.DataFrame,
        *,
        no_coord: float,
        missing_share: float,
        min_km: float = MIN_KM,
        max_km: float = MAX_KM,
        default_km: float = DEFAULT_KM,
    ) -> None:
        self.places = places
        self.no_coord = no_coord
        self.missing_share = missing_share
        self.min_km = min_km
        self.max_km = max_km
        self.default_km = default_km

    @property
    def html(self) -> str:
        return """
<div id="nearby-container" class="container-box">
  <input autocomplete="off" type="search" id="nearby-place"
         placeholder="📍 Museums near…" aria-label="Museums near a place" />
  <div id="nearby-suggestions" role="listbox" hidden></div>
  <div id="nearby-radius" hidden>
    <input type="range" id="nearby-slider" min="0" max="1000" step="1"
           aria-label="Search radius" />
    <span id="nearby-distance"></span>
  </div>
  <div id="nearby-count" hidden></div>
</div>
"""

    @property
    def css(self) -> str:
        # Colours are inherited or expressed as opacity so the control follows
        # `container-box` into dark mode instead of pinning its own palette.
        return """
#nearby-container { width: fit-content; }
#nearby-place { width: 13rem; }
#nearby-suggestions {
  max-height: 13rem; overflow-y: auto; margin-top: .25rem;
  font-size: .85em; line-height: 1.35;
}
#nearby-suggestions div {
  padding: .18rem .3rem; cursor: pointer; border-radius: 3px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
#nearby-suggestions div:hover, #nearby-suggestions div[aria-selected="true"] {
  background: rgba(128, 128, 128, .28);
}
#nearby-suggestions .nearby-where { opacity: .6; }
#nearby-radius { display: flex; align-items: center; gap: .5rem; margin-top: .4rem; }
/* An id selector beats the user agent's `[hidden] { display: none }`, so the
   slider would sit there before a place had been chosen. */
#nearby-radius[hidden] { display: none; }
#nearby-slider { flex: 1; min-width: 8rem; }
#nearby-distance { font-size: .8em; opacity: .8; min-width: 4.2rem; text-align: right; }
#nearby-count { font-size: .8em; margin-top: .35rem; line-height: 1.4; }
#nearby-count .nearby-caveat { display: block; opacity: .55; font-size: .92em; }
"""

    @property
    def javascript(self) -> str:
        return f"""
(function () {{
  const PLACES = {_payload(self.places)};
  const MIN_KM = {self.min_km}, MAX_KM = {self.max_km}, DEFAULT_KM = {self.default_km};
  const NO_COORD = {self.no_coord};
  const MISSING_SHARE = {self.missing_share:.3f};
  const MAX_SUGGESTIONS = {MAX_SUGGESTIONS};
  const ITEM_ID = "nearby";

  const box = document.getElementById("nearby-container");
  if (!box) return;
  const input = document.getElementById("nearby-place");
  const list = document.getElementById("nearby-suggestions");
  const radius = document.getElementById("nearby-radius");
  const slider = document.getElementById("nearby-slider");
  const distanceOut = document.getElementById("nearby-distance");
  const countOut = document.getElementById("nearby-count");

  // The control is emitted as custom_html, which lands loose at the end of the
  // body. The top-left stack is rendered whether or not the widget system is on,
  // so moving into it puts this under the search box rather than over the map.
  const stack = document.querySelector(".stack.top-left");
  if (stack) stack.appendChild(box);

  // Matching ignores case and accents, so "Zurich" finds "Zürich" and "Malmo"
  // finds "Malmö" — a visitor types the name they can type.
  const fold = (s) => s.normalize("NFD").replace(/\\p{{Diacritic}}/gu, "").toLowerCase();
  const foldedName = PLACES.map((p) => fold(p[0]));
  const foldedRegion = PLACES.map((p) => fold(p[1]));
  const foldedCountry = PLACES.map((p) => fold(p[2]));

  let lat = null, lon = null;   // museum coordinates, from the point metadata
  let distances = null;         // km from the chosen place, per museum
  let place = null;             // [name, country, lat, lon]
  let cursor = -1;              // highlighted suggestion

  const sliderToKm = (v) =>
    Math.exp(Math.log(MIN_KM) + (v / 1000) * (Math.log(MAX_KM) - Math.log(MIN_KM)));
  const kmToSlider = (km) =>
    Math.round(1000 * (Math.log(km) - Math.log(MIN_KM)) /
               (Math.log(MAX_KM) - Math.log(MIN_KM)));

  const fmtKm = (km) => (km < 10 ? km.toFixed(1) : Math.round(km).toLocaleString());
  const fmtN = (n) => n.toLocaleString();

  function haversine(lat1, lon1, lat2, lon2) {{
    const R = 6371.0088;
    const toRad = Math.PI / 180;
    const dLat = (lat2 - lat1) * toRad;
    const dLon = (lon2 - lon1) * toRad;
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }}

  function computeDistances() {{
    if (!place || !lat) {{ distances = null; return; }}
    const n = lat.length;
    const out = new Float64Array(n);
    for (let i = 0; i < n; i++) {{
      // A museum Wikidata has no coordinate for carries the sentinel and is
      // infinitely far from everywhere, so no radius ever reaches it.
      out[i] = lat[i] > NO_COORD - 1 ? Infinity
                                     : haversine(place[3], place[4], lat[i], lon[i]);
    }}
    distances = out;
  }}

  function apply() {{
    const datamap = window.datamap;
    if (!datamap) return;
    if (!place || !distances) {{
      datamap.removeSelection(ITEM_ID);
      countOut.hidden = true;
      return;
    }}
    const km = sliderToKm(+slider.value);
    const hits = [];
    for (let i = 0; i < distances.length; i++) if (distances[i] <= km) hits.push(i);
    datamap.addSelection(hits, ITEM_ID);

    const caveat = `<span class="nearby-caveat">${{(MISSING_SHARE * 100).toFixed(1)}}% of` +
                   ` museums have no recorded coordinates and never appear here.</span>`;
    countOut.innerHTML =
      `<b>${{fmtN(hits.length)}}</b> museum${{hits.length === 1 ? "" : "s"}} ` +
      `within ${{fmtKm(km)}} km of ${{place[0]}}${{caveat}}`;
    countOut.hidden = false;
  }}

  function closeList() {{
    list.hidden = true;
    list.innerHTML = "";
    cursor = -1;
  }}

  // Where a place sits under the typed text, best first: its own name beats the
  // name of something that contains it. Without the tiers, "york" would answer
  // with towns in Yorkshire before it got to York, and typing a region's name is
  // meant to reach the settlements in it, not to outrank a settlement's own name.
  function tierOf(i, q) {{
    if (foldedName[i].startsWith(q)) return 0;
    if (foldedName[i].includes(q)) return 1;
    if (foldedRegion[i].startsWith(q)) return 2;
    if (foldedCountry[i].startsWith(q)) return 3;
    return -1;
  }}

  function where(i) {{
    // A city-state's region is its country; saying it twice reads as an error.
    const [, region, country] = PLACES[i];
    return [region, country].filter((s, j, a) => s && a.indexOf(s) === j).join(", ");
  }}

  function suggest() {{
    const q = fold(input.value.trim());
    if (!q) {{ closeList(); return; }}
    // PLACES is ordered by museum count, so appending within a tier keeps the
    // biggest matches first without a sort.
    const tiers = [[], [], [], []];
    for (let i = 0; i < PLACES.length; i++) {{
      const t = tierOf(i, q);
      if (t >= 0 && tiers[t].length < MAX_SUGGESTIONS) tiers[t].push(i);
    }}
    const hits = [].concat(...tiers).slice(0, MAX_SUGGESTIONS);
    if (!hits.length) {{ closeList(); return; }}
    list.innerHTML = hits
      .map((i) => {{
        const place = where(i);
        const tail = place ? ` <span class="nearby-where">${{place}}</span>` : "";
        return `<div role="option" data-idx="${{i}}">${{PLACES[i][0]}}${{tail}}</div>`;
      }})
      .join("");
    list.hidden = false;
    cursor = -1;
  }}

  function choose(idx) {{
    place = PLACES[idx];
    input.value = place[0];
    closeList();
    radius.hidden = false;
    if (!slider.value || slider.value === "0") slider.value = kmToSlider(DEFAULT_KM);
    distanceOut.textContent = `${{fmtKm(sliderToKm(+slider.value))}} km`;
    computeDistances();
    apply();
  }}

  function clear() {{
    place = null;
    distances = null;
    radius.hidden = true;
    closeList();
    apply();
  }}

  input.addEventListener("input", () => {{
    // A search input's native clear button fires `input` with an empty value.
    if (!input.value.trim()) clear();
    else suggest();
  }});

  input.addEventListener("keydown", (e) => {{
    const options = list.querySelectorAll("div");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {{
      if (!options.length) return;
      e.preventDefault();
      cursor += e.key === "ArrowDown" ? 1 : -1;
      if (cursor < 0) cursor = options.length - 1;
      if (cursor >= options.length) cursor = 0;
      options.forEach((o, i) => o.setAttribute("aria-selected", i === cursor));
      options[cursor].scrollIntoView({{ block: "nearest" }});
    }} else if (e.key === "Enter") {{
      // No highlight means take the top suggestion, so typing a name and
      // pressing Enter does the obvious thing.
      if (options.length) choose(+options[cursor >= 0 ? cursor : 0].dataset.idx);
    }} else if (e.key === "Escape") {{
      closeList();
    }}
  }});

  list.addEventListener("mousedown", (e) => {{
    // mousedown, not click: the input's blur would close the list first.
    const option = e.target.closest("div[data-idx]");
    if (option) {{ e.preventDefault(); choose(+option.dataset.idx); }}
  }});

  input.addEventListener("blur", () => setTimeout(closeList, 120));

  slider.addEventListener("input", () => {{
    distanceOut.textContent = `${{fmtKm(sliderToKm(+slider.value))}} km`;
    apply();
  }});

  function bind() {{
    const meta = window.datamap && window.datamap.metaData;
    if (!meta || !meta.lat || !meta.lon) return;
    lat = meta.lat;
    lon = meta.lon;
    slider.value = kmToSlider(DEFAULT_KM);
    distanceOut.textContent = `${{fmtKm(DEFAULT_KM)}} km`;
  }}

  if (window.datamap && window.datamap.metaData) bind();
  else document.addEventListener("datamapDataLoaded", bind);
}})();
"""
