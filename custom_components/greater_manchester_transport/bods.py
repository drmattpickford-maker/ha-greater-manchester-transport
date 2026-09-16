"""Small, guarded client for BODS live-vehicle data.

The integration keeps the key in Home Assistant's server-side config-entry
storage.  It is never placed into the browser panel, entity state, diagnostics
or a request URL.
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import BODS_GM_BOUNDING_BOX, BODS_SIRI_VM_URL, CONF_BODS_API_KEY


class BodsClient:
    """Fetch BODS data without exposing the consumer token."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self._session = async_get_clientsession(hass)
        self._key = config.get(CONF_BODS_API_KEY, "")

    @property
    def configured(self) -> bool:
        """Whether the user elected to use BODS live data."""
        return bool(self._key)

    async def async_fetch_vehicles(self, bounding_box: str = BODS_GM_BOUNDING_BOX) -> list[dict[str, Any]] | None:
        """Return live GM vehicle locations from BODS's supported SIRI-VM feed.

        The feed currently provides vehicle positions and service information,
        but no monitored/onward stop calls for Greater Manchester.  Callers
        must therefore use it only as a live vehicle indicator, never as an
        invented arrival prediction.
        """
        if not self.configured:
            return None
        try:
            async with self._session.get(
                BODS_SIRI_VM_URL,
                params={"api_key": self._key, "boundingBox": bounding_box},
                timeout=30,
            ) as response:
                response.raise_for_status()
                return self._parse_siri(await response.text())
        except (ClientError, TimeoutError, ValueError, ElementTree.ParseError):
            return None

    @staticmethod
    def _text(element: ElementTree.Element | None, name: str) -> str:
        """Read one namespaced SIRI child without coupling to its namespace."""
        if element is None:
            return ""
        found = element.find(f"{{*}}{name}")
        return (found.text or "").strip() if found is not None else ""

    @classmethod
    def _parse_siri(cls, payload: str) -> list[dict[str, Any]]:
        """Extract only the useful, non-identifying live service fields."""
        root = ElementTree.fromstring(payload)
        vehicles: list[dict[str, Any]] = []
        for activity in root.findall(".//{*}VehicleActivity"):
            journey = activity.find("{*}MonitoredVehicleJourney")
            location = journey.find("{*}VehicleLocation") if journey is not None else None
            try:
                latitude = float(cls._text(location, "Latitude"))
                longitude = float(cls._text(location, "Longitude"))
            except ValueError:
                continue
            route = cls._text(journey, "PublishedLineName") or cls._text(journey, "LineRef")
            if not route:
                continue
            vehicles.append(
                {
                    "route": route,
                    "destination": cls._text(journey, "DestinationName"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "recorded_at": cls._text(activity, "RecordedAtTime"),
                }
            )
        return vehicles
