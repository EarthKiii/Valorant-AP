'use strict';
// `npm run sfx`: turns the packed companion (dist/VALORANT Companion/, from `npm run pack`) into a single
// self-extracting setup: dist/VALORANT Companion Setup.exe (see setup.cs for what it does when run).
//
// Your credentials never go into it: the packed app\.env is swapped for the blank .env.example, and the setup keeps
// whatever app\.env an existing install already has. Built with the C# compiler that ships with Windows.

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const PACKED = path.join(ROOT, 'dist', 'VALORANT Companion');
const OUTPUT = path.join(ROOT, 'dist', 'VALORANT Companion Setup.exe');
const WORK = path.join(ROOT, 'dist', '.setup-build');
const FRAMEWORK = path.join(process.env.WINDIR || 'C:\\Windows', 'Microsoft.NET', 'Framework64', 'v4.0.30319');

const quote = (text) => `'${text.replace(/'/g, "''")}'`;

function powershell(lines) {
  const script = path.join(WORK, 'step.ps1');
  fs.writeFileSync(script, lines.join('\r\n'));
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script],
    { stdio: 'inherit' });
}

function zipPayload(zip) {
  // Every packed file except your credentials and the packed shortcut (the setup makes its own).
  powershell([
    "$ErrorActionPreference = 'Stop'",
    'Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem',
    `$source = ${quote(PACKED)}`,
    `$archive = [IO.Compression.ZipFile]::Open(${quote(zip)}, 'Create')`,
    'try {',
    '  Get-ChildItem -LiteralPath $source -Recurse -File -Force | ForEach-Object {',
    "    $name = $_.FullName.Substring($source.Length + 1).Replace('\\', '/')",
    "    if ($name -ne 'app/.env' -and $name -notlike '*.lnk') {",
    "      [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $name, 'Optimal')",
    '    }',
    '  }',
    "  $blank = Join-Path $source 'app\\.env.example'",
    "  [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $blank, 'app/.env', 'Optimal')",
    '} finally { $archive.Dispose() }',
  ]);
}

function extractIcon(icon) {
  powershell([
    "$ErrorActionPreference = 'Stop'",
    'Add-Type -AssemblyName System.Drawing',
    `$icon = [Drawing.Icon]::ExtractAssociatedIcon(${quote(path.join(PACKED, 'runtime', 'electron.exe'))})`,
    `$stream = [IO.File]::Create(${quote(icon)})`,
    'try { $icon.Save($stream) } finally { $stream.Dispose() }',
  ]);
}

function main() {
  if (process.platform !== 'win32') throw new Error('The setup exe can only be built on Windows.');
  if (!fs.existsSync(path.join(PACKED, 'Start VALORANT Companion.cmd'))) {
    throw new Error('Run `npm run pack` first (or use `npm run sfx`, which does both).');
  }
  fs.rmSync(WORK, { recursive: true, force: true });
  fs.mkdirSync(WORK, { recursive: true });
  const zip = path.join(WORK, 'payload.zip');
  const icon = path.join(WORK, 'companion.ico');

  console.log('Compressing the packed companion...');
  zipPayload(zip);
  extractIcon(icon);

  console.log('Building the setup...');
  fs.rmSync(OUTPUT, { force: true });
  execFileSync(path.join(FRAMEWORK, 'csc.exe'), [
    '/nologo', '/target:winexe', '/optimize+', '/platform:anycpu',
    `/out:${OUTPUT}`, `/win32icon:${icon}`, `/resource:${zip},payload.zip`,
    '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
    '/reference:System.Windows.Forms.dll', path.join(__dirname, 'setup.cs'),
  ], { stdio: 'inherit' });
  fs.rmSync(WORK, { recursive: true, force: true });

  const size = (fs.statSync(OUTPUT).size / 1024 / 1024).toFixed(0);
  console.log(`Done: ${OUTPUT} (${size} MB). It contains no credentials, so it's safe to share.`);
}

main();
