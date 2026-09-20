from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProviderParticipant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    participant_id: UUID
    user_id: str
    display_name: str
    player_slot: int
    state: str


class ProviderSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: UUID
    display_name: str
    owner_user_id: str
    romm_rom_id: int
    platform: str
    max_players: int
    state: str
    participants: list[ProviderParticipant]
    player_count: int
    expires_at: datetime


class MultiplayerParticipantSchema(BaseModel):
    participant_id: UUID
    display_name: str
    player_slot: int
    state: str


class MultiplayerSessionSchema(BaseModel):
    session_id: UUID
    display_name: str
    romm_rom_id: int
    platform: str
    max_players: int
    state: str
    participants: list[MultiplayerParticipantSchema]
    player_count: int
    expires_at: datetime
    can_close: bool
    is_participant: bool


class MultiplayerSessionListSchema(BaseModel):
    items: list[MultiplayerSessionSchema]


class CreateMultiplayerSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=64)
    romm_rom_id: int = Field(ge=1)
    max_players: int = Field(ge=2, le=16)


class MultiplayerLaunchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stream_path: str = Field(pattern=r"^/stream/[a-f0-9]{32}/$")
    access_token: str = Field(min_length=32, max_length=512)
    expires_at: datetime


class MultiplayerGameSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    romm_rom_id: int
    platform: str
    relative_path: str
    rom_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
