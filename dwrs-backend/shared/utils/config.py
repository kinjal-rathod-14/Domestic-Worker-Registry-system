"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe env loading.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///dwrs_local.db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""
    SESSION_TTL_SECONDS: int = 3600

    # JWT
    JWT_PRIVATE_KEY_PATH: str = "./keys/private.pem"
    JWT_PUBLIC_KEY_PATH: str = "./keys/public.pem"
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Encryption
    ENCRYPTION_KEY: str = ""
    AADHAAR_SALT: str = ""

    # UIDAI
    UIDAI_AUTH_URL: str = "mock"
    UIDAI_AUA_CODE: str = ""
    UIDAI_ASA_CODE: str = ""
    UIDAI_LICENSE_KEY: str = ""
    UIDAI_CERT_PATH: str = ""

    # AWS
    AWS_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_PHOTOS: str = "dwrs-worker-photos-dev"
    S3_BUCKET_DOCUMENTS: str = "dwrs-worker-docs-dev"
    S3_PRESIGNED_URL_EXPIRY: int = 3600

    # Rekognition
    REKOGNITION_COLLECTION_ID: str = "dwrs-faces-dev"
    FACE_MATCH_THRESHOLD: float = 85.0

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_PREFIX: str = "dwrs."

    # Elasticsearch
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_INDEX_AUDIT: str = "dwrs-audit-logs"

    # SMS / OTP
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    OTP_EXPIRY_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 3

    # Risk Scoring
    RISK_LOW_THRESHOLD: int = 40
    RISK_MEDIUM_THRESHOLD: int = 60
    OFFICER_MAX_DAILY_REGISTRATIONS: int = 15
    OFFICER_BURST_WINDOW_MINUTES: int = 30
    OFFICER_BURST_MAX_COUNT: int = 5
    OFFLINE_SYNC_MAX_AGE_HOURS: int = 72
    OFFICER_TRUST_LOW_THRESHOLD: float = 0.40
    OFFICER_TRUST_SUSPEND_THRESHOLD: float = 0.25
    GEO_MAX_ACCURACY_METERS: int = 200
    GEO_ADDRESS_MAX_DISTANCE_KM: float = 2.0
    RANDOM_AUDIT_PERCENTAGE: int = 10

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Monitoring
    SENTRY_DSN: str = ""
    PROMETHEUS_ENABLED: bool = True

    # Audit
    AUDIT_CHAIN_GENESIS_HASH: str = "GENESIS_0000000000000000000000000000000000000000000000000000000000"

    @property
    def JWT_PRIVATE_KEY(self) -> str:
        with open(self.JWT_PRIVATE_KEY_PATH) as f:
            return f.read()

    @property
    def JWT_PUBLIC_KEY(self) -> str:
        with open(self.JWT_PUBLIC_KEY_PATH) as f:
            return f.read()


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
