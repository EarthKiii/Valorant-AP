'use strict';
// Companion app: loads Overwolf's game events package (GEP) and forwards every VALORANT game event as JSON
// over a local WebSocket to the Archipelago client, which does all the stat tracking. In return the client sends
// its progress, shown in a small window (set SHOW_WINDOW=false in .env to run headless). During agent select, an
// in-game overlay (Overwolf's overlay package) warns when you hover an agent that wouldn't count (optional:
// SHOW_OVERLAY=false turns it off).

if (process.env.ELECTRON_RUN_AS_NODE) {
  // Set by some editors' terminals (e.g. VS Code extension hosts); it makes Electron behave like plain Node.
  console.error('ELECTRON_RUN_AS_NODE is set, so the companion cannot start this way. Start it with "npm start".');
  process.exit(1);
}

const path = require('node:path');
const { app, BrowserWindow, screen } = require('electron');

const VALORANT = 21640;
const FEATURES = ['gep_internal', 'me', 'game_info', 'match_info', 'kill', 'death'];
const PORT = Number(process.env.VALORANT_AP_PORT || 43792);
const CLIENT_URL = `ws://127.0.0.1:${PORT}`;
const isOff = (value) => ['false', '0', 'no', 'off'].includes(String(value || '').toLowerCase());
const SHOW_WINDOW = !isOff(process.env.SHOW_WINDOW);
const SHOW_OVERLAY = !isOff(process.env.SHOW_OVERLAY); // the in-game agent-select overlay
const OVERLAY_TOP = Math.min(90, Math.max(0, Number(process.env.OVERLAY_TOP) || 12)); // % down the game window
const OVERLAY_SIZE = { width: 640, height: 90 };
const MAX_QUEUED = 5000;
const RETRY_MS = 3000;

let gep = null;
let socket = null;
let progressWindow = null;
let overlayContent = 'null'; // the agent-select state the overlay shows, as JSON
let waitingLogged = false;
let latestState = null;
const status = { client: false, game: false, live: false };
const queue = [];

function log(...args) {
  console.log(new Date().toTimeString().slice(0, 8), ...args);
}

// --- progress window -----------------------------------------------------------------------------------------

function showInWindow(channel, payload) {
  if (progressWindow && !progressWindow.isDestroyed()) progressWindow.webContents.send(channel, payload);
}

function setStatus(change) {
  Object.assign(status, change);
  showInWindow('status', status);
  updateOverlay();
}

