"""
webhooks/signing.py

HMAC-SHA256 payload signing and verification.

─── Why sign webhook payloads? ────────────────────────────────────────────────
Anyone who knows your webhook URL can POST fake events to it.  By including a
cryptographic signature computed from a shared secret, the receiving server can
verify that the payload came from PayLedger and hasn't been tampered with.

─── How it works ──────────────────────────────────────────────────────────────
1. Sender computes:  HMAC-SHA256(secret, "timestamp.body")
2. Sender sends the signature in a header:
       X-PayLedger-Signature: t=<timestamp>,v1=<hex_signature>
3. Receiver reconstructs the same signature and compares with constant-time
   comparison (to prevent timing attacks).

The timestamp prevents replay attacks: if you receive the same signature 5
minutes later, the timestamp check can reject it.
"""

import hashlib
import hmac
import time


def sign_payload(secret: str, body: bytes) -> str:
    """
    Return the signature header value for a given payload.

    Format:  t=<unix_timestamp>,v1=<hex_hmac>
    """
    timestamp = int(time.time())
    # The signed string includes the timestamp to prevent replay attacks
    signed_string = f"{timestamp}.".encode() + body
    signature = hmac.new(
        secret.encode(),
        signed_string,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def verify_signature(secret: str, body: bytes, header: str, max_age_seconds: int = 300) -> bool:
    """
    Verify a signature header produced by sign_payload().

    Returns True if valid and not too old, False otherwise.
    """
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        received_sig = parts["v1"]
    except (KeyError, ValueError):
        return False

    # Reject old signatures (replay attack prevention)
    if abs(time.time() - timestamp) > max_age_seconds:
        return False

    signed_string = f"{timestamp}.".encode() + body
    expected_sig = hmac.new(
        secret.encode(),
        signed_string,
        hashlib.sha256,
    ).hexdigest()

    # constant-time comparison prevents timing side-channel attacks
    return hmac.compare_digest(expected_sig, received_sig)
