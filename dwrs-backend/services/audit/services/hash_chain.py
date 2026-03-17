"""
Audit Hash Chain Service
Every audit record contains the SHA-256 hash of the previous record.
Any tampering breaks the chain — detectable by verify_chain_integrity().
The application DB user has INSERT-only privileges on audit_records.
"""
import hashlib
import json
import structlog
from datetime import datetime, timezone
from shared.db.postgres import db
from services.audit.services.alert import alert_security_team

logger = structlog.get_logger()

GENESIS_HASH = "GENESIS_0000000000000000000000000000000000000000000000000000000000"


class AuditChain:

    async def append(
        self,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str | None,
        before_state: dict | None,
        after_state: dict | None,
        request_context,
    ) -> str:
        """
        Append a new immutable audit record to the chain.
        Returns the new record's hash.
        """
        # Get previous record's hash for chain linking
        prev_record = await db.fetchrow(
            "SELECT record_hash FROM audit_records ORDER BY created_at DESC LIMIT 1"
        )
        prev_hash = prev_record["record_hash"] if prev_record else GENESIS_HASH

        created_at = datetime.now(timezone.utc).isoformat()

        record_data = {
            "actor_id": str(actor_id),
            "actor_role": getattr(request_context, "role", "system"),
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "before_state": json.dumps(before_state, sort_keys=True) if before_state else None,
            "after_state": json.dumps(after_state, sort_keys=True) if after_state else None,
            "ip_address": getattr(request_context, "ip", "internal"),
            "session_id": str(getattr(request_context, "session_id", "")),
            "created_at": created_at,
            "prev_hash": prev_hash,
        }

        # Deterministic hash — same input always produces same hash
        record_hash = hashlib.sha256(
            json.dumps(record_data, sort_keys=True).encode("utf-8")
        ).hexdigest()

        await db.execute("""
            INSERT INTO audit_records (
                actor_id, actor_role, action, entity_type, entity_id,
                before_state, after_state, ip_address, session_id,
                prev_hash, record_hash, created_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
            )
        """,
            record_data["actor_id"],
            record_data["actor_role"],
            record_data["action"],
            record_data["entity_type"],
            record_data["entity_id"],
            record_data["before_state"],
            record_data["after_state"],
            record_data["ip_address"],
            record_data["session_id"],
            record_data["prev_hash"],
            record_hash,
            created_at,
        )

        return record_hash

    async def verify_chain_integrity(self) -> dict:
        """
        Walk the entire audit chain and verify each record's hash.
        Should be run nightly via cron — triggers alert if chain is broken.
        Returns: {"valid": bool, "records_checked": int, "broken_at": UUID | None}
        """
        records = await db.fetch(
            "SELECT * FROM audit_records ORDER BY created_at ASC"
        )

        if not records:
            return {"valid": True, "records_checked": 0, "broken_at": None}

        prev_hash = GENESIS_HASH
        for record in records:
            expected_hash = self._compute_expected_hash(record, prev_hash)

            if expected_hash != record["record_hash"]:
                logger.error(
                    "audit_chain_integrity_violation",
                    record_id=str(record["id"]),
                    expected=expected_hash,
                    stored=record["record_hash"],
                )
                await alert_security_team(
                    event="AUDIT_CHAIN_TAMPER_DETECTED",
                    details={
                        "record_id": str(record["id"]),
                        "expected_hash": expected_hash,
                        "stored_hash": record["record_hash"],
                        "action": record["action"],
                        "actor_id": str(record["actor_id"]),
                        "created_at": str(record["created_at"]),
                    }
                )
                return {
                    "valid": False,
                    "records_checked": records.index(record) + 1,
                    "broken_at": str(record["id"]),
                }

            prev_hash = record["record_hash"]

        logger.info("audit_chain_verified", records_checked=len(records))
        return {"valid": True, "records_checked": len(records), "broken_at": None}

    def _compute_expected_hash(self, record: dict, prev_hash: str) -> str:
        """Recompute the expected hash for a stored record."""
        record_data = {
            "actor_id": str(record["actor_id"]),
            "actor_role": record["actor_role"],
            "action": record["action"],
            "entity_type": record["entity_type"],
            "entity_id": str(record["entity_id"]) if record["entity_id"] else None,
            "before_state": record["before_state"],
            "after_state": record["after_state"],
            "ip_address": record["ip_address"],
            "session_id": str(record["session_id"]),
            "created_at": record["created_at"].isoformat() if hasattr(record["created_at"], "isoformat") else str(record["created_at"]),
            "prev_hash": prev_hash,
        }
        return hashlib.sha256(
            json.dumps(record_data, sort_keys=True).encode("utf-8")
        ).hexdigest()
