"""Safe diagnostics for support without exposing a BODS token."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_BODS_API_KEY, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return transport-only state; redact credentials unconditionally."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    selected, groups = await runtime["selection"].get_state()
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, {CONF_BODS_API_KEY}
        ),
        "selected_stop_ids": selected,
        "groups": groups,
        "coordinators": {
            "timetable_success": runtime["departures"].last_update_success,
            "tram_live_success": runtime["live_trams"].last_update_success,
            "bus_live_success": runtime["live_buses"].last_update_success,
        },
    }
