import httpx
from fastapi import HTTPException

from auth import decode_access_token


TASK_SERVICE_URL = "http://task-service:8000"
NOTIFICATION_SERVICE_URL = "http://notification-service:8000"


class APIRequestError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def api_request(
    base_url: str,
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
):
    try:
        response = httpx.request(
            method,
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=5,
        )
    except httpx.RequestError as exc:
        raise APIRequestError(503, "A required REST service is unavailable") from exc

    if not response.is_success:
        try:
            body = response.json()
            detail = body.get("detail", "REST request failed")
        except ValueError:
            detail = "REST request failed"
        raise APIRequestError(response.status_code, str(detail)[:500])

    if not response.content:
        return None
    return response.json()


def get_current_user(token: str) -> dict:
    claims = decode_access_token(token)
    if not claims.get("email"):
        raise HTTPException(status_code=401, detail="Could not verify current user")
    return {"id": claims["sub"], "email": claims["email"]}


def token_subject(token: str) -> str:
    return decode_access_token(token)["sub"]
