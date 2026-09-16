"""Parser and stale-data tests; run with Home Assistant's pytest fixture set."""

from custom_components.greater_manchester_transport.live_buses import LiveBusCoordinator


def _page(wait: int, disrupted: bool = False) -> str:
    return (
        'prefix "data":{"departures":[{'
        '"service":{"mode":"BUS","name":"42","destination":"Manchester"},'
        f'"timings":{{"expectedDepartureTime":"2026-09-04T10:15:00+00:00","wait":{wait}}},'
        f'"isDisrupted":{str(disrupted).lower()}'
        '}]} suffix'
    )


def test_live_bus_parser_keeps_authoritative_upcoming_departure() -> None:
    departures = LiveBusCoordinator._parse_tf_gm_board(_page(5, disrupted=True))
    assert departures[0]["route"] == "42"
    assert departures[0]["in_minutes"] == 5
    assert departures[0]["is_disrupted"] is True


def test_live_bus_parser_discards_stale_negative_wait() -> None:
    assert LiveBusCoordinator._parse_tf_gm_board(_page(-2)) == []


def test_live_bus_parser_rejects_changed_or_partial_page() -> None:
    try:
        LiveBusCoordinator._parse_tf_gm_board("no board here")
    except ValueError as err:
        assert "live departure board" in str(err)
    else:
        raise AssertionError("A changed public page must not become fake departures")
