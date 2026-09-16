"""Scheduled Bee Network departures from TfGM's public GTFS feed."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from io import BytesIO, TextIOWrapper
from typing import Any
from zipfile import ZipFile

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, TFGM_GTFS_URL


def _seconds(value: str) -> int:
    """Convert GTFS time, including valid after-midnight values, to seconds."""
    hour, minute, second = (int(part) for part in value.split(":"))
    return hour * 3600 + minute * 60 + second


def _gtfs_date(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


class DepartureCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Download a timetable and retain only trips that serve monitored stops."""

    def __init__(self, hass: HomeAssistant, selection: Any) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            # Timetables change far less often than departure clocks do.
            update_interval=timedelta(hours=6),
        )
        self._selection = selection

    async def _async_update_data(self) -> dict[str, Any]:
        selected = await self._selection.get_selected()
        if not selected:
            return {"stops": {}, "loaded": dt_util.utcnow().isoformat()}
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(TFGM_GTFS_URL, timeout=90) as response:
                response.raise_for_status()
                archive = await response.read()
            return self._parse(archive, selected)
        except Exception as err:  # feed availability must not break HA startup
            raise UpdateFailed(f"Unable to download TfGM timetable: {err}") from err

    def _parse(self, archive: bytes, selected: list[str]) -> dict[str, Any]:
        """Build a compact, selected-stops-only view of a GTFS archive."""
        selected_set = set(selected)
        with ZipFile(BytesIO(archive)) as zf:
            stop_ids: dict[str, set[str]] = {item: set() for item in selected}
            with TextIOWrapper(zf.open("stops.txt"), encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    stop_id = row.get("stop_id", "")
                    code = row.get("stop_code", "")
                    parent = row.get("parent_station", "")
                    for selected_id in selected_set:
                        # Metrolink stations commonly have platform codes such as
                        # 9400ZZMAPWC1 and 9400ZZMAPWC2 under one NaPTAN station.
                        if (
                            code == selected_id
                            or stop_id == selected_id
                            or parent == selected_id
                            or code.startswith(selected_id)
                            # NaPTAN uses both 1800 and 9400 prefixes for the
                            # same Metrolink platform identifiers.
                            or (len(code) > 4 and len(selected_id) > 4 and code[4:] == selected_id[4:])
                        ):
                            stop_ids[selected_id].add(stop_id)

            trips: dict[str, dict[str, str]] = {}
            with TextIOWrapper(zf.open("trips.txt"), encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    trips[row["trip_id"]] = {
                        "route_id": row.get("route_id", ""),
                        "service_id": row.get("service_id", ""),
                        "headsign": row.get("trip_headsign", ""),
                    }

            routes: dict[str, dict[str, str]] = {}
            with TextIOWrapper(zf.open("routes.txt"), encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    routes[row["route_id"]] = {
                        "route": row.get("route_short_name") or row.get("route_long_name") or "Service",
                        "description": row.get("route_long_name", ""),
                        "type": row.get("route_type", ""),
                    }

            calendar: dict[str, dict[str, Any]] = {}
            with TextIOWrapper(zf.open("calendar.txt"), encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    calendar[row["service_id"]] = {
                        "days": [row.get(day) == "1" for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")],
                        "start": _gtfs_date(row["start_date"]),
                        "end": _gtfs_date(row["end_date"]),
                    }
            exceptions: dict[tuple[str, date], bool] = {}
            with TextIOWrapper(zf.open("calendar_dates.txt"), encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    exceptions[(row["service_id"], _gtfs_date(row["date"]))] = row.get("exception_type") == "1"

            wanted_by_gtfs_id = {
                gtfs_id: selected_id
                for selected_id, ids in stop_ids.items()
                for gtfs_id in ids
            }
            departures: dict[str, list[dict[str, Any]]] = {item: [] for item in selected}
            with TextIOWrapper(zf.open("stop_times.txt"), encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    selected_id = wanted_by_gtfs_id.get(row.get("stop_id", ""))
                    if not selected_id:
                        continue
                    trip = trips.get(row.get("trip_id", ""))
                    if not trip:
                        continue
                    route = routes.get(trip["route_id"], {})
                    time = row.get("departure_time") or row.get("arrival_time")
                    if not time:
                        continue
                    departures[selected_id].append(
                        {
                            "seconds": _seconds(time),
                            "service_id": trip["service_id"],
                            "route": route.get("route", "Service"),
                            "destination": trip["headsign"],
                            "description": route.get("description", ""),
                            "mode": "tram" if route.get("type") == "0" else "bus",
                        }
                    )

        for items in departures.values():
            items.sort(key=lambda item: item["seconds"])
        return {
            "stops": departures,
            "calendar": calendar,
            "exceptions": exceptions,
            "loaded": dt_util.utcnow().isoformat(),
        }

    def next_departures(self, selected_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return the next scheduled departures using the local GTFS calendar."""
        if not self.data:
            return []
        now = dt_util.now()
        items = self.data.get("stops", {}).get(selected_id, [])
        results: list[dict[str, Any]] = []
        for day_offset in range(2):
            service_day = now.date() + timedelta(days=day_offset)
            now_seconds = now.hour * 3600 + now.minute * 60 + now.second
            for item in items:
                if day_offset == 0 and item["seconds"] < now_seconds:
                    continue
                if not self._service_runs(item["service_id"], service_day):
                    continue
                event = dict(item)
                event_time = datetime.combine(service_day, datetime.min.time()) + timedelta(seconds=item["seconds"])
                event["time"] = event_time.strftime("%H:%M")
                event["in_minutes"] = max(0, round((event_time - now.replace(tzinfo=None)).total_seconds() / 60))
                event.pop("seconds", None)
                event.pop("service_id", None)
                results.append(event)
            if len(results) >= limit:
                break
        return sorted(results, key=lambda item: (item["in_minutes"], item["time"]))[:limit]

    def _service_runs(self, service_id: str, service_day: date) -> bool:
        exception = self.data.get("exceptions", {}).get((service_id, service_day))
        if exception is not None:
            return exception
        service = self.data.get("calendar", {}).get(service_id)
        return bool(service and service["start"] <= service_day <= service["end"] and service["days"][service_day.weekday()])
