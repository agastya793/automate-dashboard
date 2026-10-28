"""
Authentication, Authorization, Sessions, Workspaces & RBAC Tests (Milestone 5)

Covers all 22 required test scenarios:
Authentication:
1. Successful account registration
2. Duplicate email handling
3. Correct password login
4. Incorrect password rejection
5. Argon2id password hashes stored instead of plaintext
6. Successful session creation
7. Session expiration
8. Session revocation and logout
9. Invalid or tampered session tokens
10. Production startup rejects single-user bypass
11. Authentication rate limiting
12. CSRF token validation

Authorization:
13. An unauthenticated client cannot access a protected endpoint
14. User A cannot access User B's upload
15. User A cannot query User B's Parquet dataset
16. User A cannot reopen User B's dashboard
17. A viewer cannot alter or delete a dashboard
18. A viewer cannot delete a dataset
19. An editor cannot change workspace membership or promote themselves
20. A workspace admin cannot access unrelated workspace data
21. Unauthorized requests cannot delete storage objects
22. Unassigned legacy records remain inaccessible to non-admins
"""

import datetime as dt
import hashlib
import io
import json
import os
import secrets
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    AuthenticatedUser,
    get_current_user,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.db.models import Base, Dashboard, Dataset, Session, Upload, User, Workspace, WorkspaceMember
from app.db.repositories import (
    DashboardRepository,
    DatasetRepository,
    SessionRepository,
    UploadRepository,
    UserRepository,
    WorkspaceRepository,
)
from app.db.session import get_db, set_session_factory
from app.main import app, startup_security_check
from app.rate_limiter import rate_limiter
from app.storage import get_storage_backend


