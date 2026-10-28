import urllib.request
import urllib.error
import http.cookiejar
import json
import uuid

API_BASE = "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def log_res(step_name, method, url, status, body):
    print(f"=== {step_name} ===")
    print(f"REQUEST: {method} {url}")
    print(f"STATUS: {status}")
    print(f"BODY: {body[:300]}")
    print()

# Step 1: CSRF
try:
    req = urllib.request.Request(f"{API_BASE}/api/auth/csrf")
    with opener.open(req) as res:
        csrf_data = json.loads(res.read().decode())
        csrf_token = csrf_data.get("csrf_token")
        log_res("1. CSRF Token", "GET", f"{API_BASE}/api/auth/csrf", res.status, json.dumps(csrf_data))
except Exception as e:
    print("Step 1 failed:", e)
    csrf_token = None

# Step 2: Auth Me (before login)
try:
    req = urllib.request.Request(f"{API_BASE}/api/auth/me")
    with opener.open(req) as res:
        log_res("2. Auth Me (unauthenticated)", "GET", f"{API_BASE}/api/auth/me", res.status, res.read().decode())
except urllib.error.HTTPError as e:
    log_res("2. Auth Me (unauthenticated)", "GET", f"{API_BASE}/api/auth/me", e.code, e.read().decode())

# Step 3: Register or Login a test user
login_payload = json.dumps({"email": "test_engineer@example.com", "password": "SecurePassword123!"}).encode()
headers = {"Content-Type": "application/json"}
if csrf_token:
    headers["X-CSRF-Token"] = csrf_token

try:
    req = urllib.request.Request(f"{API_BASE}/api/auth/register", data=login_payload, headers=headers, method="POST")
    with opener.open(req) as res:
        log_res("3. Register", "POST", f"{API_BASE}/api/auth/register", res.status, res.read().decode())
except urllib.error.HTTPError as e:
    err_body = e.read().decode()
    log_res("3. Register (already exists or error)", "POST", f"{API_BASE}/api/auth/register", e.code, err_body)
    # Try login instead
    try:
        req = urllib.request.Request(f"{API_BASE}/api/auth/login", data=login_payload, headers=headers, method="POST")
        with opener.open(req) as res:
            log_res("3b. Login", "POST", f"{API_BASE}/api/auth/login", res.status, res.read().decode())
    except urllib.error.HTTPError as e2:
        log_res("3b. Login failed", "POST", f"{API_BASE}/api/auth/login", e2.code, e2.read().decode())

# Step 4: Auth Me (authenticated)
try:
    req = urllib.request.Request(f"{API_BASE}/api/auth/me")
    with opener.open(req) as res:
        log_res("4. Auth Me (authenticated)", "GET", f"{API_BASE}/api/auth/me", res.status, res.read().decode())
except urllib.error.HTTPError as e:
    log_res("4. Auth Me (authenticated)", "GET", f"{API_BASE}/api/auth/me", e.code, e.read().decode())