function createWindow() {
  progressWindow = new BrowserWindow({
    width: 480,
    height: 820,
    minWidth: 340,
    minHeight: 300,
    title: 'VALORANT Archipelago',
    backgroundColor: '#0f1923',
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'renderer', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  progressWindow.removeMenu();
  progressWindow.once('ready-to-show', () => progressWindow.show());
  progressWindow.webContents.on('did-finish-load', () => {
    showInWindow('status', status);
    if (latestState) showInWindow('state', latestState);
  });
  progressWindow.on('closed', () => app.quit()); // closing the window stops the companion
  progressWindow.loadFile(path.join(__dirname, 'renderer', 'window.html'));
}

// --- agent-select overlay ------------------------------------------------------------------------------------
// Drawn inside the game by Overwolf's overlay package, so it shows even in exclusive Fullscreen. Optional
// (SHOW_OVERLAY=false keeps the package from attaching to the game at all). The window only exists during agent
// select: created when it starts and destroyed when it ends.

let overlayApi = null;
let gameInjected = false; // the overlay package is attached to VALORANT
let overlay = null; // the open overlay window; { window: null } while it's being created

async function openOverlay() {
  const entry = { window: null };
  overlay = entry;
  try {
    // In-game windows are placed in the game window's own pixels.
    const display = screen.getPrimaryDisplay();
    const game = (overlayApi.getActiveGameInfo() || {}).gameWindowInfo;
    const area = (game && game.size) || {
      width: display.bounds.width * display.scaleFactor,
      height: display.bounds.height * display.scaleFactor,
    };
    const created = await overlayApi.createWindow({
      name: 'agent-select',
      ...OVERLAY_SIZE,
      x: Math.round((area.width - OVERLAY_SIZE.width) / 2),
      y: Math.round((area.height * OVERLAY_TOP) / 100),
      transparent: true,
      frame: false,
      resizable: false,
      movable: false,
      focusable: false,
      show: true,
      passthrough: 'passThrough', // mouse and keyboard go straight to the game
      ignoreKeyboardInput: true,
      zOrder: 'topMost',
      strictToGameWindow: true,
      webPreferences: {
        preload: path.join(__dirname, 'renderer', 'preload.js'),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
      },
    });
    const { window } = created;
    if (overlay !== entry) {
      window.destroy(); // agent select ended while it was being created
      return;
    }
    entry.window = window;
    window.webContents.on('did-finish-load', () => window.webContents.send('pregame', JSON.parse(overlayContent)));
    window.loadFile(path.join(__dirname, 'renderer', 'overlay.html'));
  } catch (error) {
    log(`Couldn't create the in-game overlay: ${(error && error.message) || error}`);
    if (overlay === entry) overlay = null;
  }
}

function closeOverlay() {
  if (!overlay) return;
  const { window } = overlay;
  overlay = null;
  if (window && !window.isDestroyed()) window.destroy();
}

function updateOverlay() {
  if (!app.isReady()) return;
  const pregame = (SHOW_OVERLAY && gameInjected && status.client && latestState && latestState.pregame) || null;
  if (!pregame) {
    overlayContent = 'null';
    closeOverlay();
    return;
  }
  const content = JSON.stringify(pregame);
  if (content === overlayContent && overlay) return;
  overlayContent = content;
  if (!overlay) {
    openOverlay(); // sends the content once loaded
  } else if (overlay.window && !overlay.window.webContents.isLoading()) {
    overlay.window.webContents.send('pregame', pregame);
  } // otherwise the page gets the latest content once it has loaded
}

function isValorant(gameInfo) {
  return Boolean(gameInfo) && (gameInfo.classId === VALORANT || gameInfo.id === VALORANT);
}

function setUpOverlayPackage() {
  overlayApi = app.overwolf.packages.overlay;
  overlayApi.on('game-launched', (event, gameInfo) => {
    if (!SHOW_OVERLAY || !isValorant(gameInfo) || gameInfo.type !== 'Game') {
      event.dismiss();
      return;
    }
    if (gameInfo.processInfo && gameInfo.processInfo.isElevated) {
      log('VALORANT is running as administrator, so the in-game overlay stays off.');
      event.dismiss();
      return;
    }
    event.inject();
  });
  overlayApi.on('game-injected', (gameInfo) => {
    if (!isValorant(gameInfo)) return;
    gameInjected = true;
    log('In-game overlay attached to VALORANT: agent-select warnings show inside the game.');
    updateOverlay();
  });
  overlayApi.on('game-injection-error', (gameInfo, error) => {
    if (isValorant(gameInfo)) log(`In-game overlay unavailable: ${error}`);
  });
  overlayApi.on('game-exit', (gameInfo) => {
    if (!isValorant(gameInfo)) return;
    gameInjected = false;
    updateOverlay();
  });
  overlayApi.on('error', (...args) => log('In-game overlay error:', ...args));
  overlayApi.registerGames({ gamesIds: [VALORANT] });
  if (status.game) requestInjection();
}

function requestInjection() {
  // For when VALORANT was already running before the overlay package got ready: ask for a late injection (the
  // 'game-launched' handler above still decides). Does nothing if it's already attached.
  if (!SHOW_OVERLAY || !overlayApi || gameInjected) return;
  overlayApi.requestGameInjection(VALORANT).catch(() => {});
}

// --- connection to the Archipelago client --------------------------------------------------------------------

function send(message) {
  const data = JSON.stringify({ ts: Date.now(), ...message });
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(data);
    return;
  }
  // Keep events while the client is away so a match in progress isn't lost.
  queue.push(data);
  if (queue.length > MAX_QUEUED) queue.shift();
}

async function sendSnapshot() {
  if (!gep || !socket || socket.readyState !== WebSocket.OPEN) return;
  try {
    const info = await gep.getInfo(VALORANT);
    if (info) socket.send(JSON.stringify({ ts: Date.now(), kind: 'snapshot', value: info }));
  } catch {
    // VALORANT isn't running; nothing to sync.
  }
}

function onClientMessage(event) {
  let message;
  try {
    message = JSON.parse(event.data);
  } catch {
    return;
  }
  if (message && message.kind === 'state') {
    latestState = message;
    showInWindow('state', message);
    updateOverlay();
  }
}

function connect() {
  socket = new WebSocket(CLIENT_URL);
  socket.addEventListener('open', () => {
    waitingLogged = false;
    log(`Connected to the Archipelago VALORANT client (port ${PORT}).`);
    setStatus({ client: true });
    while (queue.length) socket.send(queue.shift());
    sendSnapshot();
  });
  socket.addEventListener('message', onClientMessage);
  socket.addEventListener('close', () => {
    if (!waitingLogged) {
      log(`Waiting for the Archipelago VALORANT client on port ${PORT}...`);
      waitingLogged = true;
    }
    socket = null;
    setStatus({ client: false });
    setTimeout(connect, RETRY_MS);
  });
  socket.addEventListener('error', () => {}); // a 'close' always follows and schedules the retry
}

// --- game events ---------------------------------------------------------------------------------------------

async function requireFeatures() {
  for (let attempt = 0; attempt < 40; attempt++) {
    try {
      await gep.setRequiredFeatures(VALORANT, FEATURES);
      log('Receiving VALORANT game events.');
      setStatus({ live: true });
      return;
    } catch (error) {
      await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
    }
  }
  log('VALORANT game events never became available. Restart the companion after the game has fully loaded.');
}

function setUpGep() {
  gep = app.overwolf.packages.gep;
  gep.on('game-detected', (event, gameId) => {
    if (gameId !== VALORANT) return;
    log('VALORANT detected.');
    setStatus({ game: true });
    event.enable();
    requireFeatures();
    setTimeout(requestInjection, RETRY_MS); // in case the overlay package missed the launch
  });
  gep.on('new-info-update', (_event, gameId, data) => {
    if (gameId !== VALORANT) return;
    send({ kind: 'info', feature: data.feature, category: data.category, key: data.key, value: data.value });
  });
  gep.on('new-game-event', (_event, gameId, data) => {
    if (gameId !== VALORANT) return;
    send({ kind: 'event', feature: data.feature, key: data.key, value: data.value });
  });
  gep.on('game-exit', (_event, gameId) => {
    if (gameId !== VALORANT) return;
    log('VALORANT closed.');
    setStatus({ game: false, live: false });
    send({ kind: 'game_exit' });
  });
  gep.on('elevated-privileges-required', (_event, gameId) => {
    if (gameId === VALORANT) log('VALORANT is running as administrator: run this companion as administrator too.');
  });
  gep.on('error', (_event, gameId, error) => {
    if (gameId === VALORANT) log(`Game events error: ${error}`);
  });
}

if (!app.overwolf) {
  console.error('Start the companion with "npm start" (ow-electron), not plain Electron.');
  app.exit(1);
} else if (!app.requestSingleInstanceLock()) {
  console.error('The companion app is already running.');
  app.exit(0);
} else {
  app.disableHardwareAcceleration(); // a static progress page doesn't need the GPU
  app.overwolf.disableAnonymousAnalytics?.();
  app.overwolf.disableAdsOptimization?.();
  app.overwolf.packages.on('ready', (_event, name, version) => {
    if (name === 'gep') {
      log(`Game events package ready (v${version}).`);
      setUpGep();
    } else if (name === 'overlay') {
      log(`Overlay package ready (v${version}).`);
      setUpOverlayPackage();
    }
  });
  app.on('second-instance', () => progressWindow?.focus());
  app.on('window-all-closed', () => {}); // headless mode has no windows; keep running
  if (SHOW_WINDOW) app.whenReady().then(createWindow);
  connect();
}
