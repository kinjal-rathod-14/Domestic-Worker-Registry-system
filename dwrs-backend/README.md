# Domestic Worker Registration & Verification System (DWRS)
## Government-Grade Secure Registration Platform

---

## Overview

DWRS is a production-ready backend system designed for government use to register, verify, and monitor domestic workers. It prevents identity fraud, duplicate registrations, and officer corruption through layered verification, explainable risk scoring, tamper-proof audit logs, and anti-corruption enforcement mechanisms.

---

## Architecture

```
Clients (Web / Mobile / Kiosk / Admin Portal)
        │
        ▼
API Gateway (Kong / AWS API GW)  ←──→  Auth Service (JWT + MFA + RBAC)
        │
        ├── Registration Service    (self / assisted / offline-sync)
        ├── Verification Service    (ID / face / geo / duplicate)
        ├── Risk Scoring Engine     (rules 70% + ML anomaly 30%)
        └── Audit Service           (hash-chained, append-only)
                │
        Event Bus (Kafka / SQS+SNS)
                │
        ┌───────┼───────────┐
        ▼       ▼           ▼
  PostgreSQL  Redis    Elasticsearch
  (RDS)     (Cache)   (Audit search)
                │
        External APIs
        (UIDAI / Rekognition / Twilio / Maps)
```

---

## Tech Stack

| Layer         | Technology                                   |
|---------------|----------------------------------------------|
| Runtime       | Python 3.11                                  |
| Framework     | FastAPI (async)                              |
| Database      | PostgreSQL 15 + pgvector + pgcrypto          |
| Cache         | Redis 7 (ElastiCache)                        |
| Search/Audit  | Elasticsearch / AWS OpenSearch               |
| Event Bus     | Apache Kafka (AWS MSK) or AWS SQS+SNS        |
| Auth          | JWT (RS256) + TOTP (pyotp) + RBAC            |
| Face Match    | AWS Rekognition                              |
| ID Validation | UIDAI Aadhaar e-KYC API                      |
| Storage       | AWS S3 (photos, documents)                   |
| Container     | Docker + AWS ECS Fargate                     |
| IaC           | Terraform                                    |
| CI/CD         | GitHub Actions + AWS CodePipeline            |

---

## Project Structure

```
dwrs-backend/
├── services/
│   ├── auth/                   # JWT, MFA, session management
│   │   ├── main.py
│   │   ├── routes/auth.py
│   │   ├── models/user.py
│   │   ├── core/jwt.py
│   │   ├── core/rbac.py
│   │   └── middleware/rate_limit.py
│   ├── registration/           # Worker registration (all modes)
│   │   ├── main.py
│   │   ├── routes/worker.py
│   │   ├── routes/assisted.py
│   │   ├── routes/offline_sync.py
│   │   ├── models/worker.py
│   │   └── services/dedup.py
│   ├── verification/           # ID / face / geo verification
│   │   ├── routes/verify.py
│   │   └── services/
│   │       ├── face_match.py
│   │       ├── geo_validate.py
│   │       └── id_validator.py
│   ├── risk_scoring/           # Risk scoring engine
│   │   ├── engine.py
│   │   ├── rules/officer_rules.py
│   │   ├── rules/worker_rules.py
│   │   └── models/risk_score.py
│   └── audit/                  # Tamper-proof audit + officer monitoring
│       ├── routes/audit.py
│       └── services/
│           ├── hash_chain.py
│           └── alert.py
├── shared/                     # Shared utilities across services
│   ├── db/postgres.py
│   ├── db/redis_client.py
│   ├── events/kafka_producer.py
│   ├── middleware/audit_log.py
│   ├── middleware/auth_middleware.py
│   └── utils/
│       ├── encryption.py
│       └── validators.py
├── infra/
│   ├── docker-compose.yml      # Local development
│   ├── k8s/                    # Kubernetes manifests (optional)
│   └── terraform/              # AWS infrastructure as code
├── tests/
│   ├── unit/                   # Unit tests per service
│   ├── integration/            # API integration tests
│   └── smoke/                  # Post-deploy smoke tests
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Production container
└── README.md
```

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- AWS CLI configured (for S3/Rekognition in dev mode, or use mocks)

### 1. Clone & setup environment

