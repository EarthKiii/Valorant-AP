// `npm run build`: compiles the Svelte windows in src/ into renderer/build/ (one .js and one .css per window).
// `npm run watch` rebuilds on every change (reload the window with Ctrl+R).
//
// Component styles are written to the .css file rather than injected at runtime: the windows' Content Security
// Policy only allows stylesheets shipped with the app.

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as esbuild from 'esbuild';
import { compile } from 'svelte/compiler';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const WINDOWS = { window: 'src/window/main.js', overlay: 'src/overlay/main.js' };

function location(file, position) {
  return position ? { file, line: position.line, column: position.column } : null;
}

function svelte() {
  return {
    name: 'svelte',
    setup(build) {
      const styles = new Map();

      build.onLoad({ filter: /\.svelte$/ }, async ({ path: file }) => {
        const source = await fs.readFile(file, 'utf8');
        let result;
        try {
          result = compile(source, { filename: file, css: 'external' });
        } catch (error) {
          return { errors: [{ text: error.message, location: location(file, error.start) }] };
        }
        let contents = result.js.code;
        if (result.css && result.css.code) {
          const stylesheet = `${file}.css`;
          styles.set(stylesheet, result.css.code);
          contents += `\nimport ${JSON.stringify(stylesheet)};`;
        }
        const warnings = result.warnings.map((warning) => ({
          text: `${warning.message} (${warning.code})`, location: location(file, warning.start),
        }));
        return { contents, warnings, resolveDir: path.dirname(file) };
      });

      build.onResolve({ filter: /\.svelte\.css$/ }, ({ path: stylesheet }) => ({ path: stylesheet, namespace: 'svelte-css' }));
      build.onLoad({ filter: /.*/, namespace: 'svelte-css' }, ({ path: stylesheet }) => ({
        contents: styles.get(stylesheet), loader: 'css', resolveDir: path.dirname(stylesheet),
      }));
    },
  };
}

function options(watch) {
  return {
    absWorkingDir: ROOT,
    entryPoints: Object.entries(WINDOWS).map(([out, entry]) => ({ in: entry, out })),
    outdir: 'renderer/build',
    bundle: true,
    format: 'iife',
    platform: 'browser',
    target: 'chrome148', // the Chromium inside ow-electron 42
    conditions: ['svelte', 'browser', 'production'],
    mainFields: ['svelte', 'browser', 'module', 'main'],
    minify: !watch,
    sourcemap: watch ? 'inline' : false,
    legalComments: 'none',
    logLevel: 'warning',
    plugins: [svelte()],
  };
}

export async function build({ analyze = false } = {}) {
  const result = await esbuild.build({ ...options(false), metafile: analyze });
  if (analyze) console.log(await esbuild.analyzeMetafile(result.metafile));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.argv.includes('--analyze')) {
    await build({ analyze: true }); // what's in each bundle, biggest first
  } else if (process.argv.includes('--watch')) {
    const context = await esbuild.context({ ...options(true), logLevel: 'info' });
    await context.watch();
    console.log('Watching src/ for changes...');
  } else {
    await build();
    console.log('Built renderer/build/.');
  }
}
