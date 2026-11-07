// Runs under the app's own Node runtime, on 127.0.0.1, reachable only through
// OpenDiscovery's proxy. `/snapshot` reads; `/status` is the same reading as the
// Work Status section OpenDiscovery draws (status-view.ts); `/stop` ends a dev
// server or what runs in the terminal, and decides itself what that may
// include (stop.ts).
//
// Sampling runs while someone is looking. Each read keeps it
// going; with no request for IDLE_STOP_MS the loop stops, so a closed panel
// costs nothing.
import http from 'node:http';

import { SAMPLE_INTERVAL_MS, Sampler } from './sampler.ts';
import { createProcessSource } from './sources.ts';
import { statusView } from './status-view.ts';
import { parseStopTarget } from './stop.ts';
import type { Snapshot } from '../shared/snapshot.ts';

const port = Number(process.env.OPENDISCOVERY_SERVICE_PORT);
const token = process.env.OPENDISCOVERY_SERVICE_TOKEN ?? '';
if (!port || !token) {
  console.error('OPENDISCOVERY_SERVICE_PORT and OPENDISCOVERY_SERVICE_TOKEN are required');
  process.exit(1);
}

const IDLE_STOP_MS = 20_000;
/** The second sample of a cold start: CPU needs two readings to be a number. */
const WARM_UP_MS = 700;

const source = createProcessSource();
// OpenDiscovery started this service, so its parent is the app: the Electron
// main process on desktop, the server process for `openchamber serve`.
const sampler = new Sampler(source, process.ppid, process.pid);

let latest: Snapshot | null = null;
let lastRequestAt = 0;
let running = false;
let timer: ReturnType<typeof setTimeout> | null = null;
let warming: Promise<void> | null = null;

const stop = (): void => {
  if (timer) clearTimeout(timer);
  timer = null;
  running = false;
  latest = null;
  sampler.reset();
  source.close();
};

const schedule = (): void => {
  timer = setTimeout(() => { void tick(); }, SAMPLE_INTERVAL_MS);
};

const tick = async (): Promise<void> => {
  timer = null;
  if (Date.now() - lastRequestAt > IDLE_STOP_MS) {
    stop();
    return;
  }
  try {
    latest = await sampler.sample();
  } catch {
    // Keep the previous snapshot; the next tick tries again.
  }
  if (running) schedule();
};

const ensureRunning = (): Promise<void> => {
  if (running && latest) return Promise.resolve();
  if (warming) return warming;
  warming = (async () => {
    try {
      latest = await sampler.sample();
      await new Promise((resolve) => setTimeout(resolve, WARM_UP_MS));
      latest = await sampler.sample();
      running = true;
      schedule();
    } finally {
      warming = null;
    }
  })();
  return warming;
};

const json = (res: http.ServerResponse, status: number, body: unknown): void => {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
};

const server = http.createServer((req, res) => {
  if (req.headers.authorization !== `Bearer ${token}`) {
    json(res, 401, { error: 'unauthorized' });
    return;
  }
  const url = new URL(req.url ?? '/', 'http://127.0.0.1');
  if (url.pathname === '/health') {
    json(res, 200, { ok: true });
    return;
  }
  if (req.method === 'POST' && url.pathname === '/stop') {
    let body = '';
    req.on('data', (chunk: Buffer) => {
      body += chunk.toString('utf8');
    });
    req.on('end', () => {
      let target;
      try {
        target = parseStopTarget(JSON.parse(body));
      } catch {
        target = null;
      }
      if (!target) {
        json(res, 400, { error: 'bad-request' });
        return;
      }
      sampler.stop(target).then(
        (result) => (result ? json(res, 200, result) : json(res, 404, { error: 'not-stoppable' })),
        () => json(res, 500, { error: 'stop-failed' }),
      );
    });
    return;
  }
  // `/snapshot` feeds the panel and the section's frame; `/status` is the
  // section OpenDiscovery draws itself. Both keep the sampler running.
  const view = url.pathname === '/status';
  if (req.method !== 'GET' || (url.pathname !== '/snapshot' && !view)) {
    json(res, 404, { error: 'not-found' });
    return;
  }
  lastRequestAt = Date.now();
  const locale = url.searchParams.get('locale') ?? 'en';
  ensureRunning().then(() => {
    if (!latest) {
      json(res, 503, { error: 'no-sample' });
      return;
    }
    json(res, 200, view ? statusView(latest, locale) : latest);
  }).catch(() => json(res, 500, { error: 'sample-failed' }));
});

const shutdown = (): void => {
  stop();
  server.close();
  process.exit(0);
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

server.listen(port, '127.0.0.1');