```bash
git clone https://github.com/your-org/dwrs-backend.git
cd dwrs-backend
cp .env.example .env
# Edit .env with your values
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start infrastructure (Postgres, Redis, Kafka)

```bash
docker-compose -f infra/docker-compose.yml up -d
```

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start services

```bash
# Start all services (each runs on a different port)
uvicorn services.auth.main:app --port 8001 --reload &
uvicorn services.registration.main:app --port 8002 --reload &
uvicorn services.verification.main:app --port 8003 --reload &
uvicorn services.risk_scoring.main:app --port 8004 --reload &
uvicorn services.audit.main:app --port 8005 --reload
```

Or use the combined dev server:

```bash
python run_dev.py
```

### 6. API Documentation

Once running, visit:
- Auth Service: http://localhost:8001/docs
- Registration: http://localhost:8002/docs
- Verification: http://localhost:8003/docs
- Risk Scoring: http://localhost:8004/docs
- Audit: http://localhost:8005/docs

---

## Environment Variables

See `.env.example` for full list. Key variables:

| Variable                    | Description                              |
|-----------------------------|------------------------------------------|
| `DATABASE_URL`              | PostgreSQL connection string             |
| `REDIS_URL`                 | Redis connection string                  |
| `JWT_PRIVATE_KEY`           | RS256 private key (PEM format)           |
| `JWT_PUBLIC_KEY`            | RS256 public key (PEM format)            |
| `ENCRYPTION_KEY`            | AES-256 key for PII field encryption     |
| `AADHAAR_SALT`              | Salt for Aadhaar hashing                 |
| `UIDAI_AUA_CODE`            | UIDAI AUA code for Aadhaar auth          |
| `UIDAI_ASA_CODE`            | UIDAI ASA code                           |
| `AWS_REGION`                | AWS region (ap-south-1)                  |
| `S3_BUCKET_PHOTOS`          | S3 bucket for worker photos              |
| `REKOGNITION_COLLECTION_ID` | AWS Rekognition face collection ID       |
| `KAFKA_BOOTSTRAP_SERVERS`   | Kafka broker addresses                   |
| `TWILIO_ACCOUNT_SID`        | Twilio SID for SMS/OTP                   |
| `TWILIO_AUTH_TOKEN`         | Twilio auth token                        |

---

## Role-Based Access Control

| Role            | Key Permissions                                              |
|-----------------|--------------------------------------------------------------|
| `worker`        | Self-register, view own record                               |
| `employer`      | Assisted register, view assigned workers                     |
| `field_officer` | Assisted register (own district only), conduct verification  |
| `supervisor`    | All officer actions + override with reason + view district   |
| `admin`         | Manage officers, configure thresholds, view reports          |
| `auditor`       | Read-only access to all audit records                        |

---

## Risk Scoring

Risk scores are computed at registration time and recalculated nightly.

| Score Range | Level  | Action                              |
|-------------|--------|-------------------------------------|
| 0 – 39      | Low    | Auto-approve                        |
| 40 – 59     | Medium | Route to supervisor for review      |
| 60 – 100    | High   | Block + alert + generate dossier    |

**Rules contributing to score (R01–R07):**
- R01: Officer daily/burst volume
- R02: Geographic mismatch
- R03: ID name mismatch score
- R04: No contact information
- R05: Offline sync delay > 72h
- R06: Low officer trust score
- R07: Device used for multiple registrations

---

## Anti-Corruption Mechanisms

1. **Dual verification**: Registering officer ≠ verifying officer (enforced at DB constraint level)
2. **Officer trust score**: Recomputed every 6h; drops based on anomaly flags, failed verifications, geo variance
3. **Hash-chained audit logs**: Any tamper attempt breaks the chain; verified nightly by cron
4. **Random audits**: 10% of all registrations + 100% of high-risk + all from flagged officers
5. **Geo-scoping**: Field officers can only register workers in their assigned district

---

## Testing

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires running infrastructure)
pytest tests/integration/ -v

# Coverage report
pytest tests/ --cov=services --cov-report=html --cov-fail-under=85

# Security scan
bandit -r services/ -ll

# Dependency vulnerability check
safety check
```

---

## Deployment (AWS)

See `infra/terraform/` for full IaC. Summary:

- **Compute**: ECS Fargate (auto-scaling, no server management)
- **Database**: RDS PostgreSQL Multi-AZ, encrypted at rest
- **Cache**: ElastiCache Redis
- **Search**: Amazon OpenSearch Service
- **Storage**: S3 with server-side encryption
- **Networking**: VPC with public/private subnets, NAT gateway
- **Security**: WAF, Shield Standard, KMS, CloudTrail, Secrets Manager
- **CI/CD**: GitHub Actions → ECR → ECS Blue/Green deployment

```bash
cd infra/terraform
terraform init
terraform plan -var-file="prod.tfvars"
terraform apply -var-file="prod.tfvars"
```

---

## Security Considerations

- All PII fields (name, Aadhaar, DOB) encrypted at rest using pgcrypto AES-256
- Aadhaar stored only as salted SHA-256 hash for deduplication
- JWT tokens are short-lived (60 min), RS256 signed
- All officer actions require TOTP (MFA)
- No direct database access from application — connection pool via SQLAlchemy
- Audit logs are append-only at DB permission level (`REVOKE UPDATE, DELETE`)
- Photos stored in S3 with pre-signed URLs (1h expiry), never public
- All inter-service communication over TLS within VPC

---

## Compliance

- Data residency: ap-south-1 (Mumbai) — India data stays in India
- Aadhaar handling follows UIDAI guidelines and IT Act 2000
- Audit logs retained for 7 years per government record-keeping requirements
- GDPR-equivalent: workers can request data access/correction via admin

---

## License

Government use — classified. Refer to your department's software licensing policy.

---

## Contact

System Architect: [Your Name]
Department: [Ministry / Department Name]
Version: 1.0.0
Last Updated: 2026-03
