"""Selection/group persistence tests for Home Assistant's standard pytest suite."""

import pytest

from custom_components.greater_manchester_transport import StopSelectionStore


@pytest.mark.asyncio
async def test_existing_selection_migrates_to_ungrouped(hass) -> None:
    store = StopSelectionStore(hass, "test-entry")
    await store._store.async_save({"selected": ["1800TEST"]})
    selected, groups = await store.get_state()
    assert selected == ["1800TEST"]
    assert groups == {"Ungrouped": ["1800TEST"]}


@pytest.mark.asyncio
async def test_group_store_drops_unknown_selection_members(hass) -> None:
    store = StopSelectionStore(hass, "test-entry")
    await store.set_state(["1800HOME"], {"Home": ["1800HOME", "not-selected"]})
    selected, groups = await store.get_state()
    assert selected == ["1800HOME"]
    assert groups == {"Home": ["1800HOME"]}
