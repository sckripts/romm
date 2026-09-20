<script setup lang="ts">
import {
  RBtn,
  RCard,
  RDialog,
  RForm,
  RProgressCircular,
  RSelect,
  RTextField,
} from "@v2/lib";
import axios from "axios";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type {
  DetailedRomSchema,
  MultiplayerSessionSchema,
} from "@/__generated__";
import multiplayerApi from "@/services/api/multiplayer";
import storePlaying from "@/stores/playing";
import { useSnackbar } from "@/v2/composables/useSnackbar";

const props = defineProps<{ rom: DetailedRomSchema }>();
const { t } = useI18n();
const snackbar = useSnackbar();
const playingStore = storePlaying();
const enabled = ref(false);
const loading = ref(false);
const action = ref<string | null>(null);
const sessions = ref<MultiplayerSessionSchema[]>([]);
const sessionName = ref("");
const maxPlayers = ref(2);
const showCreate = ref(false);
const createForm = ref<InstanceType<typeof RForm> | null>(null);
const playerSession = ref<MultiplayerSessionSchema | null>(null);
const playerSrc = ref("");
const playerLoaded = ref(false);
const playerShell = ref<HTMLElement | null>(null);
const isFullscreen = ref(false);
const playerOptions = [
  { title: "2", value: 2 },
  { title: "3", value: 3 },
  { title: "4", value: 4 },
];
let pollTimer: number | undefined;

function showError(error: unknown) {
  const detail = axios.isAxiosError(error)
    ? error.response?.data?.detail
    : null;
  snackbar.error(
    typeof detail === "string" ? detail : t("multiplayer.action-failed"),
  );
}

async function load({ quiet = false } = {}) {
  if (!quiet) loading.value = true;
  try {
    const { data } = await multiplayerApi.list(props.rom.id);
    enabled.value = true;
    sessions.value = data.items;
    if (
      playerSession.value &&
      !data.items.some(
        (session) => session.session_id === playerSession.value?.session_id,
      )
    ) {
      closePlayer();
    }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      enabled.value = false;
      sessions.value = [];
    } else if (!quiet) {
      showError(error);
    }
  } finally {
    if (!quiet) loading.value = false;
  }
}

async function poll() {
  const active = sessions.value.filter((session) => session.is_participant);
  await Promise.allSettled(
    active.map((session) => multiplayerApi.heartbeat(session.session_id)),
  );
  await load({ quiet: true });
}

async function run(sessionId: string, operation: () => Promise<unknown>) {
  action.value = sessionId;
  try {
    await operation();
    await load({ quiet: true });
  } catch (error) {
    showError(error);
  } finally {
    action.value = null;
  }
}

async function createSession() {
  const displayName = sessionName.value.trim();
  if (!displayName) return;
  action.value = "create";
  try {
    const { data } = await multiplayerApi.create({
      display_name: displayName,
      romm_rom_id: props.rom.id,
      max_players: maxPlayers.value,
    });
    sessionName.value = "";
    maxPlayers.value = 2;
    showCreate.value = false;
    await nextTick();
    createForm.value?.resetValidation();
    await load({ quiet: true });
    await openPlayer(data);
  } catch (error) {
    showError(error);
  } finally {
    action.value = null;
  }
}

async function openPlayer(session: MultiplayerSessionSchema) {
  playerSession.value = session;
  playerSrc.value = "";
  playerLoaded.value = false;
  playingStore.setPlaying(true);
  action.value = session.session_id;
  try {
    const { data } = await multiplayerApi.launch(session.session_id);
    const destination = new URL(data.stream_path, window.location.origin);
    destination.searchParams.set("token", data.access_token);
    playerSrc.value = destination.toString();
  } catch (error) {
    closePlayer();
    showError(error);
  } finally {
    action.value = null;
  }
}

async function joinSession(session: MultiplayerSessionSchema) {
  action.value = session.session_id;
  try {
    const { data } = await multiplayerApi.join(session.session_id);
    await load({ quiet: true });
    await openPlayer(data);
  } catch (error) {
    showError(error);
  } finally {
    action.value = null;
  }
}

function closePlayer() {
  if (document.fullscreenElement === playerShell.value) {
    void document.exitFullscreen();
  }
  playerSession.value = null;
  playerSrc.value = "";
  playerLoaded.value = false;
  playingStore.setPlaying(false);
}

