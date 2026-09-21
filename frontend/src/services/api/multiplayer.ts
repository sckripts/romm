import type {
  CreateMultiplayerSessionRequest,
  MultiplayerLaunchSchema,
  MultiplayerSessionListSchema,
  MultiplayerSessionSchema,
} from "@/__generated__";
import api from "@/services/api";

export default {
  list(rommRomId: number) {
    return api.get<MultiplayerSessionListSchema>("/multiplayer/sessions", {
      params: { romm_rom_id: rommRomId },
    });
  },
  create(payload: CreateMultiplayerSessionRequest) {
    return api.post<MultiplayerSessionSchema>("/multiplayer/sessions", payload);
  },
  join(sessionId: string) {
    return api.post<MultiplayerSessionSchema>(
      `/multiplayer/sessions/${sessionId}/join`,
    );
  },
  leave(sessionId: string) {
    return api.post<MultiplayerSessionSchema>(
      `/multiplayer/sessions/${sessionId}/leave`,
    );
  },
  heartbeat(sessionId: string) {
    return api.post<MultiplayerSessionSchema>(
      `/multiplayer/sessions/${sessionId}/heartbeat`,
    );
  },
  launch(sessionId: string) {
    return api.post<MultiplayerLaunchSchema>(
      `/multiplayer/sessions/${sessionId}/launch`,
    );
  },
  close(sessionId: string) {
    return api.delete(`/multiplayer/sessions/${sessionId}`);
  },
};
