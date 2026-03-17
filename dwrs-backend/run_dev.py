"""
Development runner — starts all DWRS services concurrently.
Usage: python run_dev.py
"""
import subprocess
import sys
import os
import signal
from concurrent.futures import ThreadPoolExecutor

SERVICES = [
    {"name": "auth",          "port": 8001, "module": "services.auth.main:app"},
    {"name": "registration",  "port": 8002, "module": "services.registration.main:app"},
    {"name": "verification",  "port": 8003, "module": "services.verification.main:app"},
    {"name": "risk_scoring",  "port": 8004, "module": "services.risk_scoring.main:app"},
    {"name": "audit",         "port": 8005, "module": "services.audit.main:app"},
]

processes = []


def start_service(service):
    cmd = [
        sys.executable, "-m", "uvicorn",
        service["module"],
        "--host", "0.0.0.0",
        "--port", str(service["port"]),
        "--reload",
        "--log-level", "info",
    ]
    print(f"Starting {service['name']} on port {service['port']}...")
    proc = subprocess.Popen(cmd, env=os.environ.copy())
    processes.append(proc)
    return proc


def shutdown(sig, frame):
    print("\nShutting down all services...")
    for proc in processes:
        proc.terminate()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 50)
    print("DWRS Development Server")
    print("=" * 50)
    print()

    with ThreadPoolExecutor(max_workers=len(SERVICES)) as executor:
        futures = [executor.submit(start_service, svc) for svc in SERVICES]

    print()
    print("Services available at:")
    for svc in SERVICES:
        print(f"  {svc['name']:15} http://localhost:{svc['port']}/docs")
    print()
    print("Press Ctrl+C to stop all services")

    # Keep alive
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        shutdown(None, None)