async function leavePlayer() {
  const sessionId = playerSession.value?.session_id;
  if (!sessionId) return;
  action.value = sessionId;
  try {
    await multiplayerApi.leave(sessionId);
    closePlayer();
    await load({ quiet: true });
  } catch (error) {
    showError(error);
  } finally {
    action.value = null;
  }
}

async function toggleFullscreen() {
  if (!playerShell.value) return;
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await playerShell.value.requestFullscreen();
    }
  } catch {
    return;
  }
}

function onFullscreenChange() {
  isFullscreen.value = document.fullscreenElement === playerShell.value;
}

watch(
  () => props.rom.id,
  () => {
    closePlayer();
    void load();
  },
);
onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => void poll(), 10_000);
  document.addEventListener("fullscreenchange", onFullscreenChange);
});
onBeforeUnmount(() => {
  window.clearInterval(pollTimer);
  document.removeEventListener("fullscreenchange", onFullscreenChange);
  playingStore.setPlaying(false);
});
</script>

<template>
  <RCard v-if="enabled" :loading="loading" class="multiplayer">
    <div class="multiplayer__header">
      <h2>{{ t("multiplayer.sessions") }}</h2>
      <RBtn
        data-testid="multiplayer-create-open"
        size="small"
        color="primary"
        prepend-icon="mdi-plus"
        :disabled="action !== null"
        @click="showCreate = true"
      >
        {{ t("multiplayer.create-session") }}
      </RBtn>
    </div>

    <p v-if="sessions.length === 0" class="multiplayer__empty">
      {{ t("multiplayer.no-open-sessions") }}
    </p>
    <ul v-else class="multiplayer__list">
      <li v-for="session in sessions" :key="session.session_id">
        <div>
          <strong>{{ session.display_name }}</strong>
          <span>
            {{
              t("multiplayer.player-count", {
                current: session.player_count,
                max: session.max_players,
              })
            }}
          </span>
          <span class="multiplayer__participants">
            {{
              session.participants
                .slice()
                .sort((left, right) => left.player_slot - right.player_slot)
                .map((participant) => participant.display_name)
                .join(", ")
            }}
          </span>
        </div>
        <div class="multiplayer__actions">
          <RBtn
            v-if="!session.is_participant"
            size="small"
            variant="outlined"
            :loading="action === session.session_id"
            :disabled="
              action !== null || session.player_count >= session.max_players
            "
            @click="joinSession(session)"
          >
            {{ t("multiplayer.join") }}
          </RBtn>
          <RBtn
            v-if="session.is_participant"
            size="small"
            color="primary"
            :loading="action === session.session_id"
            :disabled="action !== null"
            data-testid="multiplayer-open-player"
            @click="openPlayer(session)"
          >
            {{ t("multiplayer.open-player") }}
          </RBtn>
          <RBtn
            v-if="session.is_participant"
            size="small"
            variant="text"
            :disabled="action !== null"
            @click="
              run(session.session_id, () =>
                multiplayerApi.leave(session.session_id),
              )
            "
          >
            {{ t("multiplayer.leave") }}
          </RBtn>
          <RBtn
            v-if="session.can_close"
            size="small"
            color="danger"
            variant="text"
            :disabled="action !== null"
            @click="
              run(session.session_id, () =>
                multiplayerApi.close(session.session_id),
              )
            "
          >
            {{ t("common.close") }}
          </RBtn>
        </div>
      </li>
    </ul>

    <RDialog v-model="showCreate" :width="480" icon="mdi-account-multiple-plus">
      <template #header>
        <strong>{{ t("multiplayer.create-session") }}</strong>
      </template>
      <template #content>
        <RForm
          ref="createForm"
          data-testid="multiplayer-create-form"
          class="multiplayer__create-form"
          @submit="createSession"
        >
          <RTextField
            v-model="sessionName"
            data-testid="multiplayer-name"
            :label="t('multiplayer.session-name')"
            :rules="[
              (value: string) => Boolean(value.trim()) || t('common.required'),
            ]"
            :disabled="action !== null"
            required
            hide-details="auto"
          />
          <RSelect
            v-model="maxPlayers"
            data-testid="multiplayer-players"
            :items="playerOptions"
            :label="t('multiplayer.players')"
            :disabled="action !== null"
            hide-details
          />
        </RForm>
      </template>
      <template #footer>
        <RBtn
          variant="text"
          :disabled="action !== null"
          @click="showCreate = false"
        >
          {{ t("common.cancel") }}
        </RBtn>
        <RBtn
          color="primary"
          :loading="action === 'create'"
          :disabled="action !== null || !sessionName.trim()"
          @click="createSession"
        >
          {{ t("common.create") }}
        </RBtn>
      </template>
    </RDialog>

    <RDialog
      :model-value="playerSession !== null"
      class="multiplayer-player"
      fullscreen
      @update:model-value="(open) => !open && closePlayer()"
      @close="closePlayer"
    >
      <template #header>
        <div class="multiplayer-player__heading">
          <strong>{{ playerSession?.display_name }}</strong>
          <span>{{ props.rom.name }}</span>
        </div>
      </template>
      <template #content>
        <div ref="playerShell" class="multiplayer-player__shell">
          <div
            v-if="!playerSrc || !playerLoaded"
            class="multiplayer-player__loading"
          >
            <RProgressCircular indeterminate />
            <span>{{ t("common.loading") }}</span>
          </div>
          <iframe
            v-if="playerSrc"
            data-testid="multiplayer-player-frame"
            class="multiplayer-player__frame"
            :src="playerSrc"
            allow="gamepad *; fullscreen *; autoplay *"
            allowfullscreen
            referrerpolicy="no-referrer"
            :title="`${playerSession?.display_name}: ${props.rom.name}`"
            @load="playerLoaded = true"
          />
        </div>
      </template>
      <template #footer>
        <span class="multiplayer-player__status">
          {{ playerLoaded ? t("common.online") : t("common.loading") }}
        </span>
        <span>{{ t("multiplayer.controller", { number: 1 }) }}</span>
        <span class="multiplayer-player__spacer" />
        <RBtn
          variant="text"
          :prepend-icon="
            isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'
          "
          @click="toggleFullscreen"
        >
          {{
            isFullscreen
              ? t("play.stream-exit-fullscreen")
              : t("play.stream-fullscreen")
          }}
        </RBtn>
        <RBtn
          data-testid="multiplayer-player-leave"
          color="danger"
          variant="text"
          :loading="action === playerSession?.session_id"
          @click="leavePlayer"
        >
          {{ t("multiplayer.leave") }}
        </RBtn>
      </template>
    </RDialog>
  </RCard>
