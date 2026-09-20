import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type {
  DetailedRomSchema,
  MultiplayerSessionSchema,
} from "@/__generated__";
import MultiplayerSessions from "./MultiplayerSessions.vue";

const mocks = vi.hoisted(() => ({
  close: vi.fn(),
  create: vi.fn(),
  heartbeat: vi.fn(),
  join: vi.fn(),
  launch: vi.fn(),
  leave: vi.fn(),
  list: vi.fn(),
  setPlaying: vi.fn(),
}));

vi.mock("vue-i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("@/services/api/multiplayer", () => ({
  default: {
    close: mocks.close,
    create: mocks.create,
    heartbeat: mocks.heartbeat,
    join: mocks.join,
    launch: mocks.launch,
    leave: mocks.leave,
    list: mocks.list,
  },
}));

vi.mock("@/stores/playing", () => ({
  default: () => ({ setPlaying: mocks.setPlaying }),
}));

vi.mock("@/v2/composables/useSnackbar", () => ({
  useSnackbar: () => ({ error: vi.fn() }),
}));

function rom(overrides: Partial<DetailedRomSchema> = {}): DetailedRomSchema {
  return { id: 7, name: "Super Tilt Bro", ...overrides } as DetailedRomSchema;
}

function session(
  overrides: Partial<MultiplayerSessionSchema> = {},
): MultiplayerSessionSchema {
  return {
    session_id: "11111111-1111-4111-8111-111111111111",
    display_name: "Saturday Night NES",
    romm_rom_id: 7,
    platform: "nes",
    max_players: 4,
    state: "OPEN",
    participants: [
      {
        participant_id: "22222222-2222-4222-8222-222222222222",
        display_name: "Daniel",
        player_slot: 1,
        state: "ACTIVE",
      },
    ],
    player_count: 1,
    expires_at: "2026-09-07T18:00:00Z",
    can_close: true,
    is_participant: true,
    ...overrides,
  };
}

const RBtn = {
  props: { loading: Boolean, disabled: Boolean },
  emits: ["click"],
  template:
    '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
};
const RCard = { template: "<section><slot /></section>" };
const RDialog = {
  name: "RDialog",
  props: { modelValue: Boolean, fullscreen: Boolean },
  emits: ["update:modelValue", "close"],
  template:
    '<section v-if="modelValue"><slot name="header" /><slot name="content" /><slot name="footer" /></section>',
};
const RForm = {
  methods: { resetValidation: vi.fn() },
  template: "<form @submit.prevent=\"$emit('submit')\"><slot /></form>",
};
const RSelect = {
  props: { modelValue: Number },
  emits: ["update:modelValue"],
  template:
    '<select :value="modelValue" @change="$emit(\'update:modelValue\', Number($event.target.value))"><option value="2">2</option><option value="4">4</option></select>',
};
const RTextField = {
  props: { modelValue: String },
  emits: ["update:modelValue"],
  template:
    '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
};

function mountComponent() {
  return mount(MultiplayerSessions, {
    props: { rom: rom() },
    global: {
      stubs: {
        RBtn,
        RCard,
        RDialog,
        RForm,
        RProgressCircular: { template: "<span />" },
        RSelect,
        RTextField,
      },
    },
  });
}

describe("MultiplayerSessions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue({ data: { items: [session()] } });
    mocks.create.mockResolvedValue({ data: session() });
    mocks.launch.mockResolvedValue({
      data: {
        stream_path: "/stream/22222222222242228222222222222222/",
        access_token: "participant-token",
        expires_at: "2026-09-07T18:00:00Z",
      },
    });
    mocks.leave.mockResolvedValue({
      data: session({ is_participant: false, player_count: 0 }),
    });
  });

  it("creates a named lobby with the selected capacity", async () => {
    const wrapper = mountComponent();
    await flushPromises();

    await wrapper
      .get('[data-testid="multiplayer-create-open"]')
      .trigger("click");
    await wrapper
      .get('[data-testid="multiplayer-name"]')
      .setValue("Four Player Night");
    await wrapper.get('[data-testid="multiplayer-players"]').setValue("4");
    await wrapper
      .get('[data-testid="multiplayer-create-form"]')
      .trigger("submit");
    await flushPromises();

    expect(mocks.create).toHaveBeenCalledWith({
      display_name: "Four Player Night",
      romm_rom_id: 7,
      max_players: 4,
    });
  });

  it("embeds the scoped stream without opening another window", async () => {
    const open = vi.spyOn(window, "open");
    const wrapper = mountComponent();
    await flushPromises();

    await wrapper
      .get('[data-testid="multiplayer-open-player"]')
      .trigger("click");
    await flushPromises();

    const frame = wrapper.get<HTMLIFrameElement>(
      '[data-testid="multiplayer-player-frame"]',
    );
    const playerDialog = wrapper
      .findAllComponents(RDialog)
      .find((dialog) => dialog.props("modelValue"));
    expect(playerDialog?.props("fullscreen")).toBe(true);
    expect(frame.attributes("src")).toBe(
      "http://localhost:3000/stream/22222222222242228222222222222222/?token=participant-token",
    );
    expect(frame.attributes("referrerpolicy")).toBe("no-referrer");
    expect(open).not.toHaveBeenCalled();
    expect(mocks.setPlaying).toHaveBeenCalledWith(true);
  });

  it("leaves the lobby and releases player input from the embedded view", async () => {
    const wrapper = mountComponent();
    await flushPromises();
    await wrapper
      .get('[data-testid="multiplayer-open-player"]')
      .trigger("click");
    await flushPromises();

    await wrapper
      .get('[data-testid="multiplayer-player-leave"]')
      .trigger("click");
    await flushPromises();

    expect(mocks.leave).toHaveBeenCalledWith(
      "11111111-1111-4111-8111-111111111111",
    );
    expect(
      wrapper.find('[data-testid="multiplayer-player-frame"]').exists(),
    ).toBe(false);
    expect(mocks.setPlaying).toHaveBeenLastCalledWith(false);
  });
});
