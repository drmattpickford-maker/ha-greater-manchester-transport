# Greater Manchester Transport

This is an early HACS-ready Home Assistant custom integration.  It adds a
sidebar map panel which lets an administrator select monitored bus stops and
Metrolink stations.  The selection is stored locally in Home Assistant, rather
than in an entity attribute or an external service.

## What it does

- Home Assistant config flow, with an optional BODS key.
- A responsive, authenticated, dependency-free OpenStreetMap panel under
  **GM Transport**.
- Searchable and refreshable official DfT NaPTAN catalogue for the whole
  Greater Manchester ATCO area, cached locally and refreshed weekly.
- Persistent monitored-stop selection, with an automatic sensor for each stop.
- Live Metrolink departures from TfGM's public stop board, refreshed every
  minute where that board is available.  Each live entry retains TfGM's
  expected time, displayed wait, status and last-update timestamp.
- Scheduled bus and Metrolink departures from TfGM's public GTFS timetable as
  a clear fallback. Each sensor exposes its next five services, route,
  destination and minutes away.
- Live bus departures from TfGM's public ATCO stop board wherever it is
  published, refreshed once a minute. An unavailable board falls back to the
  timetable without inventing an ETA.
- Live BODS SIRI-VM vehicle locations for added context, scoped to the
  selected-stop area. They are never misrepresented as arrival predictions.
- TfGM's per-service disruption flag is exposed alongside affected live
  departures.

The optional BODS key stays in Home Assistant's config-entry storage and is
never exposed to the map panel, entity state or diagnostics. It can be changed
or removed through **Settings → Devices & services → Greater Manchester
Transport → Configure**.

Good mixed-mode examples are **Altrincham Interchange**, **Bury Interchange**
and **Rochdale Interchange**: add the interchange bus stop and the nearby
Metrolink stop to see both services together.

## Coverage and live-data meaning

The stop picker covers the whole Greater Manchester NaPTAN catalogue. Every
selected bus stop and Metrolink station receives scheduled departures from the
TfGM GTFS feed.

- **Metrolink:** the integration tries TfGM's public live station board first;
  if that board is unavailable it falls back to the schedule.
- **Bus stops:** the integration tries TfGM's public ATCO stop board first;
  if it is unavailable, the departure list remains scheduled. BODS adds a
  separate vehicle-location signal, never an implied arrival prediction.

In short, the integration scales to all GM bus and tram stops, while always
making clear whether a displayed time is live or scheduled.

## Named groups and dashboard cards

Create groups such as **Home**, **Work** or **Favourite interchanges** from
the GM Transport picker, then add stops to the active group. Stops may appear
in more than one group. The bundled departures card can show a group in its
own Lovelace card:

```yaml
type: custom:gmp-transport-departures-card
title: Home departures
group: Home
```

Omit `group` to show every monitored stop. Each stop entity also exposes its
group names and any current TfGM service-disruption flags as attributes.

## Installation for development

Copy `custom_components/greater_manchester_transport` into the matching
directory in a Home Assistant configuration folder, restart Home Assistant,
then add **Greater Manchester Transport** under Settings → Devices & services.
The **GM Transport** sidebar panel appears once configured.

## Optional dashboard cards

The picker creates Home Assistant sensors as soon as a stop is monitored. Use
the bundled departures card when you want a compact, live-updating grouped
view, or a native **Entities** card when you prefer no custom resource. A
ready-made native example is in
[`examples/dashboard_card.yaml`](../../examples/dashboard_card.yaml).

Map tiles are © OpenStreetMap contributors and require the usual attribution
when this becomes a published integration.
