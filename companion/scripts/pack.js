'use strict';
// `npm run pack`: builds a self-contained, ready-to-run copy of the companion in dist/VALORANT Companion/.
//
// It deliberately stays an *unpackaged* Electron app (runtime + app folder, started as `electron.exe app`):
// Overwolf only activates dev mode, and so live game events, for unpackaged apps.

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'dist', 'VALORANT Companion');
const APP_FILES = ['main.js', 'package.json', '.env.example', 'renderer'];

const LAUNCHER = `@echo off
rem Starts the VALORANT companion app with the settings and credentials from app\\.env.
setlocal
set "ELECTRON_RUN_AS_NODE="
if exist "%~dp0app\\.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0app\\.env") do set "%%a=%%b"
)
start "" "%~dp0runtime\\electron.exe" "%~dp0app"
`;

function copy(from, to) {
  fs.cpSync(from, to, { recursive: true });
}

function createShortcut(shortcut, target, workingDirectory, icon) {
  const quote = (text) => `'${text.replace(/'/g, "''")}'`;
  const script = [
    `$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut(${quote(shortcut)})`,
    `$shortcut.TargetPath = ${quote(target)}`,
    `$shortcut.WorkingDirectory = ${quote(workingDirectory)}`,
    `$shortcut.IconLocation = ${quote(`${icon},0`)}`,
    '$shortcut.WindowStyle = 7', // minimized: the launcher's console only blinks in the taskbar
    `$shortcut.Description = 'VALORANT companion app for Archipelago'`,
    '$shortcut.Save()',
  ].join('; ');
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { stdio: 'inherit' });
}

async function main() {
  const electron = require('@overwolf/ow-electron'); // downloads the runtime first if it's missing
  const runtime = path.dirname(electron);

  console.log('Building the window...');
  await (await import('./build.mjs')).build();

  console.log(`Packing into ${OUT}`);
  fs.rmSync(OUT, { recursive: true, force: true });
  copy(runtime, path.join(OUT, 'runtime'));

  const app = path.join(OUT, 'app');
  for (const file of APP_FILES) copy(path.join(ROOT, file), path.join(app, file));
  const env = path.join(ROOT, '.env');
  copy(fs.existsSync(env) ? env : path.join(ROOT, '.env.example'), path.join(app, '.env'));

  const launcher = path.join(OUT, 'Start VALORANT Companion.cmd');
  fs.writeFileSync(launcher, LAUNCHER.replace(/\n/g, '\r\n'));
  if (process.platform === 'win32') {
    createShortcut(path.join(OUT, 'VALORANT Companion.lnk'), launcher, OUT, path.join(OUT, 'runtime', 'electron.exe'));
  }

  console.log('Done. Start it with "VALORANT Companion" (or "Start VALORANT Companion.cmd") in that folder.');
  console.log('Settings and credentials live in app\\.env. The folder contains your credentials: keep it to yourself.');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