</template>

<style scoped>
.multiplayer {
  margin-top: 16px;
  padding: 14px 16px;
}
.multiplayer__header,
.multiplayer__list li,
.multiplayer__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.multiplayer__header,
.multiplayer__list li {
  justify-content: space-between;
}
.multiplayer__header h2 {
  font-size: 15px;
}
.multiplayer__list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
  padding: 0;
  list-style: none;
}
.multiplayer__list li > div:first-child {
  display: grid;
  gap: 2px;
}
.multiplayer__participants {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.multiplayer__list span,
.multiplayer__empty {
  color: var(--r-color-fg-secondary);
  font-size: 12px;
}
.multiplayer__empty {
  margin: 12px 0 0;
}
.multiplayer__create-form {
  display: grid;
  gap: 16px;
}
.multiplayer-player__heading {
  display: grid;
  gap: 2px;
}
.multiplayer-player__heading span {
  color: var(--r-color-fg-secondary);
  font-size: 12px;
}
.multiplayer-player__shell {
  position: relative;
  display: grid;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--r-color-canvas-bg);
}
.multiplayer-player__frame,
.multiplayer-player__loading {
  grid-area: 1 / 1;
  width: 100%;
  height: 100%;
}
.multiplayer-player__frame {
  border: 0;
}
.multiplayer-player__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--r-color-fg-secondary);
}
.multiplayer-player__status {
  color: var(--r-color-success);
}
.multiplayer-player__spacer {
  flex: 1;
}
:deep(.multiplayer-player .r-dialog__body) {
  flex: 1;
  min-height: 0;
  padding: 0;
}
:deep(.multiplayer-player .r-dialog__footer) {
  flex-wrap: wrap;
}
html[data-bp~="sm-and-down"] .multiplayer__header,
html[data-bp~="sm-and-down"] .multiplayer__list li {
  align-items: stretch;
  flex-direction: column;
}
html[data-bp~="sm-and-down"] .multiplayer__actions {
  flex-wrap: wrap;
}
</style>
