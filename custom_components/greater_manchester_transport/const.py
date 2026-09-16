"""Constants for Greater Manchester Transport."""

from __future__ import annotations

DOMAIN = "greater_manchester_transport"
PANEL_URL = "/gmp_transport_static"
PANEL_PATH = "gmp-transport-map"
STORE_KEY = f"{DOMAIN}.selection"
# Version 1 already contained the selected-stop list.  Groups are optional
# data inside that same structure, so keeping the storage major version at 1
# preserves existing installations without requiring a Store migration hook.
STORE_VERSION = 1
CATALOGUE_STORE_KEY = f"{DOMAIN}.naptan_catalogue"
CATALOGUE_STORE_VERSION = 1
# Official DfT National Public Transport Access Nodes data, Greater Manchester.
NAPTAN_GM_URL = "https://naptan.api.dft.gov.uk/v1/access-nodes?atcoAreaCodes=180&dataFormat=csv"
# TfGM's public regional GTFS timetable.  This is deliberately a scheduled
# source: a missed service is not presented as a real-time prediction.
TFGM_GTFS_URL = "https://odata.tfgm.com/opendata/downloads/TfGMgtfsnew.zip"
# TfGM's public, server-rendered live board.  It is used only for tram data
# with an explicit expected-departure value; GTFS remains the fallback.
TFGM_LIVE_TRAM_PAGE = "https://tfgm.com/travel-updates/live-departures/tram/{slug}"
# Interchange boards contain public expected bus departure times. These are
# materially better than vehicle positions, but only exist for named hubs.
TFGM_LIVE_BUS_PAGE = "https://tfgm.com/travel-updates/live-departures/bus/{slug}"
SIGNAL_SELECTION_CHANGED = f"{DOMAIN}_selection_changed"

CONF_BODS_API_KEY = "bods_api_key"
CONF_BODS_AUTH_HEADER = "bods_auth_header"
# BODS replaced its earlier vehicle-data endpoint with the SIRI-VM feed.  The
# key is required by BODS as a query parameter and is kept server-side in the
# config entry; it is never returned from the integration's API or sensors.
BODS_SIRI_VM_URL = "https://data.bus-data.dft.gov.uk/api/v1/datafeed/"
# A deliberately small regional envelope: avoid fetching the national live
# vehicle feed for a Greater Manchester-only integration.
BODS_GM_BOUNDING_BOX = "-2.36,53.43,-2.10,53.61"
