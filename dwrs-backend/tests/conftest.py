"""
pytest configuration and shared fixtures for DWRS test suite.
"""
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as requiring running infrastructure"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow-running"
    )
