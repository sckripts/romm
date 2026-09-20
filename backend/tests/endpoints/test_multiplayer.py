from datetime import UTC, datetime
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from main import app as _app  # noqa: F401 - initialize RomM's endpoint import order

multiplayer = import_module("endpoints.multiplayer")


def provider_session(actor_id: str) -> dict[str, object]:
    return {
        "session_id": str(uuid4()),
        "display_name": "Saturday session",
        "owner_user_id": actor_id,
        "romm_rom_id": 42,
        "platform": "nes",
        "max_players": 2,
        "state": "OPEN",
        "participants": [
            {
                "participant_id": str(uuid4()),
                "user_id": actor_id,
                "display_name": "Player One",
                "player_slot": 1,
                "state": "JOINED",
                "runtime_container_id": "must-not-leak",
            }
        ],
        "player_count": 1,
        "expires_at": datetime.now(UTC).isoformat(),
        "rom_sha256": "a" * 64,
        "host_address": "172.20.0.9",
        "netplay_port": 55435,
    }


def test_browser_session_schema_drops_private_provider_fields():
    actor_id = "romm-7"
    result = multiplayer._validated_session(provider_session(actor_id), actor_id)
    document = result.model_dump(mode="json")

    assert document["can_close"] is True
    assert document["is_participant"] is True
    assert document["participants"][0]["display_name"] == "Player One"
    serialized = str(document)
    for private_value in [actor_id, "must-not-leak", "172.20.0.9", "55435", "a" * 64]:
        assert private_value not in serialized


def test_game_path_is_confined_to_library_root(tmp_path, monkeypatch):
    root = tmp_path / "library"
    game = root / "nes" / "roms" / "game.nes"
    game.parent.mkdir(parents=True)
    game.write_bytes(b"test game bytes")
    monkeypatch.setattr(multiplayer, "LIBRARY_BASE_PATH", str(root))

    path, relative = multiplayer._game_path(
        SimpleNamespace(full_path="nes/roms/game.nes")
    )

    assert path == game
    assert relative == "nes/roms/game.nes"


@pytest.mark.parametrize("relative", ["../game.nes", "/tmp/game.nes", "C:\\game.nes"])
def test_game_path_rejects_untrusted_paths(tmp_path, monkeypatch, relative):
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr(multiplayer, "LIBRARY_BASE_PATH", str(root))

    with pytest.raises(HTTPException) as error:
        multiplayer._game_path(SimpleNamespace(full_path=relative))

    assert error.value.status_code == 409


def test_private_resolver_uses_constant_service_credential(monkeypatch):
    monkeypatch.setattr(multiplayer, "EXTERNAL_MULTIPLAYER_ENABLED", True)
    monkeypatch.setattr(multiplayer, "EXTERNAL_MULTIPLAYER_TOKEN", "s" * 32)

    multiplayer._authenticate_provider("s" * 32)
    with pytest.raises(HTTPException) as error:
        multiplayer._authenticate_provider("x" * 32)

    assert error.value.status_code == 401
