"""
Face Match Service
Uses AWS Rekognition for production face comparison.
Falls back to local OpenCV-based matching for development.
"""
import base64
import structlog
from dataclasses import dataclass
import boto3
from shared.utils.config import settings

logger = structlog.get_logger()


@dataclass
class FaceMatchResult:
    similarity: float   # 0.0–1.0 (Rekognition returns 0–100, we normalise)
    matched: bool
    method: str


class FaceMatchService:

    def __init__(self):
        self.client = boto3.client("rekognition", region_name=settings.AWS_REGION)

    async def compare(self, stored_photo_url: str, live_photo_b64: str) -> FaceMatchResult:
        """
        Compare stored worker photo with live capture.
        stored_photo_url: S3 URL (fetched internally).
        live_photo_b64: Base64 JPEG from officer's device.
        """
        try:
            # Decode live photo
            live_bytes = base64.b64decode(live_photo_b64)

            # Fetch stored photo from S3
            stored_bytes = await _fetch_s3_photo(stored_photo_url)

            response = self.client.compare_faces(
                SourceImage={"Bytes": stored_bytes},
                TargetImage={"Bytes": live_bytes},
                SimilarityThreshold=70.0,  # Minimum to return a result
                QualityFilter="AUTO",
            )

            face_matches = response.get("FaceMatches", [])
            if not face_matches:
                return FaceMatchResult(similarity=0.0, matched=False, method="aws_rekognition")

            # Use the highest similarity match
            similarity = max(m["Similarity"] for m in face_matches) / 100.0
            return FaceMatchResult(
                similarity=round(similarity, 4),
                matched=similarity >= 0.85,
                method="aws_rekognition",
            )

        except self.client.exceptions.InvalidParameterException as e:
            logger.warning("rekognition_no_face_detected", error=str(e))
            return FaceMatchResult(similarity=0.0, matched=False, method="aws_rekognition")
        except Exception as e:
            logger.error("rekognition_error", error=str(e))
            # Fall back to local matching in development
            if settings.APP_ENV == "development":
                return await _local_face_compare(stored_photo_url, live_photo_b64)
            raise


async def get_face_embedding(photo_b64: str) -> list:
    """
    Extract 512-dimensional face embedding for duplicate detection (pgvector).
    Uses AWS Rekognition index face feature in dev/mock mode.
    """
    try:
        import numpy as np
        # In production: use Rekognition SearchFacesByImage or a dedicated embedding model
        # Here we return a mock embedding for scaffold purposes
        photo_bytes = base64.b64decode(photo_b64)
        # TODO: Replace with actual embedding extraction
        mock_embedding = [0.0] * 512
        return mock_embedding
    except Exception as e:
        logger.error("face_embedding_failed", error=str(e))
        return [0.0] * 512


async def _fetch_s3_photo(s3_url: str) -> bytes:
    """Fetch photo bytes from S3 pre-signed URL."""
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(s3_url, timeout=5.0)
        response.raise_for_status()
        return response.content


async def _local_face_compare(stored_url: str, live_b64: str) -> FaceMatchResult:
    """Development fallback using face_recognition library."""
    try:
        import face_recognition
        import numpy as np
        stored_bytes = await _fetch_s3_photo(stored_url)
        live_bytes = base64.b64decode(live_b64)

        stored_img = face_recognition.load_image_file(stored_bytes)
        live_img = face_recognition.load_image_file(live_bytes)

        stored_enc = face_recognition.face_encodings(stored_img)
        live_enc = face_recognition.face_encodings(live_img)

        if not stored_enc or not live_enc:
            return FaceMatchResult(similarity=0.0, matched=False, method="local_face_recognition")

        distance = face_recognition.face_distance([stored_enc[0]], live_enc[0])[0]
        similarity = max(0.0, 1.0 - distance)
        return FaceMatchResult(
            similarity=round(similarity, 4),
            matched=similarity >= 0.85,
            method="local_face_recognition",
        )
    except Exception as e:
        logger.error("local_face_compare_failed", error=str(e))
        return FaceMatchResult(similarity=0.0, matched=False, method="local_face_recognition")


# Singleton instance
face_match_service = FaceMatchService()
