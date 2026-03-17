"""
TOTP (Time-based One-Time Password) for MFA.
Uses pyotp — compatible with Google Authenticator, Authy, etc.
"""
import pyotp
import qrcode
import io
import base64


def generate_totp_secret() -> str:
    """Generate a new base32 TOTP secret for a user."""
    return pyotp.random_base32()


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verify a TOTP code.
    valid_window=1 allows 1 step before/after for clock drift (30s window each side).
    """
    if not secret or not code:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=valid_window)


def get_totp_uri(secret: str, username: str, issuer: str = "DWRS") -> str:
    """Generate an otpauth:// URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def generate_qr_code_b64(secret: str, username: str) -> str:
    """Generate a base64-encoded PNG QR code for MFA setup."""
    uri = get_totp_uri(secret, username)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
