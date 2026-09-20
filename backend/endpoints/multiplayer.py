import asyncio
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import Body, Header, HTTPException, Query, Request, Response, status
from pydantic import ValidationError

from adapters.services.multiplayer import (
    ExternalMultiplayerProviderError,
    ExternalMultiplayerSessionProvider,
)
from config import (
    EXTERNAL_MULTIPLAYER_ENABLED,
    EXTERNAL_MULTIPLAYER_TIMEOUT,
    EXTERNAL_MULTIPLAYER_TOKEN,
    EXTERNAL_MULTIPLAYER_URL,
    LIBRARY_BASE_PATH,
)
from decorators.auth import protected_route
from endpoints.responses.multiplayer import (
    CreateMultiplayerSessionRequest,
    MultiplayerGameSchema,
    MultiplayerLaunchSchema,
    MultiplayerParticipantSchema,
    MultiplayerSessionListSchema,
    MultiplayerSessionSchema,
    ProviderSession,
)
from exceptions.endpoint_exceptions import RomNotFoundInDatabaseException
from handler.auth.constants import Scope
from handler.auth.dependencies import assert_rom_visible
from handler.database import db_rom_handler
from models.rom import Rom
from utils.router import APIRouter

router = APIRouter(prefix="/multiplayer", tags=["multiplayer"])
ExternalMultiplayerToken = Annotated[
    str | None, Header(alias="X-External-Multiplayer-Token")
]


def _provider() -> ExternalMultiplayerSessionProvider:
    if not EXTERNAL_MULTIPLAYER_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        return ExternalMultiplayerSessionProvider(
            EXTERNAL_MULTIPLAYER_URL,
            EXTERNAL_MULTIPLAYER_TOKEN,
            EXTERNAL_MULTIPLAYER_TIMEOUT,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="External multiplayer provider is not configured",
        ) from error


def _actor(request: Request) -> tuple[str, str]:
    return f"romm-{request.user.id}", request.user.username[:64]


def _provider_error(status_code: int, document: object) -> HTTPException:
    detail = "External multiplayer provider rejected the operation"
    if isinstance(document, dict):
        candidate = document.get("error") or document.get("detail")
        if isinstance(candidate, str) and candidate:
            detail = candidate[:512]
    if status_code < 400 or status_code > 599:
        status_code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(status_code=status_code, detail=detail)


async def _call_provider(
    method: str,
    path: str,
    *,
    actor: tuple[str, str] | None = None,
    body: dict[str, object] | None = None,
) -> tuple[int, object]:
    provider = _provider()
    try:
        return await asyncio.to_thread(
            provider.request,
            method,
            path,
            actor_id=actor[0] if actor else None,
            actor_name=actor[1] if actor else None,
            body=body,
        )
    except ExternalMultiplayerProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error


def _validated_session(document: object, actor_id: str) -> MultiplayerSessionSchema:
    try:
        provider_session = ProviderSession.model_validate(document)
    except ValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="External multiplayer provider returned an invalid session",
        ) from error
    active_participants = [
        participant
        for participant in provider_session.participants
        if participant.state not in {"LEFT", "ERROR"}
    ]
    return MultiplayerSessionSchema(
        session_id=provider_session.session_id,
        display_name=provider_session.display_name,
        romm_rom_id=provider_session.romm_rom_id,
        platform=provider_session.platform,
        max_players=provider_session.max_players,
        state=provider_session.state,
        participants=[
            MultiplayerParticipantSchema(
                participant_id=participant.participant_id,
                display_name=participant.display_name,
                player_slot=participant.player_slot,
                state=participant.state,
            )
            for participant in active_participants
        ],
        player_count=provider_session.player_count,
        expires_at=provider_session.expires_at,
        can_close=provider_session.owner_user_id == actor_id,
        is_participant=any(
            participant.user_id == actor_id for participant in active_participants
        ),
    )


def _visible_rom(request: Request, rom_id: int) -> Rom:
    rom = db_rom_handler.get_rom(rom_id)
    if not rom:
        raise RomNotFoundInDatabaseException(rom_id)
    assert_rom_visible(request, rom)
    return rom


def _game_path(rom: Rom) -> tuple[Path, str]:
    relative = PurePosixPath(rom.full_path)
    if (
        relative.is_absolute()
        or PureWindowsPath(rom.full_path).is_absolute()
        or ".." in relative.parts
    ):
        raise HTTPException(status_code=409, detail="ROM path is not supported")
    try:
        root = Path(LIBRARY_BASE_PATH).resolve(strict=True)
        path = root.joinpath(*relative.parts).resolve(strict=True)
    except OSError as error:
        raise HTTPException(
            status_code=409, detail="ROM file is unavailable"
        ) from error
    if not path.is_file() or not path.is_relative_to(root):
        raise HTTPException(status_code=409, detail="ROM path is not supported")
    return path, relative.as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _authenticate_provider(credential: ExternalMultiplayerToken = None) -> None:
    valid = (
        EXTERNAL_MULTIPLAYER_ENABLED
        and len(EXTERNAL_MULTIPLAYER_TOKEN) >= 32
        and compare_digest(credential or "", EXTERNAL_MULTIPLAYER_TOKEN)
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service credential",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/health")
def multiplayer_health(
    external_token: ExternalMultiplayerToken = None,
) -> dict[str, bool]:
    _authenticate_provider(external_token)
    return {"ready": True}


