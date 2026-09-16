"""Refreshable official Greater Manchester stop catalogue."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import CATALOGUE_STORE_KEY, CATALOGUE_STORE_VERSION, NAPTAN_GM_URL

CATALOGUE_MAX_AGE = timedelta(days=7)


class GreaterManchesterStopCatalogue:
    """Cache the official NaPTAN record set and expose small search results."""

    def __init__(self, hass: Any, fallback: list[dict[str, Any]]) -> None:
        self.hass = hass
        self._store = Store[dict[str, Any]](hass, CATALOGUE_STORE_VERSION, CATALOGUE_STORE_KEY)
        self._fallback = fallback
        self.stops: list[dict[str, Any]] = fallback
        self.updated: datetime | None = None

    async def async_load(self) -> None:
        """Load an existing catalogue without delaying Home Assistant startup."""
        data = await self._store.async_load() or {}
        saved_stops = data.get("stops")
        if isinstance(saved_stops, list) and saved_stops:
            self.stops = saved_stops
        try:
            self.updated = datetime.fromisoformat(data.get("updated", ""))
        except ValueError:
            self.updated = None

    async def async_refresh_if_due(self) -> None:
        """Fetch a fresh OGL NaPTAN data file once a week."""
        if self.updated and datetime.now(UTC) - self.updated < CATALOGUE_MAX_AGE:
            return
        session = async_get_clientsession(self.hass)
        async with session.get(NAPTAN_GM_URL, timeout=60) as response:
            response.raise_for_status()
            csv_text = await response.text()

        stops: list[dict[str, Any]] = []
        for row in csv.DictReader(StringIO(csv_text)):
            if row.get("Status", "").lower() != "active":
                continue
            try:
                latitude = float(row["Latitude"])
                longitude = float(row["Longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            name = row.get("CommonName") or row.get("ShortCommonName") or "Unnamed stop"
            indicator = row.get("Indicator") or ""
            street = row.get("Street") or ""
            locality = row.get("LocalityName") or ""
            stop_type = row.get("StopType") or ""
            stops.append(
                {
                    "id": row["ATCOCode"],
                    "name": name,
                    "indicator": indicator,
                    "street": street,
                    "locality": locality,
                    "mode": "tram" if stop_type in {"MET", "TMU"} else "bus",
                    "direction": row.get("Bearing") or "",
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )
        if not stops:
            raise ValueError("NaPTAN returned no usable Greater Manchester stops")
        self.stops = stops
        self.updated = datetime.now(UTC)
        await self._store.async_save({"updated": self.updated.isoformat(), "stops": stops})

    def search(self, query: str = "", limit: int = 40) -> list[dict[str, Any]]:
        """Return a manageable, case-insensitive selection for the map panel."""
        words = [word for word in query.casefold().split() if word]
        matches: list[dict[str, Any]] = []
        for stop in self.stops:
            haystack = " ".join(
                str(stop.get(field, "")) for field in ("name", "indicator", "street", "locality", "id")
            ).casefold()
            if all(word in haystack for word in words):
                matches.append(stop)
                if len(matches) == limit:
                    break
        return matches

    def in_bounds(
        self, south: float, west: float, north: float, east: float, limit: int = 40
    ) -> list[dict[str, Any]]:
        """Return stops currently visible in a map viewport, nearest first."""
        centre_lat = (south + north) / 2
        centre_lon = (west + east) / 2
        visible = [
            stop
            for stop in self.stops
            if south <= float(stop["latitude"]) <= north
            and west <= float(stop["longitude"]) <= east
        ]
        return sorted(
            visible,
            key=lambda stop: (float(stop["latitude"]) - centre_lat) ** 2
            + (float(stop["longitude"]) - centre_lon) ** 2,
        )[:limit]

    def has_ids(self, ids: list[str]) -> bool:
        known_ids = {str(stop.get("id")) for stop in self.stops}
        return all(item in known_ids for item in ids)
