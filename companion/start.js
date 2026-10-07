'use strict';
// `npm start` entry point: loads .env (Overwolf dev credentials, optional port) and launches the companion under
// ow-electron with that environment, so the credentials are there from the moment the process starts.

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const envFile = path.join(__dirname, '.env');
if (fs.existsSync(envFile)) {
  process.loadEnvFile(envFile);
} else {
  console.warn('No .env file found. Copy .env.example to .env and fill in your Overwolf developer credentials.');
}
if (!process.env.OW_DEV_KEY && !(process.env.OW_CLI_EMAIL && process.env.OW_CLI_API_KEY)) {
  console.warn('OW_CLI_EMAIL and OW_CLI_API_KEY (or OW_DEV_KEY) are not set: game events will stay off.');
}

const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE; // set by some editor terminals; it would make Electron run as plain Node

const electron = require('@overwolf/ow-electron'); // path to the ow-electron binary
const child = spawn(electron, ['.'], { cwd: __dirname, env, stdio: 'inherit' });
child.on('close', (code) => process.exit(code ?? 1));
