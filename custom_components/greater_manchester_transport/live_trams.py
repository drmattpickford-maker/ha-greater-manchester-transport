"""Read the public TfGM live-departures payload for selected tram stops.

TfGM's public stop pages server-render a small structured ``travelInfo``
payload.  This is intentionally a conservative reader: only fields explicitly
labelled by TfGM as expected/live are exposed, and an unavailable page simply
leaves scheduled GTFS as the integration's fallback.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, TFGM_LIVE_TRAM_PAGE

# A small number of NaPTAN names use a different public TfGM page title.
TRAM_SLUG_OVERRIDES = {
    "rochdale interchange": "rochdale-town-centre",
}


class LiveTramCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Refresh TfGM's live tram board once a minute for monitored stations."""

    def __init__(self, hass: HomeAssistant, selection: Any, catalogue: Any) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_live_trams",
            update_interval=timedelta(minutes=1),
        )
        self._selection = selection
        self._catalogue = catalogue

    async def _async_update_data(self) -> dict[str, Any]:
        selected = await self._selection.get_selected()
        stops_by_id = {str(stop["id"]): stop for stop in self._catalogue.stops}
        tram_stops = [
            (stop_id, stops_by_id[stop_id])
            for stop_id in selected
            if stop_id in stops_by_id and stops_by_id[stop_id].get("mode") == "tram"
        ]
        if not tram_stops:
            return {"stops": {}, "loaded": dt_util.utcnow().isoformat()}

        # Both directions at a station resolve to the same public stop page.
        station_groups: dict[str, list[str]] = {}
        for stop_id, stop in tram_stops:
            station_groups.setdefault(self._slug(stop), []).append(stop_id)

        try:
            session = async_get_clientsession(self.hass)
            results: dict[str, list[dict[str, Any]]] = {}
            updated: dict[str, str | None] = {}
            for slug, stop_ids in station_groups.items():
                async with session.get(
                    TFGM_LIVE_TRAM_PAGE.format(slug=slug),
                    headers={"User-Agent": "GreaterManchesterTransport/0.1 (Home Assistant)"},
                    timeout=30,
                ) as response:
                    response.raise_for_status()
                    departures, last_updated = self._parse(await response.text())
                for stop_id in stop_ids:
                    results[stop_id] = departures
                    updated[stop_id] = last_updated
            return {
                "stops": results,
                "updated": updated,
                "loaded": dt_util.utcnow().isoformat(),
            }
        except Exception as err:
            raise UpdateFailed(f"Unable to read TfGM live tram data: {err}") from err

    @staticmethod
    def _slug(stop: dict[str, Any]) -> str:
        """Turn the public NaPTAN station name into TfGM's public URL slug."""
        name = str(stop.get("name", ""))
        name = re.sub(r"\s*\(Manchester Metrolink\)\s*", "", name, flags=re.I)
        name = re.sub(r"\s+tram stop\s*$", "", name, flags=re.I)
        stem = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        stem = TRAM_SLUG_OVERRIDES.get(stem, stem)
        return f"{stem}-tram"

    @staticmethod
    def _parse(page: str) -> tuple[list[dict[str, Any]], str | None]:
        """Extract TfGM's server-rendered live travelInfo data safely."""
        marker = r'\"travelInfo\":'
        start = page.find(marker)
        end = page.find(r',\"alerts\":', start)
        if start < 0 or end < 0:
            raise ValueError("TfGM page did not contain live travel information")
        # ``end`` points at the comma immediately after travelInfo's closing
        # brace, so restore that brace before decoding the extracted object.
        payload_json = (page[start + len(marker) : end] + "}").replace(r'\"', '"')
        payload = json.loads(payload_json)
        departures: list[dict[str, Any]] = []
        last_updated: str | None = None
        for item in payload.get("departures", []):
            service = item.get("service", {})
            timing = item.get("timings", {})
            if service.get("mode") != "TRAM" or "expectedDepartureTime" not in timing:
                continue
            expected = dt_util.parse_datetime(timing["expectedDepartureTime"])
            if expected is None:
                continue
            if timing.get("lastUpdated"):
                last_updated = timing["lastUpdated"]
            wait = int(timing.get("wait", 0))
            if wait < 0:
                continue
            departures.append(
                {
                    "route": "Metrolink",
                    "destination": service.get("destination", "Destination not shown"),
                    "description": "TfGM live tram departure",
                    "mode": "tram",
                    "time": dt_util.as_local(expected).strftime("%H:%M"),
                    # TfGM provides this as its own board's displayed wait,
                    # rather than us inventing an ETA from a timetable.
                    "in_minutes": wait,
                    "status": timing.get("status", "Live"),
                    "expected_departure": timing["expectedDepartureTime"],
                }
            )
        return departures, last_updated

    def next_departures(self, stop_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return public live departures for one selected tram stop."""
        return list((self.data or {}).get("stops", {}).get(stop_id, []))[:limit]

    def last_updated(self, stop_id: str) -> str | None:
        return (self.data or {}).get("updated", {}).get(stop_id)
