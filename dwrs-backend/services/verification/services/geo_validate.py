"""
Geo Validation Service
Validates that the registration location matches the worker's declared address
and that the officer is operating within their assigned district boundary.
"""
import structlog
from dataclasses import dataclass
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from shapely.geometry import Point, Polygon
from shared.db.postgres import db

logger = structlog.get_logger()
geocoder = Nominatim(user_agent="dwrs-verification/1.0")


@dataclass
class GeoValidationResult:
    distance_km: float
    passed: bool
    claimed_coords: dict | None
    verification_coords: dict


async def geo_validate(
    claimed_address: dict,
    verification_location: dict,
) -> GeoValidationResult:
    """
    Validates that the GPS location at time of verification is within
    2km of the worker's registered address.
    """
    ver_coords = (
        verification_location.get("lat"),
        verification_location.get("lng"),
    )

    # Geocode the worker's registered address
    claimed_coords = await geocode_address(claimed_address)

    if not claimed_coords:
        logger.warning("geocode_failed", address=claimed_address)
        # Cannot validate — treat as soft pass, flag for review
        return GeoValidationResult(
            distance_km=9999.0,
            passed=False,
            claimed_coords=None,
            verification_coords={"lat": ver_coords[0], "lng": ver_coords[1]},
        )

    distance_km = geodesic(
        (claimed_coords["lat"], claimed_coords["lng"]),
        ver_coords,
    ).kilometers

    return GeoValidationResult(
        distance_km=round(distance_km, 3),
        passed=distance_km <= 2.0,
        claimed_coords=claimed_coords,
        verification_coords={"lat": ver_coords[0], "lng": ver_coords[1]},
    )


async def is_within_assigned_district(district_id: str, geo_location: dict) -> bool:
    """
    Checks whether a GPS point falls within a district's boundary polygon.
    District polygons are stored as GeoJSON in the districts table.
    """
    district = await db.fetchrow(
        "SELECT boundary_polygon FROM districts WHERE id = $1", district_id
    )
    if not district or not district["boundary_polygon"]:
        return True   # No boundary configured — soft pass

    try:
        boundary = district["boundary_polygon"]
        polygon_coords = boundary.get("coordinates", [[]])[0]
        polygon = Polygon([(c[0], c[1]) for c in polygon_coords])
        point = Point(geo_location.get("lng"), geo_location.get("lat"))
        return polygon.contains(point)
    except Exception as e:
        logger.error("district_boundary_check_failed", error=str(e))
        return True   # Soft pass on error — flag separately


def is_within_polygon(geo_location: dict, boundary: dict) -> bool:
    """
    Check if a geo point is within a polygon boundary.
    boundary: GeoJSON Polygon object.
    """
    try:
        polygon_coords = boundary.get("coordinates", [[]])[0]
        polygon = Polygon([(c[0], c[1]) for c in polygon_coords])
        point = Point(geo_location.get("lng"), geo_location.get("lat"))
        return polygon.contains(point)
    except Exception:
        return False


async def geocode_address(address: dict) -> dict | None:
    """Convert a structured address to GPS coordinates."""
    try:
        address_str = ", ".join(filter(None, [
            address.get("house"),
            address.get("street"),
            address.get("village"),
            address.get("district"),
            address.get("state"),
            address.get("pincode"),
            "India",
        ]))
        location = geocoder.geocode(address_str, timeout=5)
        if location:
            return {"lat": location.latitude, "lng": location.longitude}
        return None
    except Exception as e:
        logger.error("geocode_error", error=str(e))
        return None
