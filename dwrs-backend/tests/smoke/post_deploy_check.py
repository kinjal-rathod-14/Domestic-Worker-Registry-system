"""
Post-Deploy Smoke Tests
Run after every deployment to verify critical paths are operational.
Usage: python tests/smoke/post_deploy_check.py https://api.dwrs.gov.in
"""
import sys
import httpx
import asyncio


async def run_smoke_tests(base_url: str):
    print(f"Running smoke tests against: {base_url}")
    failures = []

    async with httpx.AsyncClient(timeout=10.0) as client:

        # Test 1: Auth service health
        try:
            r = await client.get(f"{base_url}:8001/health")
            assert r.status_code == 200
            print("  [PASS] Auth service health check")
        except Exception as e:
            failures.append(f"Auth health: {e}")
            print(f"  [FAIL] Auth service health: {e}")

        # Test 2: Registration service health
        try:
            r = await client.get(f"{base_url}:8002/health")
            assert r.status_code == 200
            print("  [PASS] Registration service health check")
        except Exception as e:
            failures.append(f"Registration health: {e}")
            print(f"  [FAIL] Registration service health: {e}")

        # Test 3: Verification service health
        try:
            r = await client.get(f"{base_url}:8003/health")
            assert r.status_code == 200
            print("  [PASS] Verification service health check")
        except Exception as e:
            failures.append(f"Verification health: {e}")
            print(f"  [FAIL] Verification service health: {e}")

        # Test 4: Auth endpoint rejects bad credentials
        try:
            r = await client.post(f"{base_url}:8001/auth/token", json={
                "username": "nonexistent_user",
                "password": "wrong_password",
                "device_fingerprint": "smoke-test-device",
            })
            assert r.status_code == 401
            print("  [PASS] Auth rejects invalid credentials")
        except Exception as e:
            failures.append(f"Auth rejection: {e}")
            print(f"  [FAIL] Auth rejection test: {e}")

        # Test 5: Registration requires auth
        try:
            r = await client.post(f"{base_url}:8002/registration/worker", json={})
            assert r.status_code == 403
            print("  [PASS] Registration requires authentication")
        except Exception as e:
            failures.append(f"Auth guard: {e}")
            print(f"  [FAIL] Registration auth guard: {e}")

    if failures:
        print(f"\n[FAILED] {len(failures)} smoke test(s) failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"\n[PASSED] All smoke tests passed.")
        sys.exit(0)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost"
    asyncio.run(run_smoke_tests(url))
