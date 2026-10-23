"""
Pytest global fixtures for backend tests.
Automatically provides a verified test user for existing functional tests.
"""

import pytest
from app.auth import AuthenticatedUser, get_current_user
from app.main import app


@pytest.fixture(autouse=True)
def mock_authenticated_user():
    """
    Default autouse fixture that injects an authenticated test user.
    Specific auth tests can clear or override this.
    """
    def override_get_current_user():
        return AuthenticatedUser(
            id="00000000-0000-0000-0000-000000000001",
            email="testuser@example.com",
            role="authenticated",
        )

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
