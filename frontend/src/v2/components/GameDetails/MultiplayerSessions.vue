<script setup lang="ts">
import { RBtn, RCard, RForm, RTextField } from "@v2/lib";
import axios from "axios";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type {
  DetailedRomSchema,
  MultiplayerSessionSchema,
} from "@/__generated__";
import multiplayerApi from "@/services/api/multiplayer";
import { useSnackbar } from "@/v2/composables/useSnackbar";

const props = defineProps<{ rom: DetailedRomSchema }>();
const { t } = useI18n();
const snackbar = useSnackbar();
const enabled = ref(false);
const loading = ref(false);
const action = ref<string | null>(null);
const sessions = ref<MultiplayerSessionSchema[]>([]);
const sessionName = ref("");
const createForm = ref<InstanceType<typeof RForm> | null>(null);
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
  await run("create", async () => {
    await multiplayerApi.create({
      display_name: displayName,
      romm_rom_id: props.rom.id,
      max_players: 2,
    });
    sessionName.value = "";
    await nextTick();
    createForm.value?.resetValidation();
  });
}

async function openPlayer(session: MultiplayerSessionSchema) {
  const player = window.open("about:blank", "_blank");
  if (!player) {
    snackbar.error(t("multiplayer.popup-blocked"));
    return;
  }
  action.value = session.session_id;
  try {
    const { data } = await multiplayerApi.launch(session.session_id);
    const destination = new URL(data.stream_path, window.location.origin);
    destination.searchParams.set("token", data.access_token);
    player.location.replace(destination);
  } catch (error) {
    player.close();
    showError(error);
  } finally {
    action.value = null;
  }
}

watch(
  () => props.rom.id,
  () => void load(),
);
onMounted(() => {
  void load();
  pollTimer = window.setInterval(() => void poll(), 10_000);
});
onBeforeUnmount(() => window.clearInterval(pollTimer));
</script>

<template>
  <RCard v-if="enabled" :loading="loading" class="multiplayer">
    <div class="multiplayer__header">
      <h2>{{ t("multiplayer.sessions") }}</h2>
      <RForm
        ref="createForm"
        class="multiplayer__create"
        @submit="createSession"
      >
        <RTextField
          v-model="sessionName"
          :label="t('multiplayer.session-name')"
          :rules="[
            (value: string) => Boolean(value.trim()) || t('common.required'),
          ]"
          :disabled="action !== null"
          density="compact"
          required
          hide-details="auto"
        />
        <RBtn
          type="submit"
          size="small"
          color="primary"
          :loading="action === 'create'"
          :disabled="action !== null || !sessionName.trim()"
        >
          {{ t("multiplayer.create-session") }}
        </RBtn>
      </RForm>
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
            @click="
              run(session.session_id, () =>
                multiplayerApi.join(session.session_id),
              )
            "
          >
            {{ t("multiplayer.join") }}
          </RBtn>
          <RBtn
            v-if="session.is_participant"
            size="small"
            color="primary"
            :loading="action === session.session_id"
            :disabled="action !== null"
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
  </RCard>
</template>

<style scoped>
.multiplayer {
  margin-top: 16px;
  padding: 14px 16px;
}
.multiplayer__header,
.multiplayer__create,
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
.multiplayer__create {
  min-width: min(440px, 60%);
}
.multiplayer__create > :first-child {
  flex: 1;
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
.multiplayer__list span,
.multiplayer__empty {
  color: var(--r-color-fg-secondary);
  font-size: 12px;
}
.multiplayer__empty {
  margin: 12px 0 0;
}
html[data-bp~="sm-and-down"] .multiplayer__header,
html[data-bp~="sm-and-down"] .multiplayer__list li {
  align-items: stretch;
  flex-direction: column;
}
html[data-bp~="sm-and-down"] .multiplayer__create {
  min-width: 0;
  width: 100%;
}
html[data-bp~="sm-and-down"] .multiplayer__actions {
  flex-wrap: wrap;
}
</style>
