import { describe, expect, test } from 'bun:test';

import type { RawProcess } from './parse.ts';
import { parseStopTarget, planStop } from './stop.ts';
import { collectTree } from './tree.ts';

const proc = (pid: number, ppid: number, name: string, tty?: string): RawProcess => ({ pid, ppid, name, memory: 1, cpuSeconds: 0, ...(tty ? { tty } : {}) });

// app → helper; opencode → claude, (bun run dev → node → vite); terminal zsh → (npm → node); project action bun (exec'd); service
const processes: RawProcess[] = [
  proc(100, 1, 'OpenDiscovery'),
  proc(101, 100, 'OpenDiscovery Helper'),
  proc(200, 100, 'opendiscovery-engine'),
  proc(210, 200, 'claude'),
  proc(220, 200, 'bun'),
  proc(221, 220, 'node'),
  proc(222, 221, 'node'),
  proc(300, 100, 'zsh', 'ttys001'),
  proc(310, 300, 'npm', 'ttys001'),
  proc(311, 310, 'node', 'ttys001'),
  proc(400, 100, 'bun', 'ttys002'),
  proc(401, 400, 'node', 'ttys002'),
  proc(500, 100, 'OpenDiscovery'),
];
const members = collectTree(processes, 100, 500);
const commands = new Map([[200, 'opendiscovery-engine serve --port 4096']]);
const sorted = (pids: number[] | undefined) => [...(pids ?? [])].sort((a, b) => a - b);

describe('planStop', () => {
  test('a job goes whole, wrappers and watchers included', () => {
    expect(sorted(planStop(members, commands, { kind: 'job', pid: 220, name: 'bun' })?.pids)).toEqual([220, 221, 222]);
    expect(planStop(members, commands, { kind: 'job', pid: 220, name: 'bun' })?.needsPort).toBe(true);
    expect(planStop(members, commands, { kind: 'job', pid: 310, name: 'npm' })).toEqual({ pids: [310, 311], needsPort: false });
  });

  test("never the app, its helpers, the OpenDiscovery Engine server, a shell, a job's inner process, or this service", () => {
    for (const [pid, name] of [[100, 'OpenDiscovery'], [101, 'OpenDiscovery Helper'], [200, 'opendiscovery-engine'], [300, 'zsh'], [221, 'node'], [500, 'OpenDiscovery']] as const) {
      expect(planStop(members, commands, { kind: 'job', pid, name })).toBeNull();
    }
  });

  test('a reused pid under another name is refused', () => {
    expect(planStop(members, commands, { kind: 'job', pid: 220, name: 'python' })).toBeNull();
  });

  test('stop all in the terminal keeps the shell and ends project actions', () => {
    expect(sorted(planStop(members, commands, { kind: 'terminals' })?.pids)).toEqual([310, 311, 400, 401]);
  });

  test('only well-formed requests get through', () => {
    expect(parseStopTarget({ kind: 'job', pid: 220, name: 'bun' })).toEqual({ kind: 'job', pid: 220, name: 'bun' });
    expect(parseStopTarget({ kind: 'terminals' })).toEqual({ kind: 'terminals' });
    expect(parseStopTarget({ kind: 'job', pid: -1, name: 'bun' })).toBeNull();
    expect(parseStopTarget({ kind: 'job', pid: 2.5, name: 'bun' })).toBeNull();
    expect(parseStopTarget({ kind: 'everything' })).toBeNull();
    expect(parseStopTarget(null)).toBeNull();
  });
});
