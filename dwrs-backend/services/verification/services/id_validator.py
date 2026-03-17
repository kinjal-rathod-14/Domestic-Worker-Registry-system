"""
ID Validation Service — UIDAI Aadhaar e-KYC
Production: Calls the UIDAI Auth API.
Development: Returns mock responses if UIDAI_AUTH_URL is set to 'mock'.

Important: UIDAI failure is NOT an auto-pass. The system marks the record
as id_check_pending and queues for retry/manual verification.
"""
import structlog
import httpx
from dataclasses import dataclass
from tenacity import retry, stop_after_attempt, wait_exponential
from shared.utils.config import settings
from shared.utils.validators import fuzzy_name_match

logger = structlog.get_logger()


@dataclass
class IDValidationResult:
    is_valid: bool
    failure_reason: str | None
    aadhaar_name: str | None
    aadhaar_dob: str | None
    name_match_score: float   # 0–1 fuzzy match between submitted name and Aadhaar name


@dataclass
class LivenessResult:
    is_live: bool
    score: float


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def validate_aadhaar(aadhaar: str, name: str, dob: str) -> IDValidationResult:
    """
    Validates Aadhaar against UIDAI.
    Retries up to 3 times with exponential backoff.
    Network failure → returns failure (not auto-pass).
    """
    if settings.APP_ENV == "development" and settings.UIDAI_AUTH_URL == "mock":
        return _mock_uidai_response(aadhaar, name, dob)

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=settings.UIDAI_CERT_PATH) as client:
            response = await client.post(
                f"{settings.UIDAI_AUTH_URL}/{aadhaar}/{settings.UIDAI_AUA_CODE}",
                json={
                    "uid": aadhaar,
                    "name": name,
                    "dob": dob,
                    "ver": "2.5",
                    "ac": settings.UIDAI_AUA_CODE,
                    "sa": settings.UIDAI_ASA_CODE,
                    "lk": settings.UIDAI_LICENSE_KEY,
                },
                headers={"Content-Type": "application/json"},
            )

        data = response.json()

        if data.get("ret") != "y":
            return IDValidationResult(
                is_valid=False,
                failure_reason=_map_uidai_error(data.get("err", "UNKNOWN")),
                aadhaar_name=None,
                aadhaar_dob=None,
                name_match_score=0.0,
            )

        aadhaar_name = data.get("name", "")
        name_score = fuzzy_name_match(name, aadhaar_name)

        return IDValidationResult(
            is_valid=True,
            failure_reason=None,
            aadhaar_name=aadhaar_name,
            aadhaar_dob=data.get("dob"),
            name_match_score=round(name_score, 4),
        )

    except httpx.TimeoutException:
        logger.warning("uidai_timeout", aadhaar_suffix=aadhaar[-4:])
        return IDValidationResult(
            is_valid=False,
            failure_reason="ID_AUTHORITY_UNAVAILABLE",
            aadhaar_name=None,
            aadhaar_dob=None,
            name_match_score=0.0,
        )
    except Exception as e:
        logger.error("uidai_unexpected_error", error=str(e))
        return IDValidationResult(
            is_valid=False,
            failure_reason="ID_AUTHORITY_UNAVAILABLE",
            aadhaar_name=None,
            aadhaar_dob=None,
            name_match_score=0.0,
        )


async def validate_liveness(liveness_token: str) -> LivenessResult:
    """
    Validates a liveness token from the frontend SDK (e.g. AWS Rekognition Face Liveness).
    """
    try:
        import boto3
        client = boto3.client("rekognition", region_name=settings.AWS_REGION)
        result = client.get_face_liveness_session_results(SessionId=liveness_token)
        confidence = result.get("Confidence", 0.0)
        return LivenessResult(is_live=confidence >= 90.0, score=round(confidence / 100, 4))
    except Exception as e:
        logger.error("liveness_check_failed", error=str(e))
        return LivenessResult(is_live=False, score=0.0)


def _mock_uidai_response(aadhaar: str, name: str, dob: str) -> IDValidationResult:
    """Development mock — returns valid for any 12-digit Aadhaar."""
    return IDValidationResult(
        is_valid=True,
        failure_reason=None,
        aadhaar_name=name,   # Mock: name matches exactly
        aadhaar_dob=dob,
        name_match_score=1.0,
    )


def _map_uidai_error(err_code: str) -> str:
    mapping = {
        "100": "UID_NOT_FOUND",
        "200": "DEMOGRAPHIC_MISMATCH",
        "300": "BIOMETRIC_LOCKED",
        "400": "OTP_INVALID",
        "500": "SERVER_ERROR",
        "997": "DEACTIVATED_UID",
        "998": "INVALID_AUTH_XML",
        "999": "XML_PARSE_FAILED",
    }
    return mapping.get(err_code, f"UIDAI_ERROR_{err_code}")
