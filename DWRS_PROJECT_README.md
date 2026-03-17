# DWRS — Domestic Worker Registration & Verification System
## Complete Project Package

---

## Contents

```
dwrs-backend/       Python FastAPI backend (microservices)
dwrs-frontend/      React TypeScript PWA frontend
```

## Quick Start

### Backend
```bash
cd dwrs-backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # Edit with your values
docker-compose -f infra/docker-compose.yml up -d
alembic upgrade head
python run_dev.py
```

### Frontend
```bash
cd dwrs-frontend
npm install
npm run dev
```

## API Documentation (after running)
- Auth:         http://localhost:8001/docs
- Registration: http://localhost:8002/docs
- Verification: http://localhost:8003/docs
- Risk Scoring: http://localhost:8004/docs
- Audit:        http://localhost:8005/docs

## Key Files
- `dwrs-backend/README.md`        — Full backend documentation
- `dwrs-backend/requirements.txt` — All Python dependencies
- `dwrs-backend/.env.example`     — Environment variables template
- `dwrs-backend/infra/schema.sql` — Full PostgreSQL schema
- `dwrs-backend/infra/docker-compose.yml` — Local dev infrastructure
- `dwrs-backend/infra/terraform/main.tf`  — AWS production infrastructure
- `dwrs-backend/infra/ci-cd-pipeline.yml` — GitHub Actions CI/CD
- `dwrs-frontend/README.md`       — Frontend documentation
- `dwrs-frontend/package.json`    — Node.js dependencies

## Architecture Summary
- 5 microservices: Auth, Registration, Verification, Risk Scoring, Audit
- PostgreSQL (RDS Multi-AZ) with AES-256 PII encryption
- Redis (ElastiCache) for sessions and OTP
- Kafka (MSK) event bus for async inter-service communication
- AWS Rekognition for face matching
- UIDAI Aadhaar e-KYC integration
- Hash-chained, append-only audit records
- Explainable risk scoring: rules (70%) + ML anomaly detection (30%)
- Offline-first PWA with 72h sync window
- ECS Fargate deployment with blue/green CI/CD
