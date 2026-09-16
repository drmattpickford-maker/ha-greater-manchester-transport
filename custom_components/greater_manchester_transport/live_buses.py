"""Genuine TfGM ATCO bus-stop boards, with BODS vehicle-presence signals."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .bods import BodsClient
from .const import DOMAIN, TFGM_LIVE_BUS_PAGE


def _normalise_route(value: object) -> str:
    """Make route-number matching tolerant of harmless spacing/case changes."""
    return "".join(str(value or "").upper().split())


class LiveBusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Refresh live departure boards and a bounded BODS vehicle feed."""

    def __init__(self, hass: HomeAssistant, selection: Any, catalogue: Any, config: dict[str, Any]) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_live_buses",
            update_interval=timedelta(minutes=1),
        )
        self._selection = selection
        self._catalogue = catalogue
        self._client = BodsClient(hass, config)

    @property
    def bods_configured(self) -> bool:
        """Whether a BODS token was supplied through the config flow."""
        return self._client.configured

    async def _async_update_data(self) -> dict[str, Any]:
        selected = await self._selection.get_selected()
        stops_by_id = {str(stop["id"]): stop for stop in self._catalogue.stops}
        bus_stops = [
            (stop_id, stops_by_id[stop_id])
            for stop_id in selected
            if stop_id in stops_by_id and stops_by_id[stop_id].get("mode") == "bus"
        ]
        boards: dict[str, list[dict[str, Any]]] = {}
        if bus_stops:
            session = async_get_clientsession(self.hass)
            board_groups: dict[str, list[str]] = {}
            for stop_id, stop in bus_stops:
                # TfGM's public bus board accepts an ATCO code for ordinary
                # roadside stops as well as a friendly interchange slug.
                board_groups.setdefault(str(stop["id"]), []).append(stop_id)
            for board_key, stop_ids in board_groups.items():
                try:
                    async with session.get(
                        TFGM_LIVE_BUS_PAGE.format(slug=board_key),
                        headers={"User-Agent": "GreaterManchesterTransport/0.1 (Home Assistant)"},
                        timeout=30,
                    ) as response:
                        response.raise_for_status()
                        departures = self._parse_tf_gm_board(await response.text())
                except Exception:
                    # A missing or temporarily changed public board must leave
                    # the usual GTFS timetable available for that stop.
                    continue
                for stop_id in stop_ids:
                    boards[stop_id] = departures

        vehicles: list[dict[str, Any]] = []
        if self.bods_configured and bus_stops:
            fetched = await self._client.async_fetch_vehicles(self._vehicle_bounding_box(bus_stops))
            if fetched is None and not boards:
                raise UpdateFailed("Unable to read BODS live vehicle locations")
            vehicles = fetched or []
        return {
            "stops": boards,
            "vehicles": vehicles,
            "loaded": dt_util.utcnow().isoformat(),
        }

    @staticmethod
    def _vehicle_bounding_box(stops: list[tuple[str, dict[str, Any]]]) -> str:
        """Use a small envelope around the selected stops, not all of GM."""
        latitudes = [float(stop["latitude"]) for _, stop in stops]
        longitudes = [float(stop["longitude"]) for _, stop in stops]
        # About two miles' margin. This is a live-presence hint rather than an
        # ETA, so the modest scope avoids an unnecessary national-scale poll.
        margin = 0.03
        return ",".join(
            f"{value:.5f}"
            for value in (
                min(longitudes) - margin,
                min(latitudes) - margin,
                max(longitudes) + margin,
                max(latitudes) + margin,
            )
        )

    @staticmethod
    def _extract_departure_array(page: str) -> str:
        """Extract the first public Next.js ``data.departures`` JSON array."""
        text = page.replace(r'\"', '"')
        marker = '"data":{"departures":'
        start = text.find(marker)
        if start < 0:
            raise ValueError("TfGM page did not contain a live departure board")
        array_start = start + len(marker)
        if array_start >= len(text) or text[array_start] != "[":
            raise ValueError("TfGM live departure board was not an array")
        depth = 0
        quoted = False
        escaped = False
        for index in range(array_start, len(text)):
            char = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[array_start : index + 1]
        raise ValueError("TfGM live departure board was incomplete")

    @classmethod
    def _parse_tf_gm_board(cls, page: str) -> list[dict[str, Any]]:
        """Keep only explicit expected times from TfGM's public board."""
        departures: list[dict[str, Any]] = []
        for item in json.loads(cls._extract_departure_array(page)):
            service = item.get("service", {})
            timing = item.get("timings", {})
            expected = dt_util.parse_datetime(timing.get("expectedDepartureTime", ""))
            wait = int(timing.get("wait", 0))
            if service.get("mode") != "BUS" or expected is None or wait < 0:
                continue
            departures.append(
                {
                    "route": service.get("name", "Service"),
                    "destination": service.get("destination", "Destination not shown"),
                    "description": "TfGM live bus departure",
                    "mode": "bus",
                    "time": dt_util.as_local(expected).strftime("%H:%M"),
                    "in_minutes": wait,
                    "status": timing.get("status") or "Live",
                    "expected_departure": timing["expectedDepartureTime"],
                    "platform": item.get("platformStand"),
                    "is_disrupted": bool(item.get("isDisrupted")),
                }
            )
        return sorted(departures, key=lambda item: (item["in_minutes"], item["time"]))

    def next_departures(self, stop_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return TfGM's real-time departures at a supported interchange."""
        return list((self.data or {}).get("stops", {}).get(stop_id, []))[:limit]

    def vehicles_for_routes(self, routes: list[object]) -> list[dict[str, Any]]:
        """Find reported BODS vehicles for a stop's scheduled route numbers."""
        wanted = {_normalise_route(route) for route in routes}
        return [
            vehicle
            for vehicle in (self.data or {}).get("vehicles", [])
            if _normalise_route(vehicle.get("route")) in wanted
        ]
