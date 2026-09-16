# Greater Manchester Transport

An independent Home Assistant custom integration for Greater Manchester bus
and Metrolink departures. Preview version **0.3.0**.

Choose stops on a map, monitor their sensors, and display departures on your
own dashboard. This project is not affiliated with TfGM or the Bee Network.
It is a standalone integration; no rotary telephone or Raspberry Pi is needed.

## Features

- Map picker starts at Home Assistant's home location when it is in Greater
  Manchester; otherwise it starts at central Manchester.
- Search the regional stop catalogue, select stops, and organise them into
  groups such as Home and Work. Each monitored stop gets a sensor.
- Tries TfGM public live boards for buses and trams. Uses the scheduled
  timetable when live predictions are unavailable.
- Optional BODS key adds vehicle-presence information. Vehicle presence is
  not an arrival prediction.
- Bundled dashboard card with Location and Soonest sorting and group filters.
- Options to change/remove the BODS key, English UI strings and diagnostics.

## Install manually

1. Download this repository using **Code → Download ZIP** and extract it.
2. Copy `custom_components/greater_manchester_transport` into your Home
   Assistant `/config/custom_components/` directory.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration**, and choose
   **Greater Manchester Transport**.
5. Leave the BODS key blank unless you want its optional vehicle context.
6. Open **GM Transport** in the sidebar as an administrator and add stops.

On first startup, allow time for the regional stop catalogue and timetable to
download. The bundled sample stops are not a saved selection.

## Install through HACS

This project is not yet listed in HACS's default catalogue. In HACS, add
`https://github.com/drmattpickford-maker/ha-greater-manchester-transport` as a
**custom repository**, type **Integration**, then download it and restart
Home Assistant. Continue with step 4 above. Minimum declared Home Assistant
version is 2025.1; this preview still needs wider compatibility testing.

## Dashboard card

No dashboard is created or changed automatically. The integration registers
its card JavaScript. Add a Manual card to a dashboard of your choice:

```yaml
type: custom:gmp-transport-departures-card
title: Local area departures
```

To show only a named group, add `group: Home` (using your exact group name).
After upgrading, fully reload the browser/mobile frontend if the old card is
cached. A native Entities card can also show the created sensors.

## Coverage and limitations

The catalogue covers Greater Manchester. Scheduled departures depend on a
matching stop and current service in TfGM's feed; no departures is possible.
Live boards are not guaranteed at every stop. TfGM page changes can interrupt
live parsing; the timetable remains the fallback. Previously exercised mixed
locations include Altrincham, Bury and Rochdale interchanges. These are useful
test examples, not a guarantee of live coverage today.

Disruption information is the flag attached to TfGM live services, not a
complete regional disruption bulletin. Cached data, outages, mobile rendering,
integration reloads and older HA versions need further field testing. After
changing/removing a BODS key, restart Home Assistant to apply it in this build.

## Privacy and data sources

No API key or household configuration is shipped. Stop selections and keys
stay in Home Assistant. BODS requests send the configured key to BODS over
HTTPS, using its required query parameter. Diagnostics redact the key, but
include selected stop IDs and group names: review those before sharing.

- [TfGM](https://tfgm.com/): public departure boards and regional GTFS data.
- [DfT NaPTAN](https://naptan.api.dft.gov.uk/): stop catalogue.
- [Bus Open Data Service](https://data.bus-data.dft.gov.uk/): optional vehicles.
- Map tiles © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).

Upstream data and map tiles remain subject to their providers' terms and
licences. The bee graphic is the project's own icon, not an official logo.

## Reporting problems

Use this repository's Issues page. Include HA version, integration version,
stop ID, bus/tram mode, and whether the display says live or scheduled. Never
include API keys or unreviewed diagnostic files.

## Development

Run `python -m compileall -q custom_components` and `node --check` on each
frontend JavaScript file for syntax validation. Tests in `tests/` additionally
require a compatible Home Assistant pytest environment and
`pytest-homeassistant-custom-component`; plain Python alone is insufficient.
