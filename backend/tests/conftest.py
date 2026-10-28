"""
Pytest global fixtures for backend tests.
Automatically provides an isolated in-memory test database and verified test user for functional tests.
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import AuthenticatedUser, get_current_user
from app.db.models import Base, User, Workspace, WorkspaceMember
from app.db.session import get_db, set_session_factory
from app.main import app

# Set test environment flags
os.environ["BYPASS_CSRF_FOR_TESTS"] = "true"
os.environ["SINGLE_USER_DEV_MODE"] = "false"
os.environ["APP_ENV"] = "development"


@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    Default autouse fixture that injects:
    1. An isolated in-memory SQLite database session factory.
    2. An authenticated test user with workspace admin role.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    set_session_factory(TestingSessionLocal)

    # Pre-seed default test user and workspace
    db = TestingSessionLocal()
    try:
        user_id = "00000000-0000-0000-0000-000000000001"
        ws_id = "00000000-0000-0000-0000-000000000001"
        import uuid
        u_uuid = uuid.UUID(user_id)
        w_uuid = uuid.UUID(ws_id)
        test_user = User(
            id=u_uuid,
            email="testuser@example.com",
            display_name="Test User",
            role="admin",
            status="active",
        )
        test_ws = Workspace(
            id=w_uuid,
            name="Test Workspace",
            created_by_id=u_uuid,
        )
        test_member = WorkspaceMember(
            workspace_id=w_uuid,
            user_id=u_uuid,
            role="admin",
        )
        db.add(test_user)
        db.add(test_ws)
        db.add(test_member)
        db.commit()
    finally:
        db.close()

    def override_get_current_user():
        return AuthenticatedUser(
            id="00000000-0000-0000-0000-000000000001",
            email="testuser@example.com",
            display_name="Test User",
            role="admin",
            workspace_id="00000000-0000-0000-0000-000000000001",
            workspace_role="admin",
        )

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)
    set_session_factory(None)
