// Switching the recorder in the panel, against two fake recorders (issue #2).
//
// Runs the panel's own module in jsdom and prints, as JSON, what each scenario
// saw on screen and what the panel asked Home Assistant for. The assertions are
// in tests/test_panel_recorder_switch.py.
import { JSDOM } from "jsdom";

const PANEL = process.argv[2];

const dom = new JSDOM("<!doctype html><body></body>", {
  url: "http://ha.test:8123/xmeye",
  pretendToBeVisual: true,
});
const { window } = dom;
for (const key of Object.getOwnPropertyNames(window)) {
  if (key in globalThis) continue;
  try {
    globalThis[key] = window[key];
  } catch {
    /* read-only in node */
  }
}
globalThis.window = window;
globalThis.document = window.document;
globalThis.localStorage = window.localStorage;
globalThis.location = window.location;
// The wall needs WebCodecs to start at all; nothing is decoded here.
globalThis.VideoDecoder = class {};
window.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: () => () => {} });

/** Every video socket the panel opens, with the recorder it is signed for. */
const sockets = [];
class FakeSocket extends window.EventTarget {
  static OPEN = 1;
  constructor(url) {
    super();
    this.url = url;
    this.recorder = url.match(/\/ws\/(\w+)/)[1];
    this.readyState = 0;
    sockets.push(this);
  }
  send() {}
  close() {
    this.readyState = 3;
  }
}
globalThis.WebSocket = FakeSocket;

const RECORDERS = {
  A: { model: "Model A", name: "NVR-A", channels: ["A-front", "A-yard", "A-gate", "A-garage"] },
  B: { model: "Model B", name: "NVR-B", channels: ["B-door", "B-hall"] },
};

function detail(id) {
  const recorder = RECORDERS[id];
  return {
    entry_id: id,
    title: `Recorder ${id}`,
    host: `192.0.2.${id === "A" ? 1 : 2}`,
    device: { model: recorder.model, firmware: "V4", channels: recorder.channels.length },
    channels: recorder.channels.map((name, index) => ({
      index, name, entity_id: `camera.${name}`, entity_ids: {}, status: "Connected",
      online: true, enabled: true, bitrate: 0, recording: false, motion: false, video_loss: false,
    })),
    storage: [],
    archive: { from: null, to: null },
    capabilities: {},
    totals: { bitrate: 0, recording: 0 },
    options: { default_player: "native" },
  };
}

/** A Home Assistant that answers for both recorders and notes every call. */
function fakeHass() {
  const hass = {
    language: "en",
    user: { is_admin: true },
    auth: { accessToken: "token", expired: false },
    calls: [],
    // Set to hold back the next detail of a recorder, for a reply that is late.
    hold: null,
    async callWS(msg) {
      hass.calls.push(msg);
      switch (msg.type) {
        case "xmeye/devices":
          return { devices: ["A", "B"].map((id) => ({ entry_id: id, title: `Recorder ${id}` })) };
        case "xmeye/device":
          if (hass.hold && hass.hold.entry === msg.entry_id) {
            const held = hass.hold;
            hass.hold = null;
            await held.released;
          }
          return detail(msg.entry_id);
        case "xmeye/stream_url":
          return { path: `/api/xmeye/ws/${msg.entry_id}?authSig=signed` };
        case "xmeye/config":
          return { value: { MachineName: RECORDERS[msg.entry_id].name, AutoLogout: 10 } };
        case "xmeye/config_set":
          return { value: msg.value, restart: false };
        case "xmeye/recordings":
          return { recordings: [] };
        default:
          return {};
      }
    },
  };
  return hass;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 100));

async function mount() {
  sockets.length = 0;
  document.body.innerHTML = "";
  const hass = fakeHass();
  const panel = document.createElement("xmeye-panel");
  document.body.append(panel);
  panel.hass = hass;
  await settle();
  const root = panel.shadowRoot;
  return {
    panel,
    hass,
    tiles: () =>
      [...root.querySelectorAll(".cell[data-channel] .cell-name")].map((el) => el.textContent.trim()),
    title: () => root.querySelector("h1").textContent,
    wall: () => (panel._wallReader && panel._wallReader.socket ? panel._wallReader.socket.recorder : null),
    pick: async (id) => {
      const select = root.getElementById("device");
      select.value = id;
      select.dispatchEvent(new window.Event("change"));
      await settle();
    },
    openSettings: async (page) => {
      root.querySelector('[data-tab="settings"]').click();
      await settle();
      panel._settingsGroup = page;
      await panel._loadSettings();
    },
  };
}

await import(PANEL);
const result = {};

{
  const view = await mount();
  const before = { tiles: view.tiles(), wall: view.wall() };
  await view.pick("B");
  result.wall = {
    before,
    after: { title: view.title(), tiles: view.tiles(), wall: view.wall() },
    sockets: sockets.map((s) => ({ recorder: s.recorder, closed: s.readyState === 3 })),
  };
}

{
  const view = await mount();
  await view.openSettings("general");
  const before = view.panel._settings.value.MachineName;
  await view.pick("B");
  const after = view.panel._settings && view.panel._settings.value && view.panel._settings.value.MachineName;
  view.panel._settingsEdits = { AutoLogout: 20 };
  await view.panel._saveSettings();
  const write = view.hass.calls.filter((c) => c.type === "xmeye/config_set").pop();
  result.settings = {
    before,
    after,
    write: write ? { recorder: write.entry_id, MachineName: write.value.MachineName, AutoLogout: write.value.AutoLogout } : null,
  };
}

{
  const view = await mount();
  await view.openSettings("general");
  view.panel._settingsEdits = { AutoLogout: 20 };
  window.confirm = () => false;
  await view.pick("B");
  window.confirm = () => true;
  result.unsaved = {
    recorder: view.panel._entryId,
    picker: view.panel.shadowRoot.getElementById("device").value,
    edits: view.panel._settingsEdits,
    title: view.title(),
  };
}

{
  // A poll of recorder A sent just before the switch, answered just after it.
  const view = await mount();
  let release;
  view.hass.hold = { entry: "A", released: new Promise((resolve) => (release = resolve)) };
  const poll = view.panel._refresh();
  await view.pick("B");
  release();
  await poll;
  await settle();
  result.latePoll = {
    title: view.title(),
    tiles: view.tiles(),
    wall: view.wall(),
    detail: view.panel._detail.entry_id,
  };
}

{
  const view = await mount();
  view.panel.shadowRoot.querySelector('[data-tab="archive"]').click();
  await settle();
  await view.pick("B");
  const asked = view.hass.calls.filter((c) => c.type === "xmeye/recordings").map((c) => c.entry_id);
  result.archive = { asked };
}

console.log(JSON.stringify(result));
process.exit(0);
