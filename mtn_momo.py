import os
import uuid
import base64
import requests

MTN_BASE_URL = os.getenv(
    "MTN_BASE_URL",
    "https://sandbox.momodeveloper.mtn.com"
)

MTN_SUBSCRIPTION_KEY = os.getenv("MTN_SUBSCRIPTION_KEY", "")
MTN_API_USER = os.getenv("MTN_API_USER", "")
MTN_API_KEY = os.getenv("MTN_API_KEY", "")
MTN_TARGET_ENVIRONMENT = os.getenv(
    "MTN_TARGET_ENVIRONMENT",
    "sandbox"
)

def configured():
    return all([
        MTN_SUBSCRIPTION_KEY,
        MTN_API_USER,
        MTN_API_KEY
    ])

def get_access_token():
    if not configured():
        return None, "MTN_API_NOT_CONFIGURED"

    credentials = base64.b64encode(
        f"{MTN_API_USER}:{MTN_API_KEY}".encode()
    ).decode()

    url = f"{MTN_BASE_URL}/collection/token/"

    headers = {
        "Authorization": f"Basic {credentials}",
        "Ocp-Apim-Subscription-Key": MTN_SUBSCRIPTION_KEY,
        "Content-Type": "application/json",
        "X-Target-Environment": MTN_TARGET_ENVIRONMENT
    }

    r = requests.post(url, headers=headers, timeout=20)

    if r.status_code != 200:
        return None, f"MTN_TOKEN_ERROR_{r.status_code}"

    data = r.json()
    token = data.get("access_token")

    if not token:
        return None, "MTN_TOKEN_MISSING"

    return token, None

def request_to_pay(amount, payer_msisdn, external_id):
    token, error = get_access_token()

    if error:
        return None, error

    reference_id = str(uuid.uuid4())

    url = f"{MTN_BASE_URL}/collection/v1_0/requesttopay"

    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": MTN_SUBSCRIPTION_KEY,
        "X-Reference-Id": reference_id,
        "X-Target-Environment": MTN_TARGET_ENVIRONMENT,
        "Content-Type": "application/json"
    }

    payload = {
        "amount": str(amount),
        "currency": "UGX",
        "externalId": str(external_id),
        "payer": {
            "partyIdType": "MSISDN",
            "partyId": str(payer_msisdn)
        },
        "payerMessage": "NEXORA deposit",
        "payeeNote": "NEXORA deposit"
    }

    r = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20
    )

    if r.status_code != 202:
        return None, f"MTN_REQUEST_ERROR_{r.status_code}:{r.text[:300]}"

    return reference_id, None

def payment_status(reference_id):
    token, error = get_access_token()

    if error:
        return None, error

    url = (
        f"{MTN_BASE_URL}/collection/v1_0/"
        f"requesttopay/{reference_id}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": MTN_SUBSCRIPTION_KEY,
        "X-Target-Environment": MTN_TARGET_ENVIRONMENT
    }

    r = requests.get(
        url,
        headers=headers,
        timeout=20
    )

    if r.status_code != 200:
        return None, f"MTN_STATUS_ERROR_{r.status_code}"

    return r.json(), None
