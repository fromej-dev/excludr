"""Minimal Stripe REST client: Checkout Sessions and webhook signatures.

Talks to the API with httpx (form-encoded, as Stripe expects) so tests can swap
in an ``httpx.MockTransport`` through :func:`get_http_client`.
"""

import hashlib
import hmac
import json
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

STRIPE_API_URL = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300


class StripeError(Exception):
    """The Stripe API rejected a request or could not be reached."""


class InvalidSignatureError(Exception):
    """A webhook payload did not carry a valid ``Stripe-Signature``."""


def get_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=STRIPE_API_URL, timeout=15.0)


def encode_form(params: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Flatten nested dicts/lists into Stripe's ``a[b][0][c]=v`` form fields."""
    fields: list[tuple[str, str]] = []
    items = params.items() if isinstance(params, dict) else enumerate(params)
    for key, value in items:
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, (dict, list)):
            fields.extend(encode_form(value, name))
        elif isinstance(value, bool):
            fields.append((name, "true" if value else "false"))
        elif value is not None:
            fields.append((name, str(value)))
    return fields


async def create_checkout_session(
    secret_key: str, params: dict[str, Any], idempotency_key: Optional[str] = None
) -> dict[str, Any]:
    """Create a Checkout Session and return Stripe's JSON object."""
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        async with get_http_client() as client:
            response = await client.post(
                "/checkout/sessions",
                content=urlencode(encode_form(params)),
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise StripeError("Could not reach Stripe") from exc
    if response.status_code >= 400:
        try:
            message = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = f"HTTP {response.status_code}"
        raise StripeError(message)
    return response.json()


def sign_payload(payload: bytes, secret: str, timestamp: int) -> str:
    """Signature header value Stripe would send for ``payload`` (used by tests)."""
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_webhook(
    payload: bytes,
    signature_header: Optional[str],
    secret: str,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Check a webhook's ``Stripe-Signature`` and return the parsed event.

    Raises:
        InvalidSignatureError: missing/malformed header, no matching ``v1``
            signature, or a timestamp outside the replay tolerance.
    """
    if not signature_header:
        raise InvalidSignatureError("Missing Stripe-Signature header")
    timestamp: Optional[int] = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise InvalidSignatureError("Malformed timestamp") from None
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        raise InvalidSignatureError("Malformed Stripe-Signature header")
    now = time.time() if now is None else now
    if abs(now - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        raise InvalidSignatureError("Timestamp outside the tolerance zone")
    expected = sign_payload(payload, secret, timestamp).split("v1=", 1)[1]
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise InvalidSignatureError("No matching signature")
    try:
        return json.loads(payload)
    except ValueError:
        raise InvalidSignatureError("Payload is not JSON") from None
