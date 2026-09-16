"""Future-facing selected-stop entities for Greater Manchester Transport."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SIGNAL_SELECTION_CHANGED
from .departures import DepartureCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create a scaffold sensor now for every selected stop."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    selection = runtime["selection"]
    catalogue = runtime["catalogue"]
    departures = runtime["departures"]
    live_trams = runtime["live_trams"]
    live_buses = runtime["live_buses"]
    entities: dict[str, SelectedStopSensor] = {}

    def stop_for(stop_id: str) -> dict[str, Any] | None:
        return next((stop for stop in catalogue.stops if stop["id"] == stop_id), None)

    current_ids = await selection.get_selected()
    initial = [
        SelectedStopSensor(entry.entry_id, stop, selection, departures, live_trams, live_buses)
        for stop_id in current_ids
        if (stop := stop_for(stop_id)) is not None
    ]
    for entity in initial:
        entities[entity.stop_id] = entity
    async_add_entities(initial)

    @callback
    def async_selection_changed(
        changed_entry_id: str, selected_ids: list[str], groups: dict[str, list[str]]
    ) -> None:
        if changed_entry_id != entry.entry_id:
            return
        selected_set = set(selected_ids)
        new_entities = []
        for stop_id in selected_set:
            if stop_id not in entities and (stop := stop_for(stop_id)) is not None:
                entity = SelectedStopSensor(
                    entry.entry_id, stop, selection, departures, live_trams, live_buses
                )
                entities[stop_id] = entity
                new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)
        for stop_id, entity in entities.items():
            entity.monitored = stop_id in selected_set
            entity.groups = [name for name, members in groups.items() if stop_id in members]
            entity.async_write_ha_state()

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SELECTION_CHANGED, async_selection_changed)
    )


class SelectedStopSensor(SensorEntity):
    """A stable selected-stop sensor with its next scheduled departure."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        stop: dict[str, Any],
        selection: Any,
        coordinator: DepartureCoordinator,
        live_trams: Any,
        live_buses: Any,
    ) -> None:
        self._departures = coordinator
        self._selection = selection
        self._live_trams = live_trams
        self._live_buses = live_buses
        self.stop_id = stop["id"]
        self._stop = stop
        self.monitored = True
        self.groups: list[str] = []
        self._attr_unique_id = f"{entry_id}_{self.stop_id}"
        self._attr_name = stop["name"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Greater Manchester Transport",
            manufacturer="Greater Manchester Transport",
            model="Bee Network stop monitor",
        )

    @property
    def icon(self) -> str:
        """Use the correct vehicle icon in HA cards and entity lists."""
        return "mdi:tram" if self._stop.get("mode") == "tram" else "mdi:bus"

    @property
    def native_value(self) -> str:
        if not self.monitored:
            return "Not monitored"
        if not self._departures.last_update_success:
            return "Timetable unavailable"
        next_services = self._next_departures()
        if not next_services:
            return "No upcoming scheduled departures"
        first = next_services[0]
        # A destination is far more useful than a coloured-line label at a
        # shared Metrolink station.  Buses retain their familiar route number.
        if first.get("mode") == "tram":
            return f"{first.get('destination', 'Tram')} {first['time']}"
        return f"{first['route']} {first['time']}"

    async def async_added_to_hass(self) -> None:
        """Refresh the relative departure times once per minute."""
        groups = await self._selection.get_groups()
        self.groups = [name for name, members in groups.items() if self.stop_id in members]
        self.async_on_remove(
            async_track_time_interval(
                self.hass, lambda _now: self.async_write_ha_state(), timedelta(minutes=1)
            )
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        next_services = self._next_departures() if self.monitored else []
        live_tram = bool(self._live_trams.next_departures(self.stop_id))
        live_bus = bool(self._live_buses.next_departures(self.stop_id))
        live_bus_vehicles = (
            self._live_buses.vehicles_for_routes([item.get("route") for item in next_services])
            if self._stop.get("mode") == "bus"
            else []
        )
        return {
            "atco_code": self.stop_id,
            "indicator": self._stop.get("indicator"),
            "street": self._stop.get("street"),
            "locality": self._stop.get("locality"),
            "direction": self._stop.get("direction"),
            "mode": self._stop.get("mode"),
            "latitude": self._stop.get("latitude"),
            "longitude": self._stop.get("longitude"),
            "monitored": self.monitored,
            "groups": self.groups,
            "data_source": (
                "TfGM public live tram departures"
                if live_tram
                else "TfGM public live bus departures"
                if live_bus
                else "BODS live vehicle locations plus TfGM GTFS scheduled timetable"
                if live_bus_vehicles
                else "TfGM public GTFS scheduled timetable"
            ),
            "timetable_updated": self._departures.data.get("loaded") if self._departures.data else None,
            "live_updated": self._live_trams.last_updated(self.stop_id) if live_tram else None,
            "live_vehicle_count": len(live_bus_vehicles),
            "live_vehicles": live_bus_vehicles,
            "disruptions": [
                {
                    "route": item.get("route"),
                    "destination": item.get("destination"),
                    "summary": "TfGM reports a service disruption",
                }
                for item in next_services
                if item.get("is_disrupted")
            ],
            "next_departures": next_services,
        }

    def _next_departures(self) -> list[dict[str, Any]]:
        """Prefer an explicit TfGM live prediction; otherwise use GTFS."""
        if self._stop.get("mode") == "tram":
            live = self._live_trams.next_departures(self.stop_id)
            if live:
                return live
        if self._stop.get("mode") == "bus":
            live = self._live_buses.next_departures(self.stop_id)
            if live:
                return live
        return self._departures.next_departures(self.stop_id)
