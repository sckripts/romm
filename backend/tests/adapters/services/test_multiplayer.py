import io
import json
import urllib.error
from email.message import Message
from unittest.mock import patch

import pytest

from adapters.services.multiplayer import (
    ExternalMultiplayerProviderError,
    ExternalMultiplayerSessionProvider,
)

TOKEN = "t" * 32


class Response:
    status = 200

    def __init__(self, document: object) -> None:
        self.body = io.BytesIO(json.dumps(document).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size: int) -> bytes:
        return self.body.read(size)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/provider",
        "http://user:password@provider",
        "http://provider?token=secret",
        "http://provider#fragment",
    ],
)
def test_rejects_unsafe_provider_urls(url: str):
    with pytest.raises(ValueError):
        ExternalMultiplayerSessionProvider(url, TOKEN, 10)


def test_forwards_service_and_actor_identity_headers():
    provider = ExternalMultiplayerSessionProvider("http://provider:8000", TOKEN, 10)
    with patch(
        "adapters.services.multiplayer.urllib.request.urlopen",
        return_value=Response({"session_id": "test"}),
    ) as urlopen:
        status, document = provider.request(
            "POST",
            "/v1/sessions",
            actor_id="romm-42",
            actor_name="player",
            body={"romm_rom_id": 7},
        )

    request = urlopen.call_args.args[0]
    assert status == 200
    assert document == {"session_id": "test"}
    assert request.get_header("Authorization") == f"Bearer {TOKEN}"
    assert request.get_header("X-authenticated-user-id") == "romm-42"
    assert request.get_header("X-authenticated-user-display-name") == "player"
    assert json.loads(request.data) == {"romm_rom_id": 7}


def test_preserves_provider_http_error_body():
    provider = ExternalMultiplayerSessionProvider("http://provider", TOKEN, 10)
    error = urllib.error.HTTPError(
        "http://provider/v1/sessions",
        409,
        "Conflict",
        Message(),
        io.BytesIO(b'{"error":"full"}'),
    )
    with patch(
        "adapters.services.multiplayer.urllib.request.urlopen", side_effect=error
    ):
        status, document = provider.request("POST", "/v1/sessions")

    assert status == 409
    assert document == {"error": "full"}


def test_rejects_invalid_json():
    provider = ExternalMultiplayerSessionProvider("http://provider", TOKEN, 10)
    response = Response({})
    response.body = io.BytesIO(b"not-json")
    with (
        patch(
            "adapters.services.multiplayer.urllib.request.urlopen",
            return_value=response,
        ),
        pytest.raises(ExternalMultiplayerProviderError),
    ):
        provider.request("GET", "/v1/sessions")
