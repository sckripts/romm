import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

MAX_RESPONSE_BYTES = 1024 * 1024


class ExternalMultiplayerProviderError(Exception):
    pass


class ExternalMultiplayerSessionProvider:
    def __init__(self, base_url: str, token: str, timeout: int) -> None:
        normalized = base_url.rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("External multiplayer URL must be an HTTP(S) origin")
        if len(token) < 32:
            raise ValueError(
                "External multiplayer token must contain at least 32 characters"
            )
        if timeout <= 0:
            raise ValueError("External multiplayer timeout must be positive")
        self._base_url = normalized
        self._token = token
        self._timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        actor_id: str | None = None,
        actor_name: str | None = None,
        body: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        if actor_id is not None and actor_name is not None:
            headers["X-Authenticated-User-Id"] = actor_id
            headers["X-Authenticated-User-Display-Name"] = actor_name
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout
            ) as response:  # nosec B310
                status = response.status
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, urllib.error.URLError) as error:
            raise ExternalMultiplayerProviderError(
                "External multiplayer provider is unavailable"
            ) from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ExternalMultiplayerProviderError(
                "External multiplayer provider response is too large"
            )
        try:
            document = json.loads(raw) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalMultiplayerProviderError(
                "External multiplayer provider returned invalid JSON"
            ) from error
        return status, document