@router.get("/games/{rom_id}", response_model=MultiplayerGameSchema)
async def resolve_multiplayer_game(
    rom_id: int,
    external_token: ExternalMultiplayerToken = None,
) -> MultiplayerGameSchema:
    _authenticate_provider(external_token)
    rom = db_rom_handler.get_rom(rom_id)
    if not rom or rom.missing_from_fs or rom.is_physical:
        raise RomNotFoundInDatabaseException(rom_id)
    path, relative_path = _game_path(rom)
    return MultiplayerGameSchema(
        romm_rom_id=rom.id,
        platform=rom.platform_slug,
        relative_path=relative_path,
        rom_sha256=await asyncio.to_thread(_sha256, path),
    )


@protected_route(router.get, "/sessions", [Scope.ROMS_READ])
async def list_multiplayer_sessions(
    request: Request,
    romm_rom_id: Annotated[int | None, Query(ge=1)] = None,
) -> MultiplayerSessionListSchema:
    actor_id, _ = _actor(request)
    response_status, document = await _call_provider("GET", "/v1/sessions")
    if response_status != 200 or not isinstance(document, dict):
        raise _provider_error(response_status, document)
    items = document.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Invalid multiplayer session list")
    sessions = [_validated_session(item, actor_id) for item in items]
    if romm_rom_id is not None:
        sessions = [item for item in sessions if item.romm_rom_id == romm_rom_id]
    return MultiplayerSessionListSchema(items=sessions)


@protected_route(router.post, "/sessions", [Scope.ROMS_READ], status_code=201)
async def create_multiplayer_session(
    request: Request,
    payload: Annotated[CreateMultiplayerSessionRequest, Body()],
) -> MultiplayerSessionSchema:
    _visible_rom(request, payload.romm_rom_id)
    actor = _actor(request)
    response_status, document = await _call_provider(
        "POST",
        "/v1/sessions",
        actor=actor,
        body=payload.model_dump(),
    )
    if response_status != 201:
        raise _provider_error(response_status, document)
    return _validated_session(document, actor[0])


async def _session_action(
    request: Request, session_id: UUID, action: str
) -> MultiplayerSessionSchema:
    actor = _actor(request)
    response_status, document = await _call_provider(
        "POST", f"/v1/sessions/{session_id}/{action}", actor=actor
    )
    if response_status != 200:
        raise _provider_error(response_status, document)
    return _validated_session(document, actor[0])


@protected_route(router.post, "/sessions/{session_id}/join", [Scope.ROMS_READ])
async def join_multiplayer_session(
    request: Request, session_id: UUID
) -> MultiplayerSessionSchema:
    return await _session_action(request, session_id, "join")


@protected_route(router.post, "/sessions/{session_id}/leave", [Scope.ROMS_READ])
async def leave_multiplayer_session(
    request: Request, session_id: UUID
) -> MultiplayerSessionSchema:
    return await _session_action(request, session_id, "leave")


@protected_route(router.post, "/sessions/{session_id}/heartbeat", [Scope.ROMS_READ])
async def heartbeat_multiplayer_session(
    request: Request, session_id: UUID
) -> MultiplayerSessionSchema:
    return await _session_action(request, session_id, "heartbeat")


@protected_route(router.post, "/sessions/{session_id}/launch", [Scope.ROMS_READ])
async def launch_multiplayer_session(
    request: Request, session_id: UUID
) -> MultiplayerLaunchSchema:
    response_status, document = await _call_provider(
        "POST", f"/v1/sessions/{session_id}/launch", actor=_actor(request)
    )
    if response_status != 200:
        raise _provider_error(response_status, document)
    try:
        return MultiplayerLaunchSchema.model_validate(document)
    except ValidationError as error:
        raise HTTPException(
            status_code=502, detail="Invalid multiplayer launch"
        ) from error


@protected_route(router.delete, "/sessions/{session_id}", [Scope.ROMS_READ])
async def close_multiplayer_session(request: Request, session_id: UUID) -> Response:
    response_status, document = await _call_provider(
        "DELETE", f"/v1/sessions/{session_id}", actor=_actor(request)
    )
    if response_status != 204:
        raise _provider_error(response_status, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
