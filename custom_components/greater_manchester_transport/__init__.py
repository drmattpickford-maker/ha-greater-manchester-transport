"""Greater Manchester Transport custom integration."""

from __future__ import annotations

import json
from pathlib import Path

from aiohttp import web
from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .catalogue import GreaterManchesterStopCatalogue
from .departures import DepartureCoordinator
from .live_buses import LiveBusCoordinator
from .live_trams import LiveTramCoordinator
from .const import (
    DOMAIN,
    PANEL_PATH,
    PANEL_URL,
    SIGNAL_SELECTION_CHANGED,
    STORE_KEY,
    STORE_VERSION,
)

PLATFORMS: list[Platform] = [Platform.SENSOR]
CARD_RESOURCE_URL = f"{PANEL_URL}/gmp-transport-card.js?v=20260903-3"


def _load_stops() -> list[dict]:
    """Read the currently bundled stop catalogue.

    The catalogue is deliberately small in this first prototype.  The GTFS
    downloader will replace it with the full regional catalogue in the data
    release; keeping this panel local means it never needs an address.
    """
    return json.loads((Path(__file__).parent / "stops.json").read_text(encoding="utf-8"))


class StopSelectionStore:
    """Persist a user's map selections outside entity state."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict](hass, STORE_VERSION, STORE_KEY)
        self._hass = hass
        self._entry_id = entry_id

    async def get_selected(self) -> list[str]:
        selected, _groups = await self.get_state()
        return selected

    async def get_state(self) -> tuple[list[str], dict[str, list[str]]]:
        """Read selections and named groups, migrating the original store."""
        data = await self._store.async_load() or {}
        selected = [str(item) for item in data.get("selected", [])]
        raw_groups = data.get("groups")
        if not isinstance(raw_groups, dict):
            raw_groups = {"Ungrouped": selected}
        groups: dict[str, list[str]] = {}
        selected_set = set(selected)
        for name, items in raw_groups.items():
            cleaned_name = str(name).strip()[:40]
            if not cleaned_name or not isinstance(items, list):
                continue
            groups[cleaned_name] = [str(item) for item in items if str(item) in selected_set]
        if not groups:
            groups = {"Ungrouped": selected}
        return selected, groups

    async def get_groups(self) -> dict[str, list[str]]:
        """Return a copy of the current named group assignments."""
        _selected, groups = await self.get_state()
        return groups

    async def set_selected(self, selected: list[str]) -> None:
        _old_selected, groups = await self.get_state()
        await self.set_state(selected, groups)

    async def set_state(self, selected: list[str], groups: dict[str, list[str]]) -> None:
        """Persist a validated selection and its user-facing group labels."""
        selected = list(dict.fromkeys(str(item) for item in selected))
        selected_set = set(selected)
        cleaned_groups: dict[str, list[str]] = {}
        for name, items in groups.items():
            cleaned_name = str(name).strip()[:40]
            if not cleaned_name or not isinstance(items, list):
                continue
            cleaned_groups[cleaned_name] = list(
                dict.fromkeys(str(item) for item in items if str(item) in selected_set)
            )
        if not cleaned_groups:
            cleaned_groups = {"Ungrouped": selected}
        await self._store.async_save({"selected": selected, "groups": cleaned_groups})
        async_dispatcher_send(
            self._hass, SIGNAL_SELECTION_CHANGED, self._entry_id, selected, cleaned_groups
        )


class StopsView(HomeAssistantView):
    """Authenticated API for the Home Assistant map panel."""

    url = "/api/gmp_transport/stops"
    name = "api:gmp_transport:stops"
    requires_auth = True

    def __init__(
        self,
        selection: StopSelectionStore,
        catalogue: GreaterManchesterStopCatalogue,
        departures: DepartureCoordinator,
    ) -> None:
        self._selection = selection
        self._catalogue = catalogue
        self._departures = departures

    async def get(self, request: web.Request) -> web.Response:
        query = request.query.get("q", "")
        bounds = ("south", "west", "north", "east")
        if not query and all(name in request.query for name in bounds):
            try:
                stops = self._catalogue.in_bounds(
                    *(float(request.query[name]) for name in bounds)
                )
            except ValueError:
                return self.json_message("Invalid map viewport", status_code=400)
        else:
            stops = self._catalogue.search(query)
        selected, groups = await self._selection.get_state()
        selected_by_id = {str(stop["id"]): stop for stop in self._catalogue.stops}
        return self.json(
            {
                "stops": stops,
                "selected": selected,
                "selected_stops": [
                    selected_by_id[item] for item in selected if item in selected_by_id
                ],
                "groups": groups,
                "stop_groups": {
                    item: [name for name, members in groups.items() if item in members]
                    for item in selected
                },
                "query": query,
                "departures": {
                    item: self._departures.next_departures(item)
                    for item in selected
                },
                "catalogue_updated": self._catalogue.updated.isoformat()
                if self._catalogue.updated
                else None,
            }
        )

    async def post(self, request: web.Request) -> web.Response:
        payload = await request.json()
        requested = payload.get("selected", [])
        groups = payload.get("groups")
        if not isinstance(requested, list) or not self._catalogue.has_ids(requested):
            return self.json_message("Unknown stop selection", status_code=400)
        if groups is None:
            _previous, groups = await self._selection.get_state()
        if not isinstance(groups, dict):
            return self.json_message("Invalid stop groups", status_code=400)
        await self._selection.set_state(requested, groups)
        return self.json({"selected": requested, "groups": groups})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration and its configuration map."""
    selection = StopSelectionStore(hass, entry.entry_id)
    # Home Assistant 2026.9 treats filesystem reads in the event loop as a
    # blocking-call error.  The bundled catalogue is tiny, but still belongs
    # in the executor to keep integration start-up fully async-safe.
    catalogue = GreaterManchesterStopCatalogue(
        hass, await hass.async_add_executor_job(_load_stops)
    )
    await catalogue.async_load()
    departures = DepartureCoordinator(hass, selection)
    live_trams = LiveTramCoordinator(hass, selection, catalogue)
    transport_config = dict(entry.data)
    transport_config.update(entry.options)
    live_buses = LiveBusCoordinator(hass, selection, catalogue, transport_config)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "selection": selection,
        "catalogue": catalogue,
        "departures": departures,
        "live_trams": live_trams,
        "live_buses": live_buses,
    }
    # Do not delay Home Assistant startup on a public download. The bundled
    # sample remains usable until the full official catalogue arrives.
    hass.async_create_task(catalogue.async_refresh_if_due())
    # This is intentionally non-blocking: HA and the stop picker still work if
    # TfGM are temporarily unavailable.
    hass.async_create_task(departures.async_config_entry_first_refresh())
    hass.async_create_task(live_trams.async_config_entry_first_refresh())
    hass.async_create_task(live_buses.async_config_entry_first_refresh())

    @callback
    def async_refresh_departures(
        changed_entry_id: str, _selected: list[str], _groups: dict[str, list[str]]
    ) -> None:
        if changed_entry_id == entry.entry_id:
            hass.async_create_task(departures.async_request_refresh())
            hass.async_create_task(live_trams.async_request_refresh())
            hass.async_create_task(live_buses.async_request_refresh())

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SELECTION_CHANGED, async_refresh_departures)
    )

    static_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(static_dir), cache_headers=False)]
    )
    # Load the optional dashboard card with the integration.  This avoids a
    # separate Lovelace-resource step and works in the mobile companion app.
    frontend.add_extra_js_url(hass, CARD_RESOURCE_URL)
    hass.http.register_view(StopsView(selection, catalogue, departures))
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="gmp-transport-map",
        frontend_url_path=PANEL_PATH,
        # Bump this small cache key whenever the panel changes: the Home
        # Assistant mobile companion otherwise keeps an older ES module open.
        module_url=f"{PANEL_URL}/gmp-transport-map.js?v=20260904-14",
        config={"entry_id": entry.entry_id},
        sidebar_title="GM Transport",
        sidebar_icon="mdi:tram",
        embed_iframe=False,
        require_admin=True,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration's runtime state."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    frontend.remove_extra_js_url(hass, CARD_RESOURCE_URL)
    frontend.async_remove_panel(hass, PANEL_PATH)
    return unload_ok
