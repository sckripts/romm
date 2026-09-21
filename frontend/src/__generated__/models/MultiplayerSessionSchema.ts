/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MultiplayerParticipantSchema } from './MultiplayerParticipantSchema';
export type MultiplayerSessionSchema = {
    session_id: string;
    display_name: string;
    romm_rom_id: number;
    platform: string;
    max_players: number;
    state: string;
    participants: Array<MultiplayerParticipantSchema>;
    player_count: number;
    expires_at: string;
    can_close: boolean;
    is_participant: boolean;
};
