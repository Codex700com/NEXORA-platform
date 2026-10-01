import os
import hmac
import hashlib
import json
from decimal import Decimal, InvalidOperation
from flask import request, jsonify

PAYMENT_DESTINATION = os.getenv(
    "PAYMENT_DESTINATION",
    "0757837051"
)

PAYMENT_RECIPIENT = os.getenv(
    "PAYMENT_RECIPIENT",
    "Mary Namara"
)

WEBHOOK_SECRET = os.getenv(
    "PAYMENT_WEBHOOK_SECRET",
    ""
)

def normalize_phone(value):
    return "".join(str(value or "").split())

def amount_equal(a, b):
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, TypeError, ValueError):
        return False

def verify_webhook_signature(raw_body, signature):
    if not WEBHOOK_SECRET:
        return False

    if not signature:
        return False

    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    supplied = str(signature).replace("sha256=", "").strip()

    return hmac.compare_digest(expected, supplied)

def normalize_provider_event(data):
    """
    Provider-neutral event format.

    Expected provider event:

    {
      "reference": "...",
      "status": "SUCCESSFUL",
      "amount": 50000,
      "currency": "UGX",
      "recipient": "0757837051",
      "payer": "2567...",
      "timestamp": "..."
    }
    """

    return {
        "reference": str(
            data.get("reference")
            or data.get("transaction_id")
            or data.get("transactionId")
            or ""
        ).strip(),

        "status": str(
            data.get("status")
            or ""
        ).upper().strip(),

        "amount": data.get("amount"),

        "currency": str(
            data.get("currency")
            or "UGX"
        ).upper().strip(),

        "recipient": normalize_phone(
            data.get("recipient")
            or data.get("payee")
            or data.get("merchant")
            or ""
        ),

        "payer": normalize_phone(
            data.get("payer")
            or data.get("payer_number")
            or data.get("phone")
            or ""
        ),

        "timestamp": data.get("timestamp")
    }

def validate_event(event, expected_amount):
    if not event["reference"]:
        return False, "MISSING_REFERENCE"

    if event["status"] not in (
        "SUCCESSFUL",
        "SUCCESS",
        "COMPLETED"
    ):
        return False, "PAYMENT_NOT_SUCCESSFUL"

    if event["currency"] != "UGX":
        return False, "CURRENCY_MISMATCH"

    if not amount_equal(event["amount"], expected_amount):
        return False, "AMOUNT_MISMATCH"

    if normalize_phone(event["recipient"]) != normalize_phone(
        PAYMENT_DESTINATION
    ):
        return False, "RECIPIENT_MISMATCH"

    return True, "VERIFIED"
