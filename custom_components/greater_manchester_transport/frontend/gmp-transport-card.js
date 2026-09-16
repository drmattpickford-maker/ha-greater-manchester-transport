/* Live-updating Lovelace card. It consumes the same entity attributes as the
 * rotary phone, so a future real-time feed needs no card or phone rewrite. */

class GmpTransportDeparturesCard extends HTMLElement {
  constructor() { super(); this.sortMode = "location"; }
  setConfig(config) { this.config = config || {}; this.render(); }
  set hass(hass) { this._hass = hass; this.render(); }
  getCardSize() { return 4; }
  render() {
    if (!this._hass) return;
    const states = Object.values(this._hass.states)
      .filter((state) => state.entity_id.startsWith("sensor.greater_manchester_transport_") && state.state !== "unavailable" && state.attributes.monitored !== false && (!this.config.group || (state.attributes.groups || []).includes(this.config.group)))
      .sort((a, b) => this.sortMode === "time"
        ? ((a.attributes.next_departures || [])[0]?.in_minutes ?? Infinity) - ((b.attributes.next_departures || [])[0]?.in_minutes ?? Infinity)
        : (a.attributes.friendly_name || a.entity_id).localeCompare(b.attributes.friendly_name || b.entity_id));
    const cards = states.map((state) => {
      const next = (state.attributes.next_departures || []).slice(0, 3);
      const source = state.attributes.data_source || "Scheduled timetable";
      const services = next.length ? next.map((item) => `<li><b>${item.route}</b><span>${item.destination || "Destination not shown"}</span><time>${item.in_minutes === 0 ? "Due" : `${item.in_minutes} min`} <small>${item.time || ""}</small></time></li>`).join("") : "<li class=empty>No departures available</li>";
      return `<article><header><div><strong>${state.attributes.friendly_name || state.entity_id}</strong><small>${state.attributes.mode === "tram" ? "Metrolink" : "Bus stop"}</small></div><em>${source.toLowerCase().includes("live") ? "Live" : "Scheduled"}</em></header><ul>${services}</ul></article>`;
    }).join("");
    this.innerHTML = `<style>
      :host{display:block;font-family:var(--primary-font-family,Roboto,sans-serif);color:var(--primary-text-color)} .wrap{padding:16px;background:var(--card-background-color);border-radius:12px}h2{margin:0 0 4px;font-size:20px}.bar{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0 0 15px}.sub{margin:0;color:var(--secondary-text-color);font-size:13px}.sort{display:flex;gap:4px}.sort button{border:1px solid var(--divider-color,#ddd);border-radius:7px;padding:6px 9px;background:var(--secondary-background-color,#fafafa);color:var(--primary-text-color);font:inherit;font-size:12px}.sort button.active{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color)}article{margin:10px 0;border:1px solid var(--divider-color,#ddd);border-radius:10px;overflow:hidden;background:var(--secondary-background-color,#fafafa)}header{display:flex;justify-content:space-between;gap:8px;padding:11px 12px;background:var(--card-background-color,#fff)}header small{display:block;color:var(--secondary-text-color);margin-top:2px}em{align-self:center;font-style:normal;font-size:11px;padding:4px 7px;border-radius:20px;background:#ffca28;color:#222}ul{list-style:none;margin:0;padding:0}li{display:grid;grid-template-columns:42px 1fr auto;gap:7px;padding:9px 12px;border-top:1px solid var(--divider-color,#ddd);font-size:14px}li span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--secondary-text-color)}time{white-space:nowrap;font-weight:600}time small{font-weight:normal;color:var(--secondary-text-color);margin-left:3px}.empty{display:block;color:var(--secondary-text-color)}
    </style><section class=wrap><h2>${this.config.title || "Bee Network departures"}</h2><div class=bar><p class=sub>${this.config.group ? `${this.config.group} stops` : "Selected stops"} — refreshes automatically.</p><div class=sort><button id=location class="${this.sortMode === "location" ? "active" : ""}">Location</button><button id=time class="${this.sortMode === "time" ? "active" : ""}">Soonest</button></div></div>${cards || "<p>No stops are currently monitored in this group. Add them from GM Transport.</p>"}</section>`;
    this.querySelector("#location")?.addEventListener("click", () => { this.sortMode = "location"; this.render(); });
    this.querySelector("#time")?.addEventListener("click", () => { this.sortMode = "time"; this.render(); });
  }
}
// Home Assistant can retain an extra-resource while reloading a custom
// integration (particularly after a Core upgrade).  Defining it twice throws
// before the card can initialise, so treat registration as idempotent.
if (!customElements.get("gmp-transport-departures-card")) {
  customElements.define("gmp-transport-departures-card", GmpTransportDeparturesCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "gmp-transport-departures-card")) {
  window.customCards.push({type:"gmp-transport-departures-card",name:"GM Transport Departures",description:"Selected Bee Network stop departures"});
}
