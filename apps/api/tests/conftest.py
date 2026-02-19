import pytest

from main import app
from routers import rate_limit


@pytest.fixture(autouse=True)
def reset_local_rate_limit_counters():
    """Keep in-memory rate-limit state isolated between tests."""
    previous = getattr(app.state, "disable_rate_limits", False)
    app.state.disable_rate_limits = True
    rate_limit._local_counters.clear()
    yield
    rate_limit._local_counters.clear()
    app.state.disable_rate_limits = previous
