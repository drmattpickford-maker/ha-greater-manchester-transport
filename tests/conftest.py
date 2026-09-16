import pytest


@pytest.fixture(autouse=True)
def enable_custom_integrations_for_tests(enable_custom_integrations):
    yield