@pytest.fixture
def auth_test_env():
    """Provides an isolated database environment for auth testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    set_session_factory(TestingSession)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # Clear the global get_current_user override so real authentication runs
    app.dependency_overrides.pop(get_current_user, None)
    rate_limiter.reset()

    yield TestingSession

    app.dependency_overrides.pop(get_db, None)
    set_session_factory(None)
    rate_limiter.reset()


client = TestClient(app)


# ---------------------------------------------------------------------------
# 1-12: Authentication Tests
# ---------------------------------------------------------------------------

def test_public_health_endpoint_without_auth():
    """Health check must remain public."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_successful_account_registration(auth_test_env):
    """1. Successful account registration with default workspace."""
    payload = {
        "email": "analyst@manufacturing.com",
        "password": "SecurePassword123!",
        "display_name": "Quality Analyst",
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["user"]["email"] == "analyst@manufacturing.com"
    assert data["user"]["display_name"] == "Quality Analyst"
    assert data["workspace"]["name"] == "Quality Analyst Workspace"
    assert data["workspace"]["role"] == "admin"
    assert "csrf_token" in data

    # Verify cookies set
    assert "session_token" in res.cookies
    assert "csrf_token" in res.cookies


def test_duplicate_email_registration_rejected(auth_test_env):
    """2. Duplicate email handling without sensitive leakage."""
    payload = {
        "email": "duplicate@manufacturing.com",
        "password": "Password123!",
        "display_name": "User 1",
    }
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    # Attempt to register again with same email
    res2 = client.post("/api/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"]


def test_argon2id_password_hashes_stored(auth_test_env):
    """5. Argon2id password hashes stored instead of plaintext."""
    session_factory = auth_test_env
    email = "argon_user@manufacturing.com"
    plain_pwd = "MySecretPassword123!"

    res = client.post(
        "/api/auth/register",
        json={"email": email, "password": plain_pwd, "display_name": "Argon User"},
    )
    assert res.status_code == 201

    db = session_factory()
    try:
        user_repo = UserRepository(db)
        u = user_repo.get_by_email(email)
        assert u is not None
        assert u.password_hash is not None
        assert plain_pwd not in u.password_hash
        assert u.password_hash.startswith("$argon2id$")
        assert verify_password(plain_pwd, u.password_hash) is True
        assert verify_password("WrongPassword!", u.password_hash) is False
    finally:
        db.close()


def test_correct_password_login(auth_test_env):
    """3. Correct password login verifies hash and rotates session."""
    client.post(
        "/api/auth/register",
        json={"email": "login_user@example.com", "password": "ValidPassword123!"},
    )

    login_res = client.post(
        "/api/auth/login",
        json={"email": "login_user@example.com", "password": "ValidPassword123!"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["user"]["email"] == "login_user@example.com"
    assert "session_token" in login_res.cookies
    assert "csrf_token" in login_res.cookies


def test_incorrect_password_rejected(auth_test_env):
    """4. Incorrect password rejection with generic error."""
    client.post(
        "/api/auth/register",
        json={"email": "good_user@example.com", "password": "CorrectPassword123!"},
    )

    res = client.post(
        "/api/auth/login",
        json={"email": "good_user@example.com", "password": "WrongPassword999!"},
    )
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]


def test_successful_session_creation_and_hashing(auth_test_env):
    """6. Session token created with SHA-256 hash stored in DB."""
    session_factory = auth_test_env
    res = client.post(
        "/api/auth/register",
        json={"email": "session_check@example.com", "password": "Password123!"},
    )
    raw_token = res.cookies.get("session_token")
    assert raw_token is not None

    db = session_factory()
    try:
        token_hash = hash_session_token(raw_token)
        s_repo = SessionRepository(db)
        session = s_repo.get_valid_session(token_hash)
        assert session is not None
        assert session.token_hash == token_hash
        assert session.token_hash != raw_token
        assert session.revoked_at is None
    finally:
        db.close()


def test_session_expiration(auth_test_env):
    """7. Session expiration rejects access."""
    session_factory = auth_test_env
    res = client.post(
        "/api/auth/register",
        json={"email": "expire_test@example.com", "password": "Password123!"},
    )
    raw_token = res.cookies.get("session_token")

    # Manually backdate session expiration in DB
    db = session_factory()
    try:
        token_hash = hash_session_token(raw_token)
        s_repo = SessionRepository(db)
        stmt_session = s_repo.get_valid_session(token_hash)
        stmt_session.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    # Attempt access with expired session
    get_me = client.get("/api/auth/me", cookies={"session_token": raw_token})
    assert get_me.status_code == 401
    assert "Invalid, expired, or revoked" in get_me.json()["detail"]


def test_session_revocation_and_logout(auth_test_env):
    """8. Session revocation and logout invalidates session."""
    reg = client.post(
        "/api/auth/register",
        json={"email": "logout_test@example.com", "password": "Password123!"},
    )
    raw_token = reg.cookies.get("session_token")

    # Logout
    logout_res = client.post("/api/auth/logout", cookies={"session_token": raw_token})
    assert logout_res.status_code == 200

    # Cookie cleared and subsequent request fails
    me_res = client.get("/api/auth/me", cookies={"session_token": raw_token})
    assert me_res.status_code == 401


def test_invalid_or_tampered_session_token(auth_test_env):
    """9. Invalid or tampered session token rejected."""
    tampered_token = secrets.token_urlsafe(32)
    res = client.get("/api/auth/me", cookies={"session_token": tampered_token})
    assert res.status_code == 401
    assert "Invalid, expired, or revoked" in res.json()["detail"]


@pytest.mark.asyncio
async def test_production_startup_rejects_single_user_bypass():
    """10. Production startup guard rejects SINGLE_USER_DEV_MODE=true."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("APP_ENV", "production")
        mp.setenv("SINGLE_USER_DEV_MODE", "true")
        with pytest.raises(RuntimeError) as exc_info:
            await startup_security_check()
        assert "CRITICAL SECURITY CONFIGURATION ERROR" in str(exc_info.value)


def test_authentication_rate_limiting(auth_test_env):
    """11. Authentication rate limiting blocks brute-force attempts."""
    rate_limiter.reset()
    for _ in range(10):
        client.post(
            "/api/auth/login",
            json={"email": "brute@example.com", "password": "WrongPassword!"},
        )

    # 11th attempt should trigger 429
    blocked = client.post(
        "/api/auth/login",
        json={"email": "brute@example.com", "password": "WrongPassword!"},
    )
    assert blocked.status_code == 429
    assert "Too many login attempts" in blocked.json()["detail"]


def test_csrf_token_validation(auth_test_env):
    """12. CSRF validation requires matching header for cookie-authenticated requests."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("BYPASS_CSRF_FOR_TESTS", "false")
        reg = client.post(
            "/api/auth/register",
            json={"email": "csrf_test@example.com", "password": "Password123!"},
        )
        assert reg.status_code == 201
        session_token = reg.cookies.get("session_token")
        csrf_token = reg.cookies.get("csrf_token")

        # 1. State-changing request with session cookie but missing X-CSRF-Token -> 403
        bad_req = client.post(
            "/api/workspaces",
            json={"name": "New WS"},
            cookies={"session_token": session_token, "csrf_token": csrf_token},
        )
        assert bad_req.status_code == 403
        assert "Missing CSRF token header" in bad_req.json()["detail"]

        # 2. State-changing request with mismatched CSRF token -> 403
        tampered_req = client.post(
            "/api/workspaces",
            json={"name": "New WS"},
            cookies={"session_token": session_token, "csrf_token": csrf_token},
            headers={"X-CSRF-Token": "tampered_token_123"},
        )
        assert tampered_req.status_code == 403
        assert "Invalid or tampered CSRF token" in tampered_req.json()["detail"]

        # 3. State-changing request with matching CSRF token -> succeeds
        good_req = client.post(
            "/api/workspaces",
            json={"name": "New WS"},
            cookies={"session_token": session_token, "csrf_token": csrf_token},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert good_req.status_code == 201


# ---------------------------------------------------------------------------
# 13-22: Authorization Tests
# ---------------------------------------------------------------------------

def test_unauthenticated_client_cannot_access_protected_endpoints(auth_test_env):
    """13. Unauthenticated client cannot access protected endpoints."""
    csv_bytes = b"col1,col2\n1,2\n"
    files = {"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")}

    res1 = client.post("/api/datasets/preview", files=files)
    assert res1.status_code == 401

    res2 = client.get("/api/uploads")
    assert res2.status_code == 401

    res3 = client.get("/api/dashboards")
    assert res3.status_code == 401


def test_cross_user_upload_access_denied(auth_test_env):
    """14. User A cannot access User B's upload."""
    session_factory = auth_test_env

    # Register User A
    res_a = client.post("/api/auth/register", json={"email": "user_a@test.com", "password": "Password123!"})
    token_a = res_a.cookies.get("session_token")
    user_a_id = res_a.json()["user"]["id"]
    ws_a_id = res_a.json()["workspace"]["id"]

    # Register User B
    res_b = client.post("/api/auth/register", json={"email": "user_b@test.com", "password": "Password123!"})
    token_b = res_b.cookies.get("session_token")

    # Create an upload belonging to User A / Workspace A
    db = session_factory()
    try:
        up_repo = UploadRepository(db)
        upload_a = up_repo.create(
            original_filename="UserA_Data.xlsx",
            sanitized_filename="usera_data.xlsx",
            storage_key="uploads/usera/file.xlsx",
            file_size_bytes=100,
            file_type="xlsx",
            sha256_hash="hash_a",
            user_id=user_a_id,
            workspace_id=ws_a_id,
        )
        upload_a_id = str(upload_a.id)
    finally:
        db.close()

    # User B attempts to access User A's upload
    res = client.get(f"/api/uploads/{upload_a_id}", cookies={"session_token": token_b})
    assert res.status_code in (403, 404)


def test_cross_user_parquet_query_denied(auth_test_env):
    """15. User A cannot query User B's Parquet dataset."""
    session_factory = auth_test_env

    res_a = client.post("/api/auth/register", json={"email": "data_owner@test.com", "password": "Password123!"})
    ws_a_id = res_a.json()["workspace"]["id"]
    user_a_id = res_a.json()["user"]["id"]

    res_b = client.post("/api/auth/register", json={"email": "attacker@test.com", "password": "Password123!"})
    token_b = res_b.cookies.get("session_token")

    # Create dataset belonging to Workspace A
    db = session_factory()
    try:
        up_repo = UploadRepository(db)
        ds_repo = DatasetRepository(db)
        up = up_repo.create(
            original_filename="OwnerData.xlsx",
            sanitized_filename="ownerdata.xlsx",
            storage_key="uploads/owner/file.xlsx",
            file_size_bytes=50,
            file_type="xlsx",
            sha256_hash="hash_owner",
            user_id=user_a_id,
            workspace_id=ws_a_id,
        )
        ds = ds_repo.create(
            upload_id=up.id,
            sheet_name="Sheet1",
            cell_range="A1:C10",
            kind="tidy",
            column_metadata=[{"name": "col1", "role": "text"}],
            parquet_storage_key="datasets/secret.parquet",
        )
        ds_id = str(ds.id)
    finally:
        db.close()

    # User B queries dataset belonging to Workspace A
    query_payload = {"dataset_id": ds_id, "dimensions": ["col1"]}
    res = client.post("/api/query", json=query_payload, cookies={"session_token": token_b})
    assert res.status_code in (403, 404)


def test_cross_user_dashboard_reopen_denied(auth_test_env):
    """16. User A cannot reopen User B's dashboard."""
    session_factory = auth_test_env

    res_a = client.post("/api/auth/register", json={"email": "dash_owner@test.com", "password": "Password123!"})
    user_a_id = res_a.json()["user"]["id"]
    ws_a_id = res_a.json()["workspace"]["id"]

    res_b = client.post("/api/auth/register", json={"email": "dash_intruder@test.com", "password": "Password123!"})
    token_b = res_b.cookies.get("session_token")

    db = session_factory()
    try:
        up_repo = UploadRepository(db)
        dash_repo = DashboardRepository(db)
        up = up_repo.create(
            original_filename="f.xlsx", sanitized_filename="f.xlsx",
            storage_key="uploads/k", file_size_bytes=10, file_type="xlsx",
            sha256_hash="h", user_id=user_a_id, workspace_id=ws_a_id,
        )
        d = dash_repo.create(
            upload_id=up.id,
            title="Private Dashboard",
            spec={"widgets": []},
            user_id=user_a_id,
            workspace_id=ws_a_id,
        )
        d_id = str(d.id)
    finally:
        db.close()

    # User B attempts to access dashboard
    res = client.get(f"/api/dashboards/{d_id}", cookies={"session_token": token_b})
    assert res.status_code in (403, 404)


def test_viewer_cannot_alter_or_delete_dashboard(auth_test_env):
    """17. A viewer cannot alter or delete a dashboard."""
    session_factory = auth_test_env

    # 1. Admin creates workspace
    res_admin = client.post("/api/auth/register", json={"email": "ws_admin@test.com", "password": "Password123!"})
    ws_id = res_admin.json()["workspace"]["id"]
    admin_token = res_admin.cookies.get("session_token")

    # 2. Add Viewer user to same workspace
    res_viewer = client.post("/api/auth/register", json={"email": "viewer_user@test.com", "password": "Password123!"})
    viewer_id = res_viewer.json()["user"]["id"]
    viewer_token = res_viewer.cookies.get("session_token")

    db = session_factory()
    try:
        ws_repo = WorkspaceRepository(db)
        ws_repo.add_member(ws_id, viewer_id, role="viewer")
        # Create dashboard in workspace
        up_repo = UploadRepository(db)
        dash_repo = DashboardRepository(db)
        up = up_repo.create(
            original_filename="w.xlsx", sanitized_filename="w.xlsx",
            storage_key="uploads/w", file_size_bytes=10, file_type="xlsx",
            sha256_hash="hw", workspace_id=ws_id,
        )
        d = dash_repo.create(
            upload_id=up.id, title="Test Dash", spec={"widgets": []}, workspace_id=ws_id,
        )
        d_id = str(d.id)
        up_id = str(up.id)
    finally:
        db.close()

    # Viewer attempts to save/alter a dashboard -> 403
    save_res = client.post(
        "/api/dashboards",
        json={"upload_id": up_id, "title": "Tampered", "spec": {}},
        cookies={"session_token": viewer_token},
        headers={"X-Workspace-ID": ws_id},
    )
    assert save_res.status_code == 403
    assert "Viewers cannot" in save_res.json()["detail"]

    # Viewer attempts to delete dashboard -> 403
    del_res = client.delete(
        f"/api/dashboards/{d_id}",
        cookies={"session_token": viewer_token},
        headers={"X-Workspace-ID": ws_id},
    )
    assert del_res.status_code == 403


def test_viewer_cannot_delete_dataset(auth_test_env):
    """18. A viewer cannot delete a dataset."""
    session_factory = auth_test_env

    res_admin = client.post("/api/auth/register", json={"email": "owner_ds@test.com", "password": "Password123!"})
    ws_id = res_admin.json()["workspace"]["id"]

    res_viewer = client.post("/api/auth/register", json={"email": "viewer_ds@test.com", "password": "Password123!"})
    viewer_id = res_viewer.json()["user"]["id"]
    viewer_token = res_viewer.cookies.get("session_token")

    db = session_factory()
    try:
        ws_repo = WorkspaceRepository(db)
        ws_repo.add_member(ws_id, viewer_id, role="viewer")
        up_repo = UploadRepository(db)
        ds_repo = DatasetRepository(db)
        up = up_repo.create(
            original_filename="d.xlsx", sanitized_filename="d.xlsx",
            storage_key="uploads/d", file_size_bytes=10, file_type="xlsx",
            sha256_hash="hd", workspace_id=ws_id,
        )
        ds = ds_repo.create(
            upload_id=up.id, sheet_name="S1", cell_range="A1:B2", kind="tidy", column_metadata=[],
        )
        ds_id = str(ds.id)
    finally:
        db.close()

    # Viewer attempts to delete dataset -> 403
    del_res = client.delete(
        f"/api/datasets/{ds_id}",
        cookies={"session_token": viewer_token},
        headers={"X-Workspace-ID": ws_id},
    )
    assert del_res.status_code == 403


def test_editor_cannot_change_workspace_membership_or_elevate_role(auth_test_env):
    """19. An editor cannot manage membership or promote themselves to admin."""
    session_factory = auth_test_env

    res_admin = client.post("/api/auth/register", json={"email": "admin_rbac@test.com", "password": "Password123!"})
    ws_id = res_admin.json()["workspace"]["id"]

    res_editor = client.post("/api/auth/register", json={"email": "editor_rbac@test.com", "password": "Password123!"})
    editor_id = res_editor.json()["user"]["id"]
    editor_token = res_editor.cookies.get("session_token")

    db = session_factory()
    try:
        ws_repo = WorkspaceRepository(db)
        ws_repo.add_member(ws_id, editor_id, role="editor")
    finally:
        db.close()

    # Editor attempts to promote themselves to admin -> 403
    patch_res = client.patch(
        f"/api/workspaces/{ws_id}/members/{editor_id}",
        json={"role": "admin"},
        cookies={"session_token": editor_token},
        headers={"X-Workspace-ID": ws_id},
    )
    assert patch_res.status_code == 403

    # Editor attempts to add a new member -> 403
    add_res = client.post(
        f"/api/workspaces/{ws_id}/members",
        json={"email": "someone@test.com", "role": "viewer"},
        cookies={"session_token": editor_token},
        headers={"X-Workspace-ID": ws_id},
    )
    assert add_res.status_code == 403


def test_workspace_isolation_between_admins(auth_test_env):
    """20. A workspace admin cannot access unrelated workspace data."""
    session_factory = auth_test_env

    res_admin1 = client.post("/api/auth/register", json={"email": "admin_one@test.com", "password": "Password123!"})
    ws1_id = res_admin1.json()["workspace"]["id"]

    res_admin2 = client.post("/api/auth/register", json={"email": "admin_two@test.com", "password": "Password123!"})
    token_admin2 = res_admin2.cookies.get("session_token")

    # Admin 2 attempts to list members of Workspace 1
    res = client.get(f"/api/workspaces/{ws1_id}/members", cookies={"session_token": token_admin2})
    assert res.status_code in (403, 404)


def test_unauthorized_storage_deletion_rejected(auth_test_env):
    """21. Unauthorized requests cannot delete storage objects."""
    session_factory = auth_test_env

    res_owner = client.post("/api/auth/register", json={"email": "storage_owner@test.com", "password": "Password123!"})
    ws_owner_id = res_owner.json()["workspace"]["id"]

    res_intruder = client.post("/api/auth/register", json={"email": "storage_intruder@test.com", "password": "Password123!"})
    token_intruder = res_intruder.cookies.get("session_token")

    db = session_factory()
    try:
        up_repo = UploadRepository(db)
        up = up_repo.create(
            original_filename="secret.xlsx", sanitized_filename="secret.xlsx",
            storage_key="uploads/secret_storage.xlsx", file_size_bytes=10, file_type="xlsx",
            sha256_hash="hash_sec", workspace_id=ws_owner_id,
        )
        up_id = str(up.id)
    finally:
        db.close()

    # Intruder attempts to delete upload -> 403/404
    del_res = client.delete(f"/api/uploads/{up_id}", cookies={"session_token": token_intruder})
    assert del_res.status_code in (403, 404)


def test_unassigned_legacy_records_inaccessible_to_non_admins(auth_test_env):
    """22. Unassigned legacy records remain inaccessible to ordinary users."""
    session_factory = auth_test_env

    res_user = client.post("/api/auth/register", json={"email": "normal_user@test.com", "password": "Password123!"})
    token_user = res_user.cookies.get("session_token")

    db = session_factory()
    try:
        up_repo = UploadRepository(db)
        # Create unassigned historical record (workspace_id=None, user_id=None)
        legacy_up = up_repo.create(
            original_filename="Legacy_2020.xlsx", sanitized_filename="legacy_2020.xlsx",
            storage_key="uploads/legacy.xlsx", file_size_bytes=100, file_type="xlsx",
            sha256_hash="legacy_hash", user_id=None, workspace_id=None,
        )
        legacy_id = str(legacy_up.id)
    finally:
        db.close()

    # Ordinary user attempts to access unassigned legacy record
    res = client.get(f"/api/uploads/{legacy_id}", cookies={"session_token": token_user})
    assert res.status_code == 404
    assert "legacy" in res.json()["detail"].lower() or "not found" in res.json()["detail"].lower()
