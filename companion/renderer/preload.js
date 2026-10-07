'use strict';
// The only door between the companion and its pages: read-only event feeds.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('companion', {
  onState: (callback) => ipcRenderer.on('state', (_event, state) => callback(state)),
  onStatus: (callback) => ipcRenderer.on('status', (_event, status) => callback(status)),
  onPregame: (callback) => ipcRenderer.on('pregame', (_event, pregame) => callback(pregame)),
});
