import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const state = process.env.OPENDISCOVERY_EXTENSION_STATE;
const cache = process.env.OPENDISCOVERY_EXTENSION_CACHE;
if (!state || !cache || !path.isAbsolute(state) || !path.isAbsolute(cache)) {
  throw new Error('OpenDiscovery extension state and cache are required');
}
await fs.mkdir(state, { recursive: true, mode: 0o700 });
// Preserve the server's direct-entry startup guard and its transport lifecycle.
const entry = new URL('../dist/server.mjs', import.meta.url);
process.argv[1] = fileURLToPath(entry);
await import(entry.href);
