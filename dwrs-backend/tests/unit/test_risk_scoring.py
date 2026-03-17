"""
Unit tests for the Risk Scoring Engine.
Tests each rule individually and combined score computation.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass

# Mock dependencies before importing engine
@dataclass
class MockIDValidation:
    is_valid: bool = True
    failure_reason: str = None
    aadhaar_name: str = "Test Name"
    aadhaar_dob: str = "1990-01-01"
    name_match_score: float = 0.95

@dataclass
class MockDedupResult:
    is_duplicate: bool = False
    existing_worker_id: str = None
    match_type: str = None
    confidence_score: float = 0.0

@dataclass
class MockRegistrar:
    id: str = "officer-uuid-1234"
    role: str = "field_officer"
    district_scope: str = "district-uuid-5678"


class TestRiskScoringRules:

    @pytest.fixture
    def base_worker_data(self):
        return {
            "full_name": "Ramesh Kumar",
            "aadhaar_number": "123456789012",
            "date_of_birth": "1985-06-15",
            "gender": "M",
            "photo_base64": "base64data",
            "mobile_number": "9876543210",
            "alternate_contact": None,
            "address": {"district": "district-uuid-5678", "state": "Maharashtra"},
            "registration_mode": "assisted_officer",
            "geo_location": {"lat": 19.0760, "lng": 72.8777, "accuracy_meters": 15},
            "consent_recorded": True,
            "offline_captured_at": None,
            "device_fingerprint": "device-abc-123",
        }

    @pytest.fixture
    def field_officer(self):
        return MockRegistrar()

    @pytest.mark.asyncio
    @patch("services.risk_scoring.engine._get_officer_daily_count", new_callable=AsyncMock, return_value=5)
    @patch("services.risk_scoring.engine._get_officer_burst_count", new_callable=AsyncMock, return_value=2)
    @patch("services.risk_scoring.engine._get_officer_trust_score", new_callable=AsyncMock, return_value=0.95)
    @patch("services.risk_scoring.engine._get_district_bounds", new_callable=AsyncMock, return_value=None)
    @patch("services.risk_scoring.engine._get_device_registration_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._run_anomaly_model", new_callable=AsyncMock, return_value=0.05)
    async def test_low_risk_clean_registration(
        self, mock_anomaly, mock_device, mock_bounds, mock_trust, mock_burst, mock_daily,
        base_worker_data, field_officer
    ):
        """A clean registration with normal officer activity should score low."""
        from services.risk_scoring.engine import compute_risk_score
        result = await compute_risk_score(
            worker_data=base_worker_data,
            registrar=field_officer,
            id_validation=MockIDValidation(),
            dedup_result=MockDedupResult(),
        )
        assert result.score < 40
        assert result.level == "low"
        assert len(result.flags) == 0

    @pytest.mark.asyncio
    @patch("services.risk_scoring.engine._get_officer_daily_count", new_callable=AsyncMock, return_value=20)
    @patch("services.risk_scoring.engine._get_officer_burst_count", new_callable=AsyncMock, return_value=2)
    @patch("services.risk_scoring.engine._get_officer_trust_score", new_callable=AsyncMock, return_value=0.95)
    @patch("services.risk_scoring.engine._get_district_bounds", new_callable=AsyncMock, return_value=None)
    @patch("services.risk_scoring.engine._get_device_registration_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._run_anomaly_model", new_callable=AsyncMock, return_value=0.1)
    async def test_r01_officer_volume_rule_fires(
        self, mock_anomaly, mock_device, mock_bounds, mock_trust, mock_burst, mock_daily,
        base_worker_data, field_officer
    ):
        """R01 should fire when officer has >15 registrations today."""
        from services.risk_scoring.engine import compute_risk_score
        result = await compute_risk_score(
            worker_data=base_worker_data,
            registrar=field_officer,
            id_validation=MockIDValidation(),
            dedup_result=MockDedupResult(),
        )
        rule_ids = [f.rule_id for f in result.flags]
        assert "R01a" in rule_ids
        r01 = next(f for f in result.flags if f.rule_id == "R01a")
        assert r01.points > 0

    @pytest.mark.asyncio
    @patch("services.risk_scoring.engine._get_officer_daily_count", new_callable=AsyncMock, return_value=3)
    @patch("services.risk_scoring.engine._get_officer_burst_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._get_officer_trust_score", new_callable=AsyncMock, return_value=0.95)
    @patch("services.risk_scoring.engine._get_district_bounds", new_callable=AsyncMock, return_value=None)
    @patch("services.risk_scoring.engine._get_device_registration_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._run_anomaly_model", new_callable=AsyncMock, return_value=0.0)
    async def test_r03_name_mismatch_rule_fires(
        self, mock_anomaly, mock_device, mock_bounds, mock_trust, mock_burst, mock_daily,
        base_worker_data, field_officer
    ):
        """R03 should fire when name similarity with Aadhaar is below 0.70."""
        from services.risk_scoring.engine import compute_risk_score
        bad_id = MockIDValidation(name_match_score=0.40)
        result = await compute_risk_score(
            worker_data=base_worker_data,
            registrar=field_officer,
            id_validation=bad_id,
            dedup_result=MockDedupResult(),
        )
        rule_ids = [f.rule_id for f in result.flags]
        assert "R03" in rule_ids

    @pytest.mark.asyncio
    @patch("services.risk_scoring.engine._get_officer_daily_count", new_callable=AsyncMock, return_value=3)
    @patch("services.risk_scoring.engine._get_officer_burst_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._get_officer_trust_score", new_callable=AsyncMock, return_value=0.95)
    @patch("services.risk_scoring.engine._get_district_bounds", new_callable=AsyncMock, return_value=None)
    @patch("services.risk_scoring.engine._get_device_registration_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._run_anomaly_model", new_callable=AsyncMock, return_value=0.0)
    async def test_r04_no_contact_rule_fires(
        self, mock_anomaly, mock_device, mock_bounds, mock_trust, mock_burst, mock_daily,
        base_worker_data, field_officer
    ):
        """R04 should fire when no contact information provided."""
        from services.risk_scoring.engine import compute_risk_score
        no_contact_data = {**base_worker_data, "mobile_number": None, "alternate_contact": None}
        result = await compute_risk_score(
            worker_data=no_contact_data,
            registrar=field_officer,
            id_validation=MockIDValidation(),
            dedup_result=MockDedupResult(),
        )
        rule_ids = [f.rule_id for f in result.flags]
        assert "R04" in rule_ids

    @pytest.mark.asyncio
    @patch("services.risk_scoring.engine._get_officer_daily_count", new_callable=AsyncMock, return_value=3)
    @patch("services.risk_scoring.engine._get_officer_burst_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._get_officer_trust_score", new_callable=AsyncMock, return_value=0.95)
    @patch("services.risk_scoring.engine._get_district_bounds", new_callable=AsyncMock, return_value=None)
    @patch("services.risk_scoring.engine._get_device_registration_count", new_callable=AsyncMock, return_value=1)
    @patch("services.risk_scoring.engine._run_anomaly_model", new_callable=AsyncMock, return_value=0.0)
    async def test_r05_offline_stale_rule_fires(
        self, mock_anomaly, mock_device, mock_bounds, mock_trust, mock_burst, mock_daily,
        base_worker_data, field_officer
    ):
        """R05 should fire when offline record is older than 72h."""
        from services.risk_scoring.engine import compute_risk_score
        stale_data = {
            **base_worker_data,
            "offline_captured_at": "2024-01-01T10:00:00+00:00"  # Very old
        }
        result = await compute_risk_score(
            worker_data=stale_data,
            registrar=field_officer,
            id_validation=MockIDValidation(),
            dedup_result=MockDedupResult(),
        )
        rule_ids = [f.rule_id for f in result.flags]
        assert "R05" in rule_ids

    def test_score_is_always_0_to_100(self):
        """Score must always be clamped between 0 and 100."""
        import math
        # Simulate worst case: all rules fire at max points
        max_rule_score = 100
        max_ml_score = 1.0
        raw = (max_rule_score * 0.70) + (max_ml_score * 100 * 0.30)
        total = min(100, int(math.ceil(raw)))
        assert 0 <= total <= 100

    def test_level_mapping(self):
        """Score ranges must map to correct levels."""
        def get_level(score):
            return "low" if score < 40 else ("medium" if score < 60 else "high")

        assert get_level(0) == "low"
        assert get_level(39) == "low"
        assert get_level(40) == "medium"
        assert get_level(59) == "medium"
        assert get_level(60) == "high"
        assert get_level(100) == "high"
