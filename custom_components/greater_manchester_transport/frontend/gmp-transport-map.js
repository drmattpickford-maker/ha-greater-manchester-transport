/* Greater Manchester Transport: small, touch-first map and stop chooser. */

const TILE = 256;
const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
const GM_FALLBACK_CENTER = {lat: 53.48, lon: -2.24};
const IN_GREATER_MANCHESTER = ({lat, lon}) => lat >= 53.32 && lat <= 53.72 && lon >= -2.75 && lon <= -1.95;

class GmpTransportMap extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this.zoom = 11;
    this.center = {...GM_FALLBACK_CENTER};
    this.initialCenterApplied = false;
    this.visibleStops = [];
    this.selected = new Set();
    this.selectedStops = new Map();
    this.groups = {"Ungrouped": []};
    this.activeGroup = "Ungrouped";
    this.departures = {};
    this.highlighted = null;
    this.listMode = "view";
    this.drag = null;
    this.pan = {x: 0, y: 0};
    this._hass = null;
    this._loaded = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.initialCenterApplied) {
      const candidate = {lat: Number(hass?.config?.latitude), lon: Number(hass?.config?.longitude)};
      this.center = Number.isFinite(candidate.lat) && Number.isFinite(candidate.lon) && IN_GREATER_MANCHESTER(candidate)
        ? candidate : {...GM_FALLBACK_CENTER};
      this.initialCenterApplied = true;
    }
    this.scheduleInitialMap();
    this.loadOnce();
  }
  connectedCallback() { this.render(); this.scheduleInitialMap(); this.loadOnce(); }

  scheduleInitialMap() {
    requestAnimationFrame(() => {
      const map = this.shadowRoot.querySelector("#map");
      if (!this.isConnected || !map || !map.clientWidth || !map.clientHeight) return;
      this.renderMap();
      this.loadOnce();
    });
  }

  async loadOnce() {
    if (!this.isConnected || this._loaded) return;
    const map = this.shadowRoot.querySelector("#map");
    if (!map || !map.clientWidth || !map.clientHeight) {
      this.scheduleInitialMap();
      return;
    }
    this._loaded = true;
    await this.loadView();
  }

  lonToX(lon) { return ((lon + 180) / 360) * (2 ** this.zoom) * TILE; }
  latToY(lat) {
    const radians = (lat * Math.PI) / 180;
    return ((1 - Math.asinh(Math.tan(radians)) / Math.PI) / 2) * (2 ** this.zoom) * TILE;
  }
  xToLon(x) { return (x / ((2 ** this.zoom) * TILE)) * 360 - 180; }
  yToLat(y) {
    const n = Math.PI - (2 * Math.PI * y) / ((2 ** this.zoom) * TILE);
    return (180 / Math.PI) * Math.atan(Math.sinh(n));
  }

  async request(path, options) {
    if (this._hass) return this._hass.callApi(options?.method || "GET", path, options?.body);
    throw new Error("The authenticated Home Assistant panel connection is unavailable.");
  }

  viewportQuery() {
    const map = this.shadowRoot.querySelector("#map");
    const cx = this.lonToX(this.center.lon), cy = this.latToY(this.center.lat);
    return new URLSearchParams({
      south: this.yToLat(cy + map.clientHeight / 2),
      north: this.yToLat(cy - map.clientHeight / 2),
      west: this.xToLon(cx - map.clientWidth / 2),
      east: this.xToLon(cx + map.clientWidth / 2),
    });
  }

  applyData(data) {
    this.visibleStops = data.stops;
    if (this.listMode === "view") {
      this.visibleStops.sort((left, right) => {
        const distance = (stop) => (stop.latitude - this.center.lat) ** 2 + (stop.longitude - this.center.lon) ** 2;
        return distance(left) - distance(right);
      });
    }
    this.selected = new Set(data.selected);
    this.selectedStops = new Map(data.selected_stops.map((stop) => [stop.id, stop]));
    this.groups = data.groups || {"Ungrouped": data.selected || []};
    if (!Object.hasOwn(this.groups, this.activeGroup)) this.activeGroup = Object.keys(this.groups)[0] || "Ungrouped";
    this.departures = data.departures || {};
    this.renderLists();
  }

  async loadView() {
    try {
      this.listMode = "view";
      const data = await this.request(`gmp_transport/stops?${this.viewportQuery()}`);
      this.applyData(data);
      this.setStatus(`${data.stops.length} stops in this view.`);
    } catch (error) { this.setStatus("Could not load stops for this map view."); console.error(error); }
  }

  async search() {
    const query = this.shadowRoot.querySelector("#search").value.trim();
    if (!query) return this.loadView();
    try {
      this.listMode = "search";
      const data = await this.request(`gmp_transport/stops?q=${encodeURIComponent(query)}`);
      this.applyData(data);
      if (data.stops.length) {
        this.center = {
          lat: data.stops.reduce((total, stop) => total + stop.latitude, 0) / data.stops.length,
          lon: data.stops.reduce((total, stop) => total + stop.longitude, 0) / data.stops.length,
        };
        this.zoom = 14;
        this.renderMap();
      }
      this.setStatus(`${data.stops.length} matching stops.`);
    } catch (error) { this.setStatus("Could not search the stop catalogue."); console.error(error); }
  }

  setStatus(message) { const status = this.shadowRoot.querySelector("#status"); if (status) status.textContent = message; }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; }
        .page { min-height:100%; display:grid; grid-template-columns:minmax(0,1fr) 360px; isolation:isolate; background:var(--card-background-color,#fff); color:var(--primary-text-color,#111); }
        #map { position:relative; z-index:0; min-height:430px; overflow:hidden; background:#d7e8f1; touch-action:none; }
        #tiles, #highlight { position:absolute; inset:0; will-change:transform; } .tile { position:absolute; width:256px; height:256px; }
        #highlight { pointer-events:none; } .focus-ring { position:absolute; width:30px; height:30px; transform:translate(-50%,-50%); border:4px solid #ffca28; border-radius:50%; box-shadow:0 0 0 2px #263238; }
        .zoom { position:absolute; z-index:2; top:12px; left:12px; display:grid; gap:5px; } .zoom button { width:38px; height:38px; border:0; border-radius:4px; background:#fff; color:#222; font-size:25px; box-shadow:0 1px 4px #777; }
        aside { position:relative; z-index:1; padding:18px; overflow:auto; background:var(--card-background-color,#fff); border-left:1px solid var(--divider-color,#ddd); } .title { display:flex; align-items:center; gap:10px; } .title img { width:38px; height:38px; } h1 { font-size:22px; margin:0; } h2 { font-size:17px; margin:20px 0 8px; }
        p { line-height:1.4; } .search-row { display:flex; gap:6px; } .search-row input { min-width:0; flex:1; padding:9px; font:inherit; }
        button.action { border:0; border-radius:7px; padding:8px 10px; font:inherit; cursor:pointer; background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); } .group-row { display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:6px; margin:12px 0; } .group-row select { min-width:0; padding:8px; font:inherit; }
        button.remove { background:var(--error-color,#c62828); } ul { list-style:none; padding:0; margin:0; } li.stop { display:grid; grid-template-columns:1fr auto; gap:8px; align-items:center; padding:11px; margin:7px 0; border:1px solid var(--divider-color,#ddd); border-radius:10px; background:var(--secondary-background-color,#fafafa); } .detail { color:var(--secondary-text-color,#555); font-size:12px; }
        #status { min-height:20px; color:var(--secondary-text-color,#555); } @media(max-width:800px) { .page { grid-template-columns:1fr; grid-template-rows:48vh auto; } #map { min-height:0; height:48vh; } aside { padding-top:28px; border-left:0; border-top:1px solid #ddd; } }
      </style>
      <main class="page"><section id="map"><div class="zoom"><button type="button" id="zoom-in" aria-label="Zoom in">+</button><button type="button" id="zoom-out" aria-label="Zoom out">−</button></div><div id="tiles"></div><div id="highlight"></div></section>
      <aside><div class="title"><img src="/gmp_transport_static/gm-transport-bee.svg" alt=""><h1>Greater Manchester Transport</h1></div><p>Move the map to see nearby stops, or search anywhere in Greater Manchester.</p>
      <div class="search-row"><input id="search" type="search" placeholder="Search stop, road or area"><button class="action" id="search-button" type="button">Search</button></div>
      <div class="group-row"><label for="group">Group</label><select id="group"></select><button class="action" id="new-group" type="button">New group</button></div>
      <h2 id="view-title">Stops in this view</h2><ul id="view-list"></ul><h2>Currently monitored</h2><ul id="selected-list"></ul><p id="status" aria-live="polite"></p></aside></main>`;
    const map = this.shadowRoot.querySelector("#map");
    map.addEventListener("pointerdown", (event) => { this.drag = {x:event.clientX, y:event.clientY}; map.setPointerCapture(event.pointerId); });
    map.addEventListener("pointermove", (event) => { if (!this.drag) return; this.pan = {x:event.clientX - this.drag.x, y:event.clientY - this.drag.y}; this.updatePan(); });
    map.addEventListener("pointerup", () => this.endPan());
    map.addEventListener("pointercancel", () => { this.drag = null; this.pan = {x:0,y:0}; this.updatePan(); });
    map.addEventListener("wheel", (event) => { event.preventDefault(); this.zoom = clamp(this.zoom + (event.deltaY < 0 ? 1 : -1), 10, 17); this.renderMap(); this.loadView(); }, {passive:false});
    this.shadowRoot.querySelector("#zoom-in").addEventListener("click", () => { this.zoom = clamp(this.zoom + 1, 10, 17); this.renderMap(); this.loadView(); });
    this.shadowRoot.querySelector("#zoom-out").addEventListener("click", () => { this.zoom = clamp(this.zoom - 1, 10, 17); this.renderMap(); this.loadView(); });
    this.shadowRoot.querySelector("#search-button").addEventListener("click", () => this.search());
    this.shadowRoot.querySelector("#search").addEventListener("keydown", (event) => { if (event.key === "Enter") this.search(); });
    this.shadowRoot.querySelector("#group").addEventListener("change", (event) => { this.activeGroup = event.target.value; this.renderLists(); });
    this.shadowRoot.querySelector("#new-group").addEventListener("click", () => this.createGroup());
  }

  endPan() {
    if (!this.drag) return;
    this.center = {lon:this.xToLon(this.lonToX(this.center.lon) - this.pan.x), lat:this.yToLat(this.latToY(this.center.lat) - this.pan.y)};
    this.drag = null; this.pan = {x:0,y:0}; this.renderMap(); this.loadView();
  }

  renderMap() {
    const map = this.shadowRoot.querySelector("#map"); if (!map) return;
    const tiles = this.shadowRoot.querySelector("#tiles"); const highlight = this.shadowRoot.querySelector("#highlight"); const width = map.clientWidth, height = map.clientHeight;
    const cx = this.lonToX(this.center.lon), cy = this.latToY(this.center.lat), scale = 2 ** this.zoom;
    const left = Math.floor((cx - width / 2) / TILE), top = Math.floor((cy - height / 2) / TILE);
    this.pan = {x:0,y:0}; this.updatePan(); tiles.replaceChildren();
    for (let x = left; x <= Math.ceil((cx + width / 2) / TILE); x++) for (let y = top; y <= Math.ceil((cy + height / 2) / TILE); y++) {
      if (y < 0 || y >= scale) continue;
      const tile = document.createElement("img"); tile.className="tile"; tile.alt=""; tile.draggable=false;
      tile.src=`https://tile.openstreetmap.org/${this.zoom}/${((x % scale) + scale) % scale}/${y}.png`;
      tile.style.left=`${x * TILE - cx + width / 2}px`; tile.style.top=`${y * TILE - cy + height / 2}px`; tiles.append(tile);
    }
    highlight.replaceChildren();
    const stop = this.visibleStops.find((item) => item.id === this.highlighted) || this.selectedStops.get(this.highlighted);
    if (stop) {
      const x = this.lonToX(stop.longitude) - cx + width / 2;
      const y = this.latToY(stop.latitude) - cy + height / 2;
      if (x >= 0 && x <= width && y >= 0 && y <= height) {
        const ring = document.createElement("div"); ring.className = "focus-ring";
        ring.style.left = `${x}px`; ring.style.top = `${y}px`; highlight.append(ring);
      }
    }
  }

  updatePan() {
    const transform = `translate(${this.pan.x}px, ${this.pan.y}px)`;
    this.shadowRoot.querySelector("#tiles").style.transform = transform;
    this.shadowRoot.querySelector("#highlight").style.transform = transform;
  }

  makeStopRow(stop, action) {
    const item = document.createElement("li"); item.className = "stop";
    const text = document.createElement("span"); text.tabIndex = 0; text.setAttribute("role", "button"); text.title = "Highlight on map";
    const suffix = [stop.indicator, stop.street, stop.locality].filter(Boolean).join(" — ");
    const next = this.departures[stop.id]?.[0];
    const scheduled = next ? `Next scheduled: ${next.route} to ${next.destination || "destination not shown"}, ${next.time} (${next.in_minutes} min)` : "";
    text.innerHTML = `${stop.name}<br><span class="detail">${suffix || stop.id}${scheduled ? `<br>${scheduled}` : ""}</span>`;
    text.addEventListener("click", () => this.focusStop(stop));
    text.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") this.focusStop(stop); });
    const inActiveGroup = (this.groups[this.activeGroup] || []).includes(stop.id);
    const button = document.createElement("button"); button.className = `action ${inActiveGroup ? "remove" : ""}`; button.textContent = inActiveGroup ? "Remove" : "Add";
    button.addEventListener("click", () => this.changeSelection(stop, !inActiveGroup));
    item.append(text, button); return item;
  }

  renderLists() {
    const view = this.shadowRoot.querySelector("#view-list"); const selected = this.shadowRoot.querySelector("#selected-list");
    const groupSelect = this.shadowRoot.querySelector("#group");
    groupSelect.replaceChildren(...Object.keys(this.groups).map((name) => { const option = document.createElement("option"); option.value = name; option.textContent = name; option.selected = name === this.activeGroup; return option; }));
    this.shadowRoot.querySelector("#view-title").textContent = this.listMode === "search" ? "Search results" : "Stops in this view (nearest first)";
    view.replaceChildren(); selected.replaceChildren();
    for (const stop of this.visibleStops) view.append(this.makeStopRow(stop));
    for (const stop of this.selectedStops.values()) selected.append(this.makeStopRow(stop));
    if (!this.visibleStops.length) view.textContent = "No stops found in this view.";
    if (!this.selectedStops.size) selected.textContent = "No stops selected yet.";
  }

  focusStop(stop) {
    this.highlighted = stop.id;
    this.renderMap();
  }

  async changeSelection(stop, add) {
    const members = new Set(this.groups[this.activeGroup] || []);
    if (add) { this.selected.add(stop.id); this.selectedStops.set(stop.id, stop); members.add(stop.id); }
    else { members.delete(stop.id); }
    this.groups[this.activeGroup] = [...members];
    const inAnyGroup = Object.values(this.groups).some((items) => items.includes(stop.id));
    if (!inAnyGroup) { this.selected.delete(stop.id); this.selectedStops.delete(stop.id); }
    this.renderLists(); this.setStatus(`${add ? "Adding" : "Removing"} ${stop.name}…`);
    try {
      await this.request("gmp_transport/stops", {method:"POST", body:{selected:[...this.selected], groups:this.groups}});
      this.setStatus(`${add ? "Added" : "Removed"}: ${stop.name}.`);
    } catch (error) {
      this.setStatus("Could not update the monitored stops. Reloading the saved selection."); console.error(error); this._loaded = false; this.loadOnce();
    }
  }

  async createGroup() {
    const name = window.prompt("Name this group, for example Home or Work:", "");
    if (!name) return;
    const cleaned = name.trim().slice(0, 40);
    if (!cleaned) return;
    if (Object.hasOwn(this.groups, cleaned)) { this.setStatus("That group already exists."); return; }
    this.groups[cleaned] = [];
    this.activeGroup = cleaned;
    try {
      await this.request("gmp_transport/stops", {method:"POST", body:{selected:[...this.selected], groups:this.groups}});
      this.renderLists(); this.setStatus(`Created group: ${cleaned}.`);
    } catch (error) { delete this.groups[cleaned]; this.activeGroup = Object.keys(this.groups)[0] || "Ungrouped"; this.renderLists(); this.setStatus("Could not create the group."); console.error(error); }
  }
}

customElements.define("gmp-transport-map", GmpTransportMap);
