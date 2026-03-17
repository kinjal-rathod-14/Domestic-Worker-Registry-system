"""
Integration tests for the Registration Service.
Requires running PostgreSQL, Redis, and Kafka (use docker-compose).
Run: pytest tests/integration/ -v --integration
"""
import pytest
import httpx
import asyncio

BASE_URL = "http://localhost:8002"

# Test credentials (seeded in test DB)
OFFICER_CREDENTIALS = {
    "username": "test_officer",
    "password": "Test@1234",
    "totp_code": "000000",     # TOTP bypassed in test mode
    "device_fingerprint": "test-device-001",
    "geo_location": {"lat": 19.0760, "lng": 72.8777, "accuracy_meters": 10},
}

VALID_WORKER_PAYLOAD = {
    "full_name": "Sunita Devi",
    "aadhaar_number": "999988887777",
    "date_of_birth": "1990-03-15",
    "gender": "F",
    "photo_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "mobile_number": "9876543210",
    "address": {
        "house": "12",
        "street": "Main Road",
        "village": "Andheri",
        "district": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400053",
    },
    "registration_mode": "assisted_officer",
    "geo_location": {"lat": 19.1136, "lng": 72.8697, "accuracy_meters": 20},
    "consent_recorded": True,
}


@pytest.fixture(scope="module")
async def officer_token():
    """Obtain officer JWT token for test requests."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/auth/token",
            json=OFFICER_CREDENTIALS,
        )
        assert response.status_code == 200
        return response.json()["access_token"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_worker_success(officer_token):
    """Happy path: valid registration returns 201 with worker_id."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/registration/worker",
            json=VALID_WORKER_PAYLOAD,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
    assert response.status_code == 201
    data = response.json()
    assert "worker_id" in data
    assert "registration_number" in data
    assert data["registration_number"].startswith("DWRS-")
    assert data["risk_level"] in ["low", "medium", "high"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_worker_duplicate_rejected(officer_token):
    """Second registration with same Aadhaar must return 409."""
    async with httpx.AsyncClient() as client:
        # First registration
        r1 = await client.post(
            f"{BASE_URL}/registration/worker",
            json={**VALID_WORKER_PAYLOAD, "aadhaar_number": "111122223333"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r1.status_code == 201

        # Duplicate attempt
        r2 = await client.post(
            f"{BASE_URL}/registration/worker",
            json={**VALID_WORKER_PAYLOAD, "aadhaar_number": "111122223333"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
    assert r2.status_code == 409
    assert r2.json()["detail"]["error"] == "DUPLICATE_REGISTRATION"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_without_auth_returns_401():
    """Unauthenticated request must return 401."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/registration/worker",
            json=VALID_WORKER_PAYLOAD,
        )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_without_consent_returns_422(officer_token):
    """Registration without consent must return 422."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/registration/worker",
            json={**VALID_WORKER_PAYLOAD, "consent_recorded": False},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_register_invalid_aadhaar_returns_422(officer_token):
    """Invalid Aadhaar format must return 422."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/registration/worker",
            json={**VALID_WORKER_PAYLOAD, "aadhaar_number": "123"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_offline_sync_expires_stale_records(officer_token):
    """Offline records older than 72h must be rejected as 'expired'."""
    batch = {
        "batch_id": "test-batch-stale",
        "records": [
            {
                "local_id": "local-001",
                "worker_data": VALID_WORKER_PAYLOAD,
                "captured_at": "2020-01-01T10:00:00+00:00",   # Very stale
                "device_fingerprint": "test-device-001",
            }
        ],
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/registration/offline-sync",
            json=batch,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["status"] == "expired"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_health_check():
    """Health endpoint returns 200."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
